import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { useStored, useHashRoute, go, api } from './lib.js';
import { defaultExpiry } from '../shared/engine.mjs';
import Home from './screens/Home.jsx';
import Pantry from './screens/Pantry.jsx';
import Recipe from './screens/Recipe.jsx';
import Cook from './screens/Cook.jsx';
import Bachao from './screens/Bachao.jsx';
import Family from './screens/Family.jsx';
import Shopping from './screens/Shopping.jsx';
import AiChef from './screens/AiChef.jsx';
import { RECIPE_BY_ID } from '../shared/engine.mjs';

export default function App() {
  const route = useHashRoute();
  const [pantry, setPantry] = useStored('pantry', []);
  const [members, setMembers] = useStored('members', []);
  const [shopping, setShopping] = useStored('shopping', []);
  const [history, setHistory] = useStored('history', []);
  const [aiRecipes, setAiRecipes] = useStored('aiRecipes', {});
  const [filters, setFilters] = useStored('filters', {});
  const [toast, setToast] = useState(null);
  const [aiStatus, setAiStatus] = useState({ checked: false, ai: false, server: false });

  useEffect(() => {
    api('health').then(d => setAiStatus({ checked: true, ai: !!d.ai, server: true }))
      .catch(() => setAiStatus({ checked: true, ai: false, server: false }));
  }, []);

  const notify = useCallback((msg) => {
    setToast(msg);
    clearTimeout(window.__toastT);
    window.__toastT = setTimeout(() => setToast(null), 3500);
  }, []);

  // Latest rating per recipe: Ballava learns your "andaaz" (taste) from this.
  const ratings = useMemo(() => {
    const r = {};
    for (const h of history) if (h.rating) r[h.recipeId] = h.rating;
    return r;
  }, [history]);

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

  const findRecipe = id => RECIPE_BY_ID[id] || aiRecipes[id];

  const ctx = {
    pantry, setPantry, addToPantry, members, setMembers, shopping, setShopping, addToShopping,
    history, setHistory, ratings, aiRecipes, setAiRecipes, filters, setFilters, notify, aiStatus, findRecipe,
  };

  const [screen, param] = route;
  let body;
  switch (screen) {
    case 'pantry': body = <Pantry {...ctx} />; break;
    case 'recipe': body = <Recipe {...ctx} recipe={findRecipe(param)} />; break;
    case 'cook': body = <Cook {...ctx} recipe={findRecipe(param)} />; break;
    case 'bachao': body = <Bachao {...ctx} />; break;
    case 'family': body = <Family {...ctx} />; break;
    case 'list': body = <Shopping {...ctx} />; break;
    case 'ai': body = <AiChef {...ctx} />; break;
    default: body = <Home {...ctx} />;
  }

  const tabs = [
    ['home', 'Cook', '🍳'], ['pantry', 'Kitchen', '🧺'], ['bachao', 'Bachao', '🛟'], ['list', 'List', '🛒'], ['family', 'Family', '👪'],
  ];
  const hideNav = screen === 'cook';
  const listCount = shopping.filter(s => !s.done).length;

  return (
    <div className={'app' + (hideNav ? ' no-nav' : '')}>
      <main>{body}</main>
      {toast && <div className="toast" role="status">{toast}</div>}
      {!hideNav && (
        <nav className="tabbar" aria-label="Main">
          {tabs.map(([id, label, icon]) => (
            <button key={id} className={(screen === id || (id === 'home' && !['pantry', 'bachao', 'list', 'family'].includes(screen))) ? 'active' : ''}
              onClick={() => go(id)} aria-label={label}>
              <span className="tab-icon" aria-hidden="true">{icon}</span>
              <span>{label}</span>
              {id === 'list' && listCount > 0 && <span className="badge">{listCount}</span>}
            </button>
          ))}
        </nav>
      )}
    </div>
  );
}
