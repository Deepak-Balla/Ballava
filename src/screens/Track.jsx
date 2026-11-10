import React, { useMemo, useState } from 'react';
import { getCatalog, dayKey, addDays, slotNow, SLOTS, SLOT_LABEL, WEEKDAYS } from '../catalog.js';
import { Header, Empty, Thinking } from '../ui.jsx';
import { go, listenOnce, SpeechRec, useBrain } from '../lib.js';
import { t } from '../i18n.js';

const GROUPS = [['greens', 'Leafy greens', '🥬'], ['vegetables', 'Vegetables', '🥕'], ['protein', 'Protein', '🫘'], ['wholegrain', 'Whole grains', '🌾'], ['fruit', 'Fruit', '🍌']];

function QuickLog({ recipes, plan, logMeal, notify, log }) {
  const today = dayKey();
  const [date, setDate] = useState(today);
  const [slot, setSlot] = useState(slotNow());
  const [text, setText] = useState('');
  const [listening, setListening] = useState(false);

  function save(name, recipe) {
    logMeal({ recipeId: recipe?.id || null, name: recipe?.name || name, date, slot });
    notify(`Logged ${recipe?.name || name}`);
    setText('');
  }

  function submit(e) {
    e.preventDefault();
    const name = text.trim();
    if (!name) { notify('Type what you made'); return; }
    const low = name.toLowerCase();
    save(name, recipes.find(r => r.name.toLowerCase() === low || r.alt?.toLowerCase().split(' / ').includes(low)));
  }

  const planned = plan[date]?.[slot] && recipes.find(r => r.id === plan[date][slot]);
  const logged = log.some(e => e.date === date && e.slot === slot);
  return (
    <form className="card form" onSubmit={submit}>
      <h3>{t('What did you make today?')}</h3>
      <div className="chips wrap" role="group" aria-label="Meal">
        {SLOTS.map(s => <button type="button" key={s} className={'chip' + (slot === s ? ' on' : '')} aria-pressed={slot === s} onClick={() => setSlot(s)}>{t(SLOT_LABEL[s])}</button>)}
      </div>
      <div className="chips wrap" role="group" aria-label="Day">
        {[[today, 'Today'], [addDays(today, -1), 'Yesterday']].map(([d, label]) => <button type="button" key={d} className={'chip' + (date === d ? ' on' : '')} aria-pressed={date === d} onClick={() => setDate(d)}>{label}</button>)}
      </div>
      {planned && !logged && <button type="button" className="btn ghost" onClick={() => save(planned.name, planned)}>✓ Made {planned.name}, as planned</button>}
      <div className="row nowrap">
        <input aria-label="Dish name" list="dish-names" value={text} onChange={e => setText(e.target.value)} placeholder="e.g. Dal Tadka, or Pizza from outside" />
        {SpeechRec && <button type="button" className={'icon-btn mic' + (listening ? ' live' : '')} aria-label="Say the dish name" onClick={() => { setListening(true); listenOnce(setText, () => setListening(false)); }}>🎤</button>}
        <button className="btn primary" type="submit">{t('Log a meal').split(' ')[0]}</button>
      </div>
      <datalist id="dish-names">{recipes.map(r => <option key={r.id} value={r.name} />)}</datalist>
    </form>
  );
}

const EMPTY = { total: 0, weekCount: 0, variety: null, groups: {}, insights: [], byDay: {}, top: [], saved: 0 };

