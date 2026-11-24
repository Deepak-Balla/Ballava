import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { useHashRoute, go, api, useBrain } from './lib.js';
import { useSynced, startSync, rejoin, wipeDevice } from './sync.js';
import { setLang, t } from './i18n.js';
import { defaultExpiry, dayKey, slotNow, getCatalog, setCatalog as storeCatalog, recipeById, hasCatalog } from './catalog.js';
import Home from './screens/Home.jsx';
import Pantry from './screens/Pantry.jsx';
import Recipe from './screens/Recipe.jsx';
import Cook from './screens/Cook.jsx';
import Bachao from './screens/Bachao.jsx';
import Family from './screens/Family.jsx';
import Shopping from './screens/Shopping.jsx';
import AiChef from './screens/AiChef.jsx';
import Plan from './screens/Plan.jsx';
import Dashboard from './screens/Dashboard.jsx';
import More from './screens/More.jsx';
import Account from './screens/Account.jsx';
import Login from './screens/Login.jsx';
import Vote from './screens/Vote.jsx';
import Saved from './screens/Saved.jsx';
import Settings from './screens/Settings.jsx';
import Assistant from './Assistant.jsx';
import { applyLook } from './look.js';
import { hasReturned } from './supabase.js';

const isGuest = () => { try { return localStorage.getItem('ballava.guest') === '1'; } catch { return false; } };

