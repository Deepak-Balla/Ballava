// Small browser helpers: saved state, voice, sound, sharing.
import { useEffect, useState } from 'react';

// State that survives a page reload (saved in this browser only).
export function useStored(key, initial) {
  const [value, setValue] = useState(() => {
    try {
      const raw = localStorage.getItem('ballava.' + key);
      return raw ? JSON.parse(raw) : initial;
    } catch { return initial; }
  });
  useEffect(() => {
    try { localStorage.setItem('ballava.' + key, JSON.stringify(value)); } catch { /* private mode: keep in memory */ }
  }, [key, value]);
  return [value, setValue];
}

export function useHashRoute() {
  const read = () => (location.hash.replace(/^#\/?/, '') || 'dashboard').split('/'); // the Dashboard is the first screen
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const on = () => { setRoute(read()); window.scrollTo(0, 0); };
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  return route;
}
export const go = path => { location.hash = '#/' + path; };

// ---- Voice input (speech to text). Works in Chrome / Edge / Android.
export const SpeechRec = typeof window !== 'undefined' && (window.SpeechRecognition || window.webkitSpeechRecognition);

export function listenOnce(onText, onEnd) {
  if (!SpeechRec) return null;
  const rec = new SpeechRec();
  rec.lang = 'en-IN';
  rec.interimResults = false;
  rec.onresult = e => onText(e.results[0][0].transcript);
  rec.onend = () => onEnd && onEnd();
  rec.onerror = () => onEnd && onEnd();
  try { rec.start(); } catch { onEnd && onEnd(); }
  return rec;
}

// ---- Read aloud (text to speech).
// Hands-free mode must not hear the app's own voice as a command, so we remember when we last spoke.
let speakingUntil = 0;
let voiceRate = 0.95; // Settings → Cooking → Voice speed
export const setVoiceRate = rate => { voiceRate = Number(rate) || 0.95; };
export function speak(text) {
  try {
    if (!('speechSynthesis' in window)) return;
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'en-IN';
    u.rate = voiceRate;
    speakingUntil = Date.now() + 60000; // until it finishes (or a minute, if the browser never says)
    u.onend = u.onerror = () => { speakingUntil = Date.now() + 1200; }; // the tail of our voice can still arrive
    speechSynthesis.speak(u);
  } catch { /* ignore */ }
}
export function stopSpeaking() { try { speechSynthesis.cancel(); speakingUntil = Math.min(speakingUntil, Date.now() + 600); } catch { /* ignore */ } }
export const isSpeaking = () => Date.now() < speakingUntil || (typeof speechSynthesis !== 'undefined' && speechSynthesis.speaking);

// ---- Alarm beep + vibration for timers.
let audioCtx;
export function beep(times = 3) {
  try {
    audioCtx ||= new (window.AudioContext || window.webkitAudioContext)();
    for (let i = 0; i < times; i++) {
      const o = audioCtx.createOscillator();
      const g = audioCtx.createGain();
      o.frequency.value = 880;
      o.connect(g); g.connect(audioCtx.destination);
      const t = audioCtx.currentTime + i * 0.45;
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(0.4, t + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 0.35);
      o.start(t); o.stop(t + 0.4);
    }
  } catch { /* ignore */ }
  try { navigator.vibrate && navigator.vibrate([300, 150, 300, 150, 300]); } catch { /* ignore */ }
}

// ---- Keep the screen on while cooking.
export async function keepAwake() {
  try { return await navigator.wakeLock.request('screen'); } catch { return null; }
}

export const whatsappLink = text => 'https://wa.me/?text=' + encodeURIComponent(text);

export function fmtTime(sec) {
  const m = Math.floor(sec / 60), s = sec % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

// Shrink a photo before sending it to the AI (saves data, and phones take huge photos).
export function shrinkImage(file, max = 1024) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const scale = Math.min(1, max / Math.max(img.width, img.height));
      const c = document.createElement('canvas');
      c.width = Math.round(img.width * scale); c.height = Math.round(img.height * scale);
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
      resolve(c.toDataURL('image/jpeg', 0.85).split(',')[1]);
      URL.revokeObjectURL(img.src);
    };
    img.onerror = () => reject(new Error('Could not read that photo'));
    img.src = URL.createObjectURL(file);
  });
}

// ---- Talking to the Python server (Django). ----
// Django only accepts changes that carry its CSRF token, which it hands out in a cookie on any API call.
const csrfToken = () => (document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/) || [])[1];

export async function api(path, body) {
  if (body && !csrfToken()) await fetch('api/auth/config').catch(() => {});
  const res = await fetch('api/' + path, body ? {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() || '' }, body: JSON.stringify(body),
  } : undefined);
  let data = {};
  try { data = await res.json(); } catch { /* not JSON */ }
  if (!res.ok) throw Object.assign(new Error(data.error || `Request failed (${res.status})`), { status: res.status, data });
  return data;
}

// Asks the Python "brain" (kitchen/planner.py) to think. The last good answer is remembered,
// so when there's no connection the screen can still show something useful.
export async function brain(name, body) {
  const key = 'ballava.brain.' + name;
  try {
    const data = await api('brain/' + name, { ...body, tz: new Date().getTimezoneOffset() });
    try { localStorage.setItem(key, JSON.stringify(data)); } catch { /* storage full */ }
    return data;
  } catch (err) {
    if (err.status) throw err; // the server answered with a real error
    let cached = null;
    try { cached = JSON.parse(localStorage.getItem(key) || 'null'); } catch { /* nothing saved */ }
    if (cached) return { ...cached, offline: true };
    throw Object.assign(new Error("You're offline. Connect to the internet and try again."), { offline: true });
  }
}

// React hook: re-asks the brain whenever `body` changes. Returns { data, loading, error }.
export function useBrain(name, body, enabled = true) {
  const key = JSON.stringify(body);
  const [state, setState] = useState({ data: null, loading: enabled, error: null });
  useEffect(() => {
    if (!enabled) return undefined;
    let live = true;
    setState(s => ({ ...s, loading: true }));
    const timer = setTimeout(() => {
      brain(name, body).then(data => live && setState({ data, loading: false, error: null }))
        .catch(error => live && setState(s => ({ ...s, loading: false, error })));
    }, 150);
    return () => { live = false; clearTimeout(timer); };
  }, [name, key, enabled]);
  return state;
}
