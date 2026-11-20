import React, { useMemo, useState } from 'react';
import { getCatalog, dayKey } from '../catalog.js';
import { Header, Empty, DietDot, SaveButton, kcalOf } from '../ui.jsx';
import { go } from '../lib.js';

const FILTERS = [['all', 'All'], ['breakfast', 'Breakfast'], ['main', 'Lunch & dinner'], ['snack', 'Snacks'], ['quick', 'Under 20 min'], ['light', 'Light (≤400 kcal)']];
const SORTS = [['recent', 'Recently saved'], ['forgotten', 'Not made lately'], ['quick', 'Quickest'], ['light', 'Fewest calories']];

const daysSince = (date, today) => Math.round((new Date(today + 'T12:00:00') - new Date(date + 'T12:00:00')) / 86400000);

// What's missing from the kitchen for a dish (main items only; salt, oil and water are assumed).
export function missingFor(recipe, pantry) {
  const have = new Set([...pantry.map(p => p.id), ...getCatalog().assumed]);
  return recipe.ingredients.filter(it => !it.optional && !it.options.some(id => have.has(id)));
}

export default function Saved({ savedDishes, isSaved, toggleSave, findRecipe, log, pantry }) {
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState('all');
  const [sort, setSort] = useState('recent');
  const today = dayKey();

  const lastMade = useMemo(() => {
    const out = {};
    for (const e of log) if (e.recipeId && (!out[e.recipeId] || e.date > out[e.recipeId])) out[e.recipeId] = e.date;
    return out;
  }, [log]);

  const rows = savedDishes.map(s => ({ ...s, recipe: findRecipe(s.id) })).filter(s => s.recipe).filter(({ recipe: r }) => {
    const text = `${r.name} ${r.alt || ''} ${r.cuisine || ''}`.toLowerCase();
    if (q && !text.includes(q.toLowerCase())) return false;
    if (filter === 'breakfast') return r.meal.includes('breakfast');
    if (filter === 'main') return r.meal.includes('lunch') || r.meal.includes('dinner');
    if (filter === 'snack') return r.meal.includes('snack');
    if (filter === 'quick') return r.time <= 20;
    if (filter === 'light') return (kcalOf(r) ?? 999) <= 400;
    return true;
  });
  const since = id => (lastMade[id] ? daysSince(lastMade[id], today) : 9999);
  rows.sort((a, b) => (sort === 'forgotten' ? since(b.id) - since(a.id)
    : sort === 'quick' ? a.recipe.time - b.recipe.time
      : sort === 'light' ? (kcalOf(a.recipe) ?? 999) - (kcalOf(b.recipe) ?? 999)
        : (b.at || 0) - (a.at || 0)));

  return (
    <div className="screen">
      <Header title="Saved dishes" back="more" />
      {savedDishes.length === 0 ? (
        <Empty title="Nothing saved yet">Tap the ♡ on any dish to keep it here. Saved dishes come up a little more often in your plans.</Empty>
      ) : (
        <>
          <input className="search" type="search" aria-label="Search saved dishes" placeholder={`Search ${savedDishes.length} saved dishes`} value={q} onChange={e => setQ(e.target.value)} />
          <div className="chips scroll" role="group" aria-label="Show">
            {FILTERS.map(([id, label]) => <button key={id} className={'chip' + (filter === id ? ' on' : '')} aria-pressed={filter === id} onClick={() => setFilter(id)}>{label}</button>)}
          </div>
          <div className="row sort-row">
            <label className="muted small" htmlFor="saved-sort">Sort</label>
            <select id="saved-sort" value={sort} onChange={e => setSort(e.target.value)}>{SORTS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select>
          </div>
          {rows.length === 0 && <p className="muted">No saved dishes match. Try another filter.</p>}
          <div className="dish-list">
            {rows.map(({ id, recipe: r }) => {
              const miss = missingFor(r, pantry);
              const days = lastMade[id] ? daysSince(lastMade[id], today) : null;
              return (
                <div key={id} className="dish-wrap">
                  <button className="dish-card" onClick={() => go('recipe/' + id)}>
                    <div className="dish-info">
                      <div className="dish-title"><DietDot diet={r.diet} /> {r.name}</div>
                      {r.alt && <div className="dish-alt">{r.alt}</div>}
                      <div className="dish-meta">{r.time} min{kcalOf(r) != null ? ` · ${kcalOf(r)} kcal` : ''} · {r.ai ? 'AI original' : r.cuisine}</div>
                      <div className={'dish-status ' + (miss.length ? 'need' : 'have')}>{miss.length ? `Need ${miss.length} item${miss.length > 1 ? 's' : ''}` : 'You can cook this now'}</div>
                      <div className="pill">{days === null ? 'Not made yet' : days === 0 ? 'Made today' : `Made ${days} day${days > 1 ? 's' : ''} ago`}</div>
                    </div>
                  </button>
                  <SaveButton recipe={r} isSaved={isSaved} toggleSave={toggleSave} className="corner" />
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
