import React from 'react';
import { ASSUMED } from '../../shared/ingredients.mjs';
import { householdCheck, recipeText } from '../../shared/engine.mjs';
import { Header, DietDot, Spice, Stars, Empty, ingName } from '../ui.jsx';
import { go, whatsappLink } from '../lib.js';

export default function Recipe({ recipe, pantry, members, addToShopping, notify, ratings }) {
  if (!recipe) return <div className="screen"><Header title="Recipe" back /><Empty title="Recipe not found">It may have been removed. <a href="#/home">Go home</a></Empty></div>;
  const have = new Set([...pantry.map(p => p.id), ...ASSUMED]);
  const house = householdCheck(recipe, members);
  const missing = recipe.ingredients.filter(it => !it.optional && !it.options.some(id => have.has(id)));

  return (
    <div className="screen recipe">
      <Header title="" back right={<a className="icon-btn" href={whatsappLink(recipeText(recipe))} target="_blank" rel="noreferrer" aria-label="Share on WhatsApp">⤴</a>} />
      <h2 className="recipe-title"><DietDot diet={recipe.diet} /> {recipe.name}</h2>
      {recipe.alt && <p className="dish-alt">{recipe.alt}</p>}
      <div className="meta-row">
        <span>⏱ {recipe.time} min</span><span>🍽 Serves {recipe.serves}</span><Spice level={recipe.spice} /><span>{recipe.cuisine}</span>
      </div>
      <div className="tags">{recipe.tags.map(t => <span key={t} className="tag">{t.replace('-', ' ')}</span>)}</div>
      {ratings[recipe.id] && <div className="your-rating">Your rating <Stars value={ratings[recipe.id]} size="sm" /></div>}

      {!house.ok && <div className="note bad">{house.reason}</div>}
      {house.ok && house.notes.map(n => <div key={n} className="note info">{n}</div>)}
      {recipe.prep && <div className="note warn"><b>Plan ahead:</b> {recipe.prep}</div>}
      {recipe.safety && <div className="note bad"><b>Food safety:</b> {recipe.safety}</div>}
      {recipe.tip && <div className="note info"><b>Tip:</b> {recipe.tip}</div>}

      <h3 className="section-title">Ingredients</h3>
      <ul className="ing-list">
        {recipe.ingredients.map((it, i) => {
          const ok = it.options.some(id => have.has(id));
          const label = it.custom || it.options.map(ingName).join(' or ');
          return (
            <li key={i} className={ok ? 'have' : it.optional ? 'opt' : 'miss'}>
              <span className="mark" aria-hidden="true">{ok ? '✓' : it.optional ? '·' : '✕'}</span>
              <span className="ing-label">{label}{it.optional && <em> (optional)</em>}</span>
              <span className="qty">{it.qty}</span>
            </li>
          );
        })}
      </ul>
      {missing.length > 0 && (
        <button className="btn ghost" onClick={() => { addToShopping(missing.map(it => it.options[0])); notify(`Added ${missing.length} item(s) to your shopping list`); }}>
          + Add {missing.length} missing to shopping list
        </button>
      )}

      <h3 className="section-title">Steps</h3>
      <ol className="step-list">
        {recipe.steps.map((s, i) => (
          <li key={i}>{s.text}{s.minutes && <span className="pill">⏱ {s.minutes} min</span>}{s.whistles && <span className="pill">{s.whistles} whistles</span>}</li>
        ))}
      </ol>

      <div className="sticky-cta">
        <button className="btn primary big" onClick={() => go('cook/' + recipe.id)}>Start cooking</button>
      </div>
    </div>
  );
}
