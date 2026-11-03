import React, { useMemo } from 'react';
import { suggest, buyTips, useSoon, daysLeft, defaultExpiry } from '../../shared/engine.mjs';
import { go } from '../lib.js';
import { DietDot, ingName, expiryLabel } from '../ui.jsx';

const FILTERS = [
  ['veg', 'Veg only'], ['quick', 'Under 20 min'], ['leftover', 'Leftover magic'], ['healthy', 'Diabetic-friendly'], ['vrat', 'Vrat / fasting'],
];

const DEMO = ['rice', 'toor_dal', 'onion', 'tomato', 'potato', 'green_chilli', 'curd', 'leftover_rice', 'egg', 'poha', 'lemon', 'coriander',
  'turmeric', 'red_chilli_powder', 'cumin', 'mustard_seeds', 'garam_masala', 'coriander_powder', 'peanuts', 'atta'];

function greeting() {
  const h = new Date().getHours();
  if (h < 11) return 'Good morning! Breakfast time?';
  if (h < 16) return 'Lunch plans?';
  if (h < 19) return 'Chai-time snack?';
  return 'What\'s for dinner tonight?';
}

export function DishCard({ r }) {
  const { recipe } = r;
  const status = r.majorMissing.length === 0
    ? (r.spiceMissing.length ? `Have main items · check ${r.spiceMissing.map(o => ingName(o[0])).join(', ')}` : 'You have everything')
    : `Need ${r.majorMissing.map(o => ingName(o[0])).join(', ')}`;
  return (
    <button className="dish-card" onClick={() => go('recipe/' + recipe.id)}>
      <div className="dish-ring" style={{ '--p': Math.round(r.coverage * 100) }} aria-hidden="true">
        <span>{Math.round(r.coverage * 100)}%</span>
      </div>
      <div className="dish-info">
        <div className="dish-title"><DietDot diet={recipe.diet} /> {recipe.name}</div>
        {recipe.alt && <div className="dish-alt">{recipe.alt}</div>}
        <div className="dish-meta">{recipe.time} min · {recipe.cuisine}</div>
        <div className={'dish-status ' + (r.majorMissing.length ? 'need' : 'have')}>{status}</div>
        {r.usesSoon.length > 0 && <div className="pill warn">Uses up {r.usesSoon.map(ingName).join(', ')}</div>}
        {r.notes.length > 0 && <div className="pill info">{r.notes[0]}</div>}
      </div>
    </button>
  );
}

export default function Home({ pantry, addToPantry, members, filters, setFilters, ratings, history, aiRecipes, aiStatus, notify }) {
  const params = { pantry, members, filters, ratings };
  const { ready, almost } = useMemo(() => suggest(params), [pantry, members, filters, ratings]);
  const tips = useMemo(() => buyTips(params), [pantry, members, filters, ratings]);
  const soon = useSoon(pantry);
  const saved = history.reduce((n, h) => n + (h.saved?.length || 0), 0);

  if (!pantry.length) {
    return (
      <div className="screen">
        <section className="hero">
          <div className="hero-brand">Ballava</div>
          <p className="hero-tag">Cooks with you today. For you tomorrow.</p>
          <p>Tell me what's in your kitchen and I'll tell you what to cook, then guide you step by step.</p>
          <button className="btn primary big" onClick={() => go('pantry')}>Add what I have</button>
          <button className="btn ghost" onClick={() => { addToPantry(DEMO); notify('Loaded a sample Indian kitchen. Edit it anytime in Kitchen.'); }}>Try with a sample kitchen</button>
        </section>
        <section className="card how">
          <h3>How it works</h3>
          <ol>
            <li><b>Kitchen:</b> type or say what you have, in English, Hindi, Telugu or Tamil words.</li>
            <li><b>Cook:</b> get dishes ranked by what you already have and what's about to spoil.</li>
            <li><b>Cook mode:</b> big steps, timers, whistle counter and read-aloud.</li>
            <li><b>Bachao:</b> too salty? Burnt? Get a fix in seconds.</li>
          </ol>
        </section>
      </div>
    );
  }

  return (
    <div className="screen">
      <header className="home-head">
        <div>
          <div className="hero-brand small">Ballava</div>
          <h2>{greeting()}</h2>
        </div>
        <button className="btn ghost sm" onClick={() => go('ai')}>✨ AI Chef</button>
      </header>

      <div className="stats">
        <div><b>{history.length}</b><span>meals cooked</span></div>
        <div><b>{saved}</b><span>items saved from waste</span></div>
        <div><b>{pantry.length}</b><span>in your kitchen</span></div>
      </div>

      {soon.length > 0 && (
        <button className="soon-banner" onClick={() => go('pantry')}>
          <b>Use soon:</b> {soon.slice(0, 4).map(p => `${ingName(p.id)} (${expiryLabel(daysLeft(p)).text.toLowerCase()})`).join(', ')}
        </button>
      )}

      <div className="chips scroll" role="group" aria-label="Filters">
        {FILTERS.map(([k, label]) => (
          <button key={k} className={'chip' + (filters[k] ? ' on' : '')} aria-pressed={!!filters[k]}
            onClick={() => setFilters({ ...filters, [k]: !filters[k] })}>{label}</button>
        ))}
      </div>
      {members.length > 0 && <p className="muted small">Showing dishes that suit everyone in your family ({members.map(m => m.name).join(', ')}).</p>}

      <h3 className="section-title">Cook now <span className="count">{ready.length}</span></h3>
      {ready.length === 0 && <p className="muted">Nothing complete yet. Check "Almost there" below, or add more to your kitchen.</p>}
      <div className="dish-list">{ready.slice(0, 12).map(r => <DishCard key={r.recipe.id} r={r} />)}</div>

      {tips.length > 0 && (
        <div className="card tip-card">
          <h3>Buy just one thing</h3>
          {tips.map(t => (
            <p key={t.id}><b>{t.name}</b> unlocks {t.dishes.length} more dish{t.dishes.length > 1 ? 'es' : ''}: {t.dishes.slice(0, 3).join(', ')}</p>
          ))}
        </div>
      )}

      <h3 className="section-title">Almost there <span className="count">{almost.length}</span></h3>
      <div className="dish-list">{almost.slice(0, 10).map(r => <DishCard key={r.recipe.id} r={r} />)}</div>

      {Object.keys(aiRecipes).length > 0 && (
        <>
          <h3 className="section-title">Your AI creations</h3>
          <div className="dish-list">
            {Object.values(aiRecipes).map(rec => (
              <button key={rec.id} className="dish-card slim" onClick={() => go('recipe/' + rec.id)}>
                <div className="dish-info"><div className="dish-title"><DietDot diet={rec.diet} /> {rec.name}</div><div className="dish-meta">{rec.time} min · AI original</div></div>
              </button>
            ))}
          </div>
        </>
      )}
      {!aiStatus.ai && aiStatus.checked && <p className="muted small center">Want brand-new dishes and fridge-photo scanning? See ✨ AI Chef.</p>}
    </div>
  );
}

export { DEMO, defaultExpiry };
