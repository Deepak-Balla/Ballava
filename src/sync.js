// Keeps family data in step between this device and the server.
// The app always reads and writes this device first, so it works offline.
// When signed in, changes are sent up in the background and other people's changes come down.
import { useEffect, useRef, useState } from 'react';
import { api } from './lib.js';

const KEYS = ['pantry', 'members', 'shopping', 'history', 'aiRecipes', 'filters', 'plan', 'pins', 'prefs'];
const PREFIX = 'ballava.';

const read = (key, fallback) => {
  try { const raw = localStorage.getItem(PREFIX + key); return raw ? JSON.parse(raw) : fallback; } catch { return fallback; }
};
const write = (key, value) => {
  try { localStorage.setItem(PREFIX + key, JSON.stringify(value)); } catch { /* private mode: keep in memory */ }
};
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const isEmpty = v => v == null || (Array.isArray(v) ? v.length === 0 : typeof v === 'object' && Object.keys(v).length === 0);

const hooks = new Map();
const sync = { signedIn: false, versions: read('_versions', {}), dirty: new Set(read('_dirty', [])), timer: null, pushing: false, ticker: null, onLost: null };
const saveMeta = () => { write('_versions', sync.versions); write('_dirty', [...sync.dirty]); };

const ID_OF = {
  pantry: x => x.id, shopping: x => x.id, members: x => x.name,
  history: x => x.id || `${x.at}:${x.name}`, pins: x => `${x.recipeId}:${x.weekday}`,
};

// When two people changed the same thing, keep both sides. This device wins on the same item.
export function mergeValues(key, local, remote) {
  if (remote == null) return local;
  if (local == null) return remote;
  const idOf = ID_OF[key];
  if (idOf) {
    const out = new Map(remote.map(x => [idOf(x), x]));
    for (const x of local) out.set(idOf(x), x);
    return [...out.values()];
  }
  return { ...remote, ...local };
}

function apply(key, value) {
  const hook = hooks.get(key);
  if (hook && !same(hook.get(), value)) hook.set(value);
}

function schedule(ms = 700) {
  if (!sync.signedIn) return;
  clearTimeout(sync.timer);
  sync.timer = setTimeout(push, ms);
}

function markDirty(key) {
  if (!sync.signedIn) return;
  sync.dirty.add(key);
  saveMeta();
  schedule();
}

// Like useState, but saved on this device and shared with the family.
export function useSynced(key, initial) {
  const [value, setValue] = useState(() => read(key, initial));
  const latest = useRef(value);
  latest.current = value;
  const skipNext = useRef(true);
  useEffect(() => {
    hooks.set(key, { get: () => latest.current, set: v => { skipNext.current = true; latest.current = v; setValue(v); } });
    return () => hooks.delete(key);
  }, [key]);
  useEffect(() => {
    write(key, value);
    if (skipNext.current) { skipNext.current = false; return; }
    markDirty(key);
  }, [key, value]);
  return [value, setValue];
}

async function push() {
  if (!sync.signedIn || sync.pushing || !navigator.onLine) return;
  sync.pushing = true;
  try {
    for (const key of [...sync.dirty]) {
      const value = hooks.get(key)?.get();
      if (value === undefined) continue;
      try {
        const { version } = await api('state', { key, value, baseVersion: sync.versions[key] || 0 });
        sync.versions[key] = version;
        if (same(hooks.get(key)?.get(), value)) sync.dirty.delete(key);
      } catch (e) {
        if (e.status === 409) {
          sync.versions[key] = e.data.version;
          apply(key, mergeValues(key, hooks.get(key)?.get(), e.data.value));
        } else if (e.status === 401) {
          sync.onLost?.();
          return;
        } else break; // offline or server trouble: the next tick tries again
      }
    }
    saveMeta();
  } finally {
    sync.pushing = false;
    if (sync.dirty.size && sync.signedIn) sync.timer = setTimeout(push, 2500);
  }
}

async function pull(merge = false) {
  if (!sync.signedIn) return;
  const { items } = await api('state');
  for (const key of KEYS) {
    const remote = items[key];
    const local = hooks.get(key)?.get();
    if (merge) {
      if (!remote) { if (!isEmpty(local)) sync.dirty.add(key); continue; }
      sync.versions[key] = remote.version;
      const merged = mergeValues(key, local, remote.value);
      apply(key, merged);
      if (!same(merged, remote.value)) sync.dirty.add(key);
    } else if (remote && remote.version !== sync.versions[key] && !sync.dirty.has(key)) {
      sync.versions[key] = remote.version;
      apply(key, remote.value);
    }
  }
  saveMeta();
  if (sync.dirty.size) schedule(100);
}

const refresh = () => { pull().catch(() => {}); push(); };

// merge = true when this device's data should be added to the family's (first sign-in, joining a family).
export async function startSync({ merge = false, onLost } = {}) {
  sync.signedIn = true;
  sync.onLost = onLost;
  if (!sync.ticker) {
    sync.ticker = setInterval(refresh, 20000);
    window.addEventListener('online', refresh);
    window.addEventListener('focus', refresh);
  }
  await pull(merge).catch(() => {});
  push();
}

export const syncNow = () => pull();

export function pendingChanges() { return sync.dirty.size; }

export function stopSync() {
  sync.signedIn = false;
  clearInterval(sync.ticker);
  clearTimeout(sync.timer);
  sync.ticker = null;
  window.removeEventListener('online', refresh);
  window.removeEventListener('focus', refresh);
}

// After joining another family: forget this device's version numbers, then merge.
export async function rejoin(onLost) {
  sync.versions = {};
  sync.dirty.clear();
  saveMeta();
  await startSync({ merge: true, onLost });
}

// Signing out removes the family's data from this device, because phones get shared.
export function wipeDevice() {
  stopSync();
  try {
    for (const k of Object.keys(localStorage)) if (k.startsWith(PREFIX) && k !== PREFIX + 'voter') localStorage.removeItem(k);
  } catch { /* nothing stored */ }
}