export default function App() {
  const route = useHashRoute();
  const [pantry, setPantry] = useSynced('pantry', []);
  const [members, setMembers] = useSynced('members', []);
  const [shopping, setShopping] = useSynced('shopping', []);
  const [history, setHistory] = useSynced('history', []);
  const [aiRecipes, setAiRecipes] = useSynced('aiRecipes', {});
  const [filters, setFilters] = useSynced('filters', {});
  const [plan, setPlan] = useSynced('plan', {});
  const [pins, setPins] = useSynced('pins', []);
  const [prefs, setPrefs] = useSynced('prefs', {});
  const [savedDishes, setSavedDishes] = useSynced('savedDishes', []);
  const [chatOpen, setChatOpen] = useState(false);
  const [catalog, setCatalog] = useState(getCatalog);
  const [catalogFailed, setCatalogFailed] = useState(false);
  const [toast, setToast] = useState(null);
  const [aiStatus, setAiStatus] = useState({ checked: false, ai: false, server: false });
  const [auth, setAuth] = useState({ checked: false, user: null, household: null });
  const [guest, setGuest] = useState(() => isGuest() && !hasReturned());

  setLang(prefs.lang);
  // Settings → Look (theme, colour, text size...), applied to the whole page, even before signing in.
  useEffect(() => { applyLook(prefs); }, [prefs.theme, prefs.accent, prefs.textSize, prefs.reduceMotion, prefs.showCalories, prefs.voiceRate]);
  // Settings → Open the app on: only when the app opens without a page in the address.
  useEffect(() => { if (!location.hash && prefs.startPage && prefs.startPage !== 'dashboard') go(prefs.startPage); }, []);

  const notify = useCallback((msg) => {
    setToast(msg);
    clearTimeout(window.__toastT);
    window.__toastT = setTimeout(() => setToast(null), 3500);
  }, []);

  const signedOut = useCallback(() => {
    wipeDevice();
    location.hash = '';
    location.reload();
  }, []);

  // The server said "not signed in" while saving. Double-check before clearing this phone,
  // so a passing server hiccup never throws away changes that haven't been saved yet.
  const sessionLost = useCallback(async () => {
    try {
      const me = await api('me');
      if (!me.user) signedOut();
    } catch { /* can't tell right now: keep everything and try again later */ }
  }, [signedOut]);

  const loadMe = useCallback(async ({ merge = false, rejoined = false } = {}) => {
    const me = await api('me');
    setAuth({ checked: true, user: me.user, household: me.household || null });
    if (!me.user) return;
    if (rejoined) await rejoin(sessionLost);
    else await startSync({ merge, onLost: sessionLost });
  }, [sessionLost]);

  // Is the AI switched on? Asked when the app opens, again whenever Chef or Recipe Studio opens,
  // and when you come back to the tab, so a server restart or a newly added key never leaves it stuck on "off".
  const held = useRef({ stamp: null, loading: false }); // which version of the recipe book and festivals this screen has
  const loadCatalog = useCallback(async () => {
    if (held.current.loading) return;
    held.current.loading = true;
    try {
      const c = await api('catalog');
      storeCatalog(c);
      setCatalog(getCatalog());
      held.current.stamp = c.stamp;
    } finally { held.current.loading = false; }
  }, []);
  const refreshAi = useCallback(() => api('health')
    .then(d => { setAiStatus({ checked: true, ai: !!d.ai, provider: d.aiProvider || null, server: true, retentionDays: d.retentionDays });
      // Admins changed something (a festival, an announcement, a recipe)? Fetch it, without a reload.
      if (d.catalog !== held.current.stamp) loadCatalog().catch(() => {});
      return d;
    })
    .catch(() => setAiStatus(s => ({ ...s, checked: true, server: false }))), []);
  useEffect(() => {
    const onFocus = () => refreshAi();
    window.addEventListener('focus', onFocus);
    const timer = setInterval(() => document.visibilityState === 'visible' && refreshAi(), 30000);
    return () => { window.removeEventListener('focus', onFocus); clearInterval(timer); };
  }, [refreshAi]);

  // Ballava keeps things for 6 months (the server decides how long). Old meals, saved dishes and AI recipes are
  // trimmed on this phone too, so they don't linger offline or for people using it without an account.
  useEffect(() => {
    const days = aiStatus.retentionDays;
    if (!days) return;
    const cutMs = Date.now() - days * 86400000;
    const cutDay = dayKey(cutMs);
    const fresh = h => (h.date ? h.date >= cutDay : (h.at || 0) >= cutMs);
    if (history.some(h => !fresh(h))) setHistory(hs => hs.filter(fresh));
    if (savedDishes.some(s => s.at && s.at < cutMs)) setSavedDishes(ss => ss.filter(s => !s.at || s.at >= cutMs));
    const keep = new Set(savedDishes.map(s => s.id));
    if (Object.values(aiRecipes).some(r => r.createdAt && r.createdAt < cutMs && !keep.has(r.id))) {
      setAiRecipes(rs => Object.fromEntries(Object.entries(rs).filter(([id, r]) => !r.createdAt || r.createdAt >= cutMs || keep.has(id))));
    }
    try {
      const chats = JSON.parse(localStorage.getItem('ballava.chats') || 'null');
      if (chats?.list?.some(c => (c.at || 0) < cutMs)) {
        localStorage.setItem('ballava.chats', JSON.stringify({ ...chats, list: chats.list.filter(c => (c.at || 0) >= cutMs) }));
      }
    } catch { /* nothing saved */ }
  }, [aiStatus.retentionDays]);

  useEffect(() => {
    loadMe().catch(() => {
      // No connection: if this device was signed in, keep working from what it has.
      let cached = null;
      try { cached = JSON.parse(localStorage.getItem('ballava._user') || 'null'); } catch { /* nothing stored */ }
      setAuth({ checked: true, user: cached, household: null });
      if (cached) startSync({ onLost: sessionLost });
    });
    // The recipe book comes from the Python server, and is kept on the phone for offline use.
    loadCatalog().catch(() => setCatalogFailed(true)).then(refreshAi);
  }, [loadMe]);

  useEffect(() => {
    try { if (auth.user) localStorage.setItem('ballava._user', JSON.stringify(auth.user)); } catch { /* ignore */ }
  }, [auth.user]);

  // Latest rating per recipe: Ballava learns your "andaaz" (taste) from this.
  const ratings = useMemo(() => {
    const r = {};
    for (const h of history) if (h.rating && h.recipeId) r[h.recipeId] = h.rating;
    return r;
  }, [history]);

  // Older diary entries only have a timestamp; give each a day and a meal for display.
  const log = useMemo(() => history.map(h => ({ ...h, date: h.date || dayKey(h.at), slot: h.slot || slotNow(h.at) })), [history]);
  // What the family knows, sent along whenever the Python brain is asked something.
  const family = useMemo(() => ({ pantry, members, history, pins, aiRecipes, savedDishes, fastDays: prefs.fastDays, notKept: prefs.notKept }),
    [pantry, members, history, pins, aiRecipes, savedDishes, prefs.fastDays, prefs.notKept]);
  // Who fasts in the next month (weekly fasts, fasting festivals and chosen days), worked out by Python.
  const fastInfo = useBrain('fasts', { ...family, festivals: catalog.festivals }, auth.checked && hasCatalog() && route[0] !== 'vote');
  const fasts = fastInfo.data?.fasts || null;
  // "Fasting today" used to stay ticked for ever. It's now a choice for one day, so yesterday's fast ends by itself.
  useEffect(() => {
    const ticked = members.filter(m => m.fasting).map(m => m.name);
    if (!ticked.length) return;
    const today = dayKey();
    setPrefs(p => ({ ...p, fastDays: { ...p.fastDays, [today]: ticked.length === members.length ? ['*'] : ticked } }));
    setMembers(ms => ms.map(({ fasting: _f, ...m }) => m));
  }, [members]);

  // Returns the ids that were actually new (so messages can be accurate).
  const addToPantry = useCallback((ids) => {
    const now = Date.now();
    const have = new Set(pantry.map(p => p.id));
    const added = [...new Set(ids)].filter(id => !have.has(id));
    if (added.length) {
      setPantry(prev => {
        const h = new Set(prev.map(p => p.id));
        return [...prev, ...added.filter(id => !h.has(id)).map(id => ({ id, addedAt: now, expiresAt: defaultExpiry(id, now) }))];
      });
    }
    return added;
  }, [pantry, setPantry]);

  const addToShopping = useCallback((ids) => {
    setShopping(prev => {
      const have = new Set(prev.map(s => s.id));
      return [...prev, ...ids.filter(id => !have.has(id)).map(id => ({ id, done: false }))];
    });
  }, [setShopping]);

  const logMeal = useCallback(({ recipeId = null, name, date = dayKey(), slot = slotNow(), rating = null, saved = [] }) => {
    const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
    setHistory(h => [...h, { id, recipeId, name, date, slot, at: Date.now(), rating, saved }]);
  }, [setHistory]);

  const findRecipe = useCallback(id => recipeById(id) || aiRecipes[id], [aiRecipes, catalog]);

  // ❤️ Saved dishes, shared with the family. AI recipes are kept in aiRecipes, so saving one keeps it too.
  const savedIds = useMemo(() => new Set(savedDishes.map(s => s.id)), [savedDishes]);
  const isSaved = useCallback(id => savedIds.has(id), [savedIds]);
  const toggleSave = useCallback(recipe => {
    const on = savedIds.has(recipe.id);
    setSavedDishes(list => (on ? list.filter(s => s.id !== recipe.id) : [...list.filter(s => s.id !== recipe.id), { id: recipe.id, at: Date.now() }]));
    if (!on && recipe.ai) setAiRecipes(r => ({ ...r, [recipe.id]: recipe }));
    notify(on ? `Removed ${recipe.name} from saved dishes` : `Saved ${recipe.name} ❤️`);
  }, [savedIds, setSavedDishes, setAiRecipes, notify]);

  const [screen, param, extraParam] = route;
  // Moving to another screen closes the AI window; the old #/ask address opens it.
  useEffect(() => { setChatOpen(screen === 'ask'); }, [screen, param]);
  if (screen === 'vote') return <Vote group={param} choice={extraParam} />;

  if (!auth.checked) return <div className="splash"><span className="brand-mark">B</span></div>;
  if (!auth.user && !guest) {
    return <Login onDone={() => loadMe({ merge: true })} onGuest={() => { try { localStorage.setItem('ballava.guest', '1'); } catch { /* ok */ } setGuest(true); }} server={aiStatus.server || !aiStatus.checked} />;
  }

  if (!hasCatalog()) {
    return (
      <div className="splash">
        <div className="center">
          <span className="brand-mark">B</span>
          <p className="muted">{catalogFailed ? 'Ballava needs an internet connection the first time it opens. Please connect and refresh.' : 'Loading recipes…'}</p>
        </div>
      </div>
    );
  }

  const ctx = {
    pantry, setPantry, addToPantry, members, setMembers, shopping, setShopping, addToShopping, history, setHistory, log, logMeal, ratings, aiRecipes, setAiRecipes,
    filters, setFilters, notify, aiStatus, findRecipe, plan, setPlan, pins, setPins, prefs, setPrefs, catalog, family, fasts, fastsLoading: fastInfo.loading, auth, loadMe, signedOut,
    savedDishes, isSaved, toggleSave, openAssistant: () => setChatOpen(true), refreshAi,
  };

  let body;
  switch (screen) {
    case 'pantry': body = <Pantry {...ctx} />; break;
    case 'recipe': body = <Recipe {...ctx} recipe={findRecipe(param)} />; break;
    case 'cook': body = <Cook {...ctx} recipe={findRecipe(param)} />; break;
    case 'bachao': body = <Bachao {...ctx} />; break;
    case 'family': body = <Family {...ctx} />; break;
    case 'list': body = <Shopping {...ctx} />; break;
    case 'ai': body = <AiChef {...ctx} />; break;
    case 'plan': body = <Plan {...ctx} />; break;
    case 'dashboard': case 'track': body = <Dashboard {...ctx} view={screen === 'track' ? 'diary' : 'overview'} />; break;
    case 'more': body = <More {...ctx} />; break;
    case 'saved': body = <Saved {...ctx} />; break;
    case 'settings': body = <Settings {...ctx} />; break;
    case 'account': body = <Account {...ctx} />; break;
    default: body = <Home {...ctx} />; // also #/ask, the old chat address: Home with the AI window open
  }

  // The Dashboard comes first; 🧑‍🍳 Chef sits in the middle of the bar, one tap away on every screen.
  // On a computer the same bar becomes a sidebar on the left (see the end of styles.css).
  const tabs = [
    ['dashboard', 'Dashboard', '📊'], ['home', 'Cook', '🍳'], ['plan', 'Plan', '🗓️'], ['chef', 'Chef', '🧑‍🍳'], ['pantry', 'Kitchen', '🧺'],
    ['list', 'List', '🛒'], ['more', 'More', '☰'],
  ];
  const moreScreens = ['more', 'family', 'bachao', 'account', 'saved', 'settings'];
  const active = id => (id === 'more' ? moreScreens.includes(screen)
    : id === 'dashboard' ? ['dashboard', 'track'].includes(screen)
      : screen === id || (id === 'home' && !['plan', 'track', 'dashboard', 'pantry', 'list', ...moreScreens].includes(screen)));
  const hideNav = screen === 'cook';
  const listCount = shopping.filter(s => !s.done).length;

  return (
    <div className={'app' + (hideNav ? ' no-nav' : '') + (chatOpen ? ' chat-open' : '')}>
      <main>{body}</main>
      {chatOpen && <Assistant screen={screen} param={param} onClose={() => setChatOpen(false)} ctx={ctx} />}
      {toast && <div className="toast" role="status">{toast}</div>}
      {!hideNav && (
        <nav className="tabbar" aria-label="Main">
          <a className="nav-brand" href="#/dashboard" aria-label="Ballava, go to the dashboard"><span className="brand-mark" aria-hidden="true">B</span><span>Ballava</span></a>
          {tabs.map(([id, label, icon]) => (id === 'chef' ? (
            <button key={id} className={'ai-tab' + (chatOpen ? ' active' : '')} onClick={() => setChatOpen(o => !o)}
              aria-label="Ballava Chef" aria-expanded={chatOpen}>
              <span className="ai-orb" aria-hidden="true">{icon}</span>
              <span>{label}</span>
            </button>
          ) : (
            <button key={id} className={active(id) && !chatOpen ? 'active' : ''} onClick={() => { setChatOpen(false); go(id); }} aria-label={t(label)}>
              <span className="tab-icon" aria-hidden="true">{icon}</span>
              <span>{t(label)}</span>
              {id === 'list' && listCount > 0 && <span className="badge">{listCount}</span>}
            </button>
          )))}
        </nav>
      )}
    </div>
  );
}