export default function Track({ history, setHistory, log, logMeal, plan, aiRecipes, catalog, notify }) {
  const [offset, setOffset] = useState(0);
  const recipes = useMemo(() => {
    const hidden = new Set(catalog.hidden);
    return [...getCatalog().recipes.filter(r => !hidden.has(r.id)), ...Object.values(aiRecipes)];
  }, [catalog, aiRecipes]);
  // Python (kitchen/planner.py -> dashboard) studies the diary: food groups, repeats, forgotten favourites.
  const brain = useBrain('dashboard', { history, aiRecipes });
  const d = brain.data ? { ...EMPTY, ...brain.data } : EMPTY;
  const today = dayKey();
  const weekEnd = addDays(today, -offset * 7);
  const week = Array.from({ length: 7 }, (_, i) => addDays(weekEnd, -i));
  const most = Math.max(1, ...Object.values(d.groups));
  const group = id => d.groups[id] || 0;

  const removeEntry = entry => setHistory(h => h.filter(x => (x.id ? x.id !== entry.id : !(x.at === entry.at && x.name === entry.name))));

  return (
    <div className="screen">
      <Header title={t('Food diary')} />
      <QuickLog recipes={recipes} plan={plan} logMeal={logMeal} notify={notify} log={log} />

      <Thinking state={brain}>Looking at your week…</Thinking>
      <div className="stats">
        <div><b>{d.weekCount}</b><span>meals in 7 days</span></div>
        <div><b>{d.variety === null ? '–' : d.variety + '%'}</b><span>variety</span></div>
        <div><b>{d.saved}</b><span>items saved from waste</span></div>
      </div>

      {d.insights.length > 0 && (
        <section className="insights" aria-label="Insights">
          {d.insights.slice(0, 4).map(i => (
            i.recipeId
              ? <button key={i.text} className={'insight ' + i.kind} onClick={() => go('recipe/' + i.recipeId)}>{i.text}</button>
              : <div key={i.text} className={'insight ' + i.kind}>{i.text}</div>
          ))}
        </section>
      )}

      {d.total > 0 && (
        <div className="card">
          <h3>{t('This week')}: what's on the table</h3>
          {GROUPS.map(([id, label, icon]) => (
            <div key={id} className="bar-row">
              <span className="bar-label">{icon} {label}</span>
              <span className="bar"><span style={{ width: `${(group(id) / most) * 100}%` }} /></span>
              <b className="bar-count">{group(id)}</b>
            </div>
          ))}
          <p className="muted small">Counted from the dishes you logged. This is a rough guide, not a nutrition report.</p>
        </div>
      )}

      <div className="row between week-nav">
        <button className="btn link" onClick={() => setOffset(offset + 1)}>‹ Earlier</button>
        <b>{offset === 0 ? 'Last 7 days' : `${week[6].slice(5)} to ${week[0].slice(5)}`}</b>
        <button className="btn link" disabled={offset === 0} onClick={() => setOffset(offset - 1)}>Later ›</button>
      </div>
      {d.total === 0 && <Empty title="Nothing logged yet">Log what you make, and Ballava stops repeating it and spots what's missing.</Empty>}
      {d.total > 0 && (
        <div className="diary">
          {week.map(date => {
            const items = (d.byDay[date] || []).slice().sort((a, b) => SLOTS.indexOf(a.slot) - SLOTS.indexOf(b.slot));
            const label = date === today ? 'Today' : WEEKDAYS[new Date(date + 'T12:00:00').getDay()] + ' ' + date.slice(8);
            return (
              <div key={date} className="diary-day">
                <span className="diary-date">{label}</span>
                <div className="diary-items">
                  {items.length === 0 && <span className="muted small">Nothing logged</span>}
                  {items.map(e => (
                    <span key={e.id || e.at + e.name} className="diary-item">
                      <span className="muted small">{t(SLOT_LABEL[e.slot] || e.slot)}:</span> {e.name}
                      <button className="x" onClick={() => removeEntry(e)} aria-label={`Remove ${e.name}`}>✕</button>
                    </span>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {d.top.length > 0 && (
        <div className="card">
          <h3>Family favourites</h3>
          {d.top.map(r => <div key={r.id || r.name} className="row between"><span>{r.name}</span><span className="muted small">{r.count} time{r.count > 1 ? 's' : ''}{r.rating ? ` · ${'★'.repeat(r.rating)}` : ''}</span></div>)}
        </div>
      )}
    </div>
  );
}
