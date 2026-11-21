import React, { useState } from 'react';
import { getCatalog, WEEKDAYS } from '../catalog.js';
import { Header, DietDot, Spice, Stars, Empty, ingName, SaveButton, NutritionCard } from '../ui.jsx';
import { go, whatsappLink, useBrain } from '../lib.js';
import { t } from '../i18n.js';

export default function Recipe({ recipe, pantry, addToShopping, notify, ratings, pins, setPins, family, isSaved, toggleSave, openAssistant }) {
  const [weekday, setWeekday] = useState(0);
  // Python (kitchen/api.py -> recipe_info): can the family eat it, portion tips, and when it was last made.
  const info = useBrain('recipe', { ...family, recipeId: recipe?.id }, !!recipe);
  if (!recipe) return <div className="screen"><Header title="Recipe" back /><Empty title="Recipe not found">It may have been removed. <a href="#/home">Go home</a></Empty></div>;
  const have = new Set([...pantry.map(p => p.id), ...getCatalog().assumed]);
  const missing = recipe.ingredients.filter(it => !it.optional && !it.options.some(id => have.has(id)));
  const house = info.data?.house || { ok: true, notes: [] };
  const plates = info.data?.plates || [];
  const lastMade = info.data?.lastDays ?? null;
  const shareText = info.data?.shareText || recipe.name + ' (' + recipe.time + ' min)';

  return (
    <div className="screen recipe">
      <Header title="" back right={(
        <div className="row nowrap">
          <SaveButton recipe={recipe} isSaved={isSaved} toggleSave={toggleSave} className="big" />
          <a className="icon-btn" href={whatsappLink(shareText)} target="_blank" rel="noreferrer" aria-label="Share on WhatsApp">⤴</a>
        </div>
      )} />
      <div className="recipe-cols">
      <div className="recipe-left">
      <h2 className="recipe-title"><DietDot diet={recipe.diet} /> {recipe.name}</h2>
      {recipe.alt && <p className="dish-alt">{recipe.alt}</p>}
      <div className="meta-row">
        <span>⏱ {recipe.time} min</span><span>🍽 Serves {recipe.serves}</span><Spice level={recipe.spice} /><span>{recipe.cuisine}</span>
      </div>
      <div className="tags">{recipe.tags.map(t => <span key={t} className="tag">{t.replace('-', ' ')}</span>)}</div>
      {ratings[recipe.id] && <div className="your-rating">Your rating <Stars value={ratings[recipe.id]} size="sm" /></div>}

      <NutritionCard n={recipe.nutrition} />
      <button className="ask-bar" onClick={openAssistant}>
        <span aria-hidden="true">🧑‍🍳</span> <span>Ask Chef about this dish: calories, swaps, a kid-friendly version…</span>
      </button>

      {!house.ok && <div className="note bad">{house.reason}</div>}
      {house.ok && house.notes.map(n => <div key={n} className="note info">{n}</div>)}
      {lastMade !== null && <div className="note warn">{lastMade === 0 ? 'You already made this today.' : `You made this ${lastMade} day${lastMade > 1 ? 's' : ''} ago.`}</div>}
      {plates.length > 0 && (
        <div className="card plates">
          <h3>🍽 {t('One meal, many plates')}</h3>
          {plates.map(p => <p key={p.who}><b>{p.who}:</b> {p.tips.join(' ')}</p>)}
        </div>
      )}
      {recipe.prep && <div className="note warn"><b>Plan ahead:</b> {recipe.prep}</div>}
      {recipe.safety && <div className="note bad"><b>Food safety:</b> {recipe.safety}</div>}
      {recipe.tip && <div className="note info"><b>Tip:</b> {recipe.tip}</div>}
      </div>

      <div className="recipe-right">
      <h3 className="section-title">Ingredients</h3>
      <ul className="ing-list">
        {recipe.ingredients.map((it, i) => {
          const ok = it.options.some(id => have.has(id));
          const label = it.custom || it.options.map(ingName).join(' or ');
          const kcal = recipe.nutrition?.lines?.[i]?.kcal;
          return (
            <li key={i} className={ok ? 'have' : it.optional ? 'opt' : 'miss'}>
              <span className="mark" aria-hidden="true">{ok ? '✓' : it.optional ? '·' : '✕'}</span>
              <span className="ing-label">{label}{it.optional && <em> (optional)</em>}</span>
              <span className="qty">{it.qty}{kcal >= 1 && <span className="line-kcal">≈ {kcal} kcal</span>}</span>
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

      <div className="row pin-row">
        <span className="muted small">Family tradition?</span>
        <select aria-label="Day of the week" value={weekday} onChange={e => setWeekday(Number(e.target.value))}>
          {WEEKDAYS.map((d, i) => <option key={d} value={i}>Every {d}</option>)}
        </select>
        <button className="btn sm" onClick={() => {
          if (!pins.some(p => p.recipeId === recipe.id && p.weekday === weekday)) setPins([...pins, { recipeId: recipe.id, weekday, slot: recipe.meal.includes('lunch') ? 'lunch' : recipe.meal[0] }]);
          notify(`${recipe.name} is now your ${WEEKDAYS[weekday]} favourite`);
        }}>⭐ Pin</button>
      </div>
      </div>
      </div>

      <div className="sticky-cta">
        <button className="btn primary big" onClick={() => go('cook/' + recipe.id)}>{t('Start cooking')}</button>
      </div>
    </div>
  );
}
