import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { useHashRoute, go, api } from './lib.js';
import { useSynced, startSync, rejoin, wipeDevice } from './sync.js';
import { setLang, t } from './i18n.js';
import { defaultExpiry, RECIPE_BY_ID, applyCatalog, prepareRecipe } from '../shared/engine.mjs';
import { dayKey, normalizeLog, slotNow } from '../shared/planner.mjs';
import Home from './screens/Home.jsx';
import Pantry from './screens/Pantry.jsx';
import Recipe from './screens/Recipe.jsx';
import Cook from './screens/Cook.jsx';
import Bachao from './screens/Bachao.jsx';
import Family from './screens/Family.jsx';
import Shopping from './screens/Shopping.jsx';
import AiChef from './screens/AiChef.jsx';
import Plan from './screens/Plan.jsx';
import Track from './screens/Track.jsx';
import More from './screens/More.jsx';
import Ask from './screens/Ask.jsx';
import Account from './screens/Account.jsx';
import Login from './screens/Login.jsx';
import Vote from './screens/Vote.jsx';

const EMPTY_CATALOG = { recipes: [], hidden: [], ingredients: [], rescues: [], announcements: [], festivals: [] };

function cachedCatalog() {
  try {
    const c = { ...EMPTY_CATALOG, ...JSON.parse(localStorage.getItem('ballava.catalog') || '{}') };
    applyCatalog(c);
    return c;
  } catch { return EMPTY_CATALOG; }
}

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
  const [catalog, setCatalog] = useState(cachedCatalog);
  const [toast, setToast] = useState(null);
  const [aiStatus, setAiStatus] = useState({ checked: false, ai: false, server: false });
  const [auth, setAuth] = useState({ checked: false, user: null, household: null });
  const [guest, setGuest] = useState(isGuest);

  setLang(prefs.lang);

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

  const loadMe = useCallback(async ({ merge = false, rejoined = false } = {}) => {
    const me = await api('me');
    setAuth({ checked: true, user: me.user, household: me.household || null });
    if (!me.user) return;
    if (rejoined) await rejoin(signedOut);
    else await startSync({ merge, onLost: signedOut });
  }, [signedOut]);

  useEffect(() => {
    api('health').then(d => setAiStatus({ checked: true, ai: !!d.ai, server: true }))
      .catch(() => setAiStatus({ checked: true, ai: false, server: false }));
    loadMe().catch(() => {
      // No connection: if this device was signed in, keep working from what it has.
      let cached = null;
      try { cached = JSON.parse(localStorage.getItem('ballava._user') || 'null'); } catch { /* nothing stored */ }
      setAuth({ checked: true, user: cached, household: null });
      if (cached) startSync({ onLost: signedOut });
    });
    api('catalog').then(c => {
      applyCatalog(c);
      setCatalog(c);
      try { localStorage.setItem('ballava.catalog', JSON.stringify(c)); } catch { /* keep in memory */ }
    }).catch(() => {});
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

  const log = useMemo(() => normalizeLog(history), [history]);
  const extraRecipes = useMemo(() => catalog.recipes.map(r => prepareRecipe({ tags: [], ...r })), [catalog]);
  const extra = useMemo(() => ({ ...aiRecipes, ...Object.fromEntries(extraRecipes.map(r => [r.id, r])) }), [aiRecipes, extraRecipes]);
  const hidden = catalog.hidden;

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

  const findRecipe = id => extra[id] || RECIPE_BY_ID[id];

  const [screen, param] = route;
  if (screen === 'vote') return <Vote token={param} />;

  if (!auth.checked) return <div className="splash"><span className="brand-mark">B</span></div>;
  if (!auth.user && !guest) {
    return <Login onDone={() => loadMe({ merge: true })} onGuest={() => { try { localStorage.setItem('ballava.guest', '1'); } catch { /* ok */ } setGuest(true); }} server={aiStatus.server || !aiStatus.checked} />;
  }

  const ctx = {
    pantry, setPantry, addToPantry, members, setMembers, shopping, setShopping, addToShopping, history, setHistory, log, logMeal, ratings, aiRecipes, setAiRecipes,
    filters, setFilters, notify, aiStatus, findRecipe, plan, setPlan, pins, setPins, prefs, setPrefs, catalog, extraRecipes, extra, hidden, auth, loadMe, signedOut,
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
    case 'track': body = <Track {...ctx} />; break;
    case 'more': body = <More {...ctx} />; break;
    case 'ask': body = <Ask {...ctx} />; break;
    case 'account': body = <Account {...ctx} />; break;
    default: body = <Home {...ctx} />;
  }

  const tabs = [
    ['home', 'Cook', '🍳'], ['plan', 'Plan', '🗓️'], ['track', 'Track', '📊'], ['pantry', 'Kitchen', '🧺'], ['list', 'List', '🛒'], ['more', 'More', '☰'],
  ];
  const moreScreens = ['more', 'family', 'bachao', 'ask', 'account'];
  const active = id => (id === 'more' ? moreScreens.includes(screen) : screen === id || (id === 'home' && !['plan', 'track', 'pantry', 'list', ...moreScreens].includes(screen)));
  const hideNav = screen === 'cook';
  const listCount = shopping.filter(s => !s.done).length;

  return (
    <div className={'app' + (hideNav ? ' no-nav' : '')}>
      <main>{body}</main>
      {toast && <div className="toast" role="status">{toast}</div>}
      {!hideNav && (
        <nav className="tabbar" aria-label="Main">
          {tabs.map(([id, label, icon]) => (
            <button key={id} className={active(id) ? 'active' : ''} onClick={() => go(id)} aria-label={t(label)}>
              <span className="tab-icon" aria-hidden="true">{icon}</span>
              <span>{t(label)}</span>
              {id === 'list' && listCount > 0 && <span className="badge">{listCount}</span>}
            </button>
          ))}
        </nav>
      )}
    </div>
  );
}
