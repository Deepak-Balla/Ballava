// The family dashboard: calories, nutrients and every meal with its calories (Overview), and the food diary.
// Python works the numbers out (kitchen/planner.py -> calorie_dashboard). Calories are one serving of each logged
// meal, so they're a rough guide per person, not a medical report.
import React, { useState } from 'react';
import { WEEKDAYS, SLOTS, SLOT_LABEL, dayKey } from '../catalog.js';
import { Header, Thinking } from '../ui.jsx';
import { api, go, useBrain, whatsappLink } from '../lib.js';
import { t } from '../i18n.js';
import Track from './Track.jsx';

const DEFAULT_GOAL = 1800;
const PERIODS = [[7, '7 days'], [14, '14 days'], [30, '30 days']];
const dayLabel = (date, today) => (date === today ? 'Today' : `${WEEKDAYS[new Date(date + 'T12:00:00').getDay()]} ${Number(date.slice(8))}`);
const fmt = n => (n == null ? '–' : Math.round(n).toLocaleString('en-IN'));

function GoalRing({ kcal, goal }) {
  const pct = Math.min(100, Math.round((kcal / goal) * 100));
  const over = kcal > goal;
  return (
    <div className={'goal-ring' + (over ? ' over' : '')} style={{ '--p': pct }} role="img" aria-label={`${kcal} of ${goal} kcal today`}>
      <div><b>{fmt(kcal)}</b><span>of {fmt(goal)} kcal</span></div>
    </div>
  );
}

function MealKcal({ meal, ai, setHistory, notify }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const save = nutrition => setHistory(h => h.map(x => (x.id && x.id === meal.id ? { ...x, nutrition } : x)));
  if (meal.kcal != null) return <span className="kcal-cell">{fmt(meal.kcal)}{meal.source === 'ai' ? <small title="Estimated by AI"> ✨</small> : meal.source === 'manual' ? <small title="Typed by you"> ✎</small> : null}</span>;
  if (!meal.id) return <span className="muted small">–</span>;
  if (editing) {
    return (
      <form className="kcal-edit" onSubmit={e => { e.preventDefault(); const n = Number(value); if (n > 0 && n < 5000) { save({ kcal: n, source: 'manual' }); notify(`Saved ${n} kcal for ${meal.name}`); } setEditing(false); }}>
        <input type="number" inputMode="numeric" min="1" max="4999" aria-label={`Calories for ${meal.name}`} value={value} onChange={e => setValue(e.target.value)} autoFocus />
        <button className="btn sm primary" type="submit">OK</button>
      </form>
    );
  }
  return (
    <span className="kcal-actions">
      <button className="btn link sm" onClick={() => setEditing(true)}>Add kcal</button>
      {ai && (
        <button className="btn link sm" disabled={busy} aria-label={`Estimate calories for ${meal.name} with AI`} onClick={async () => {
          setBusy(true);
          try { const n = await api('ai/estimate', { name: meal.name }); save(n); notify(`About ${n.kcal} kcal for ${meal.name} (AI estimate)`); } catch (e) { notify(e.message); }
          setBusy(false);
        }}>{busy ? '…' : '✨ Estimate'}</button>
      )}
    </span>
  );
}

function Overview({ history, setHistory, aiRecipes, plan, members, prefs, setPrefs, savedDishes, pantry, notify, aiStatus }) {
  const [days, setDays] = useState(7);
  const [editGoal, setEditGoal] = useState(false);
  const goal = Number(prefs.kcalGoal) || DEFAULT_GOAL;
  const brain = useBrain('calories', { history, aiRecipes, plan, members, savedDishes, days });
  const d = brain.data;
  const today = dayKey();
  if (!d) return <Thinking state={brain}>Adding up your calories…</Thinking>;

  const top = Math.max(goal, ...d.days.map(x => x.kcal), 1);
  const s = d.macros.split;
  const donut = `conic-gradient(var(--green) 0 ${s.protein}%, #e0a100 ${s.protein}% ${s.protein + s.carbs}%, var(--accent) ${s.protein + s.carbs}% 100%)`;
  const slotMax = Math.max(1, ...Object.values(d.bySlot));
  const left = goal - d.today.kcal;
  const report = [`Ballava dashboard (${days} days)`, `Average: ${fmt(d.avgKcal)} kcal a day per person, protein ${fmt(d.avgProtein)} g`,
    `Today: ${fmt(d.today.kcal)} of ${fmt(goal)} kcal`, ...d.dishes.slice(0, 3).map(x => `- ${x.name}: ${x.times}x, ${fmt(x.kcal)} kcal a serving`)].join('\n');

  return (
    <>
      <Thinking state={brain} />
      <section className="card today-kcal">
        <GoalRing kcal={d.today.kcal} goal={goal} />
        <div className="today-kcal-text">
          <h3>Today</h3>
          <p className={left < 0 ? 'bad-text' : 'muted'}>{d.today.counted === 0 ? 'Nothing with calories logged yet today.' : left >= 0 ? `${fmt(left)} kcal left of your goal` : `${fmt(-left)} kcal over your goal`}</p>
          <p className="muted small">Protein {fmt(d.today.protein)} g · Carbs {fmt(d.today.carbs)} g · Fat {fmt(d.today.fat)} g</p>
          {d.planned.today && <p className="small">📅 Planned today: <b>{fmt(d.planned.today.kcal)} kcal</b> ({d.planned.today.meals} meal{d.planned.today.meals > 1 ? 's' : ''})</p>}
          {d.planned.tomorrow && <p className="small">📅 Planned tomorrow: <b>{fmt(d.planned.tomorrow.kcal)} kcal</b></p>}
          {editGoal ? (
            <form className="row nowrap goal-form" onSubmit={e => { e.preventDefault(); const v = Number(new FormData(e.target).get('goal')); if (v >= 800 && v <= 5000) setPrefs(p => ({ ...p, kcalGoal: v })); setEditGoal(false); }}>
              <input name="goal" type="number" min="800" max="5000" step="50" defaultValue={goal} aria-label="Daily calorie goal per person" autoFocus />
              <button className="btn sm primary" type="submit">Save</button>
            </form>
          ) : <button className="btn link sm" onClick={() => setEditGoal(true)}>Daily goal: {fmt(goal)} kcal per person · change</button>}
        </div>
      </section>

      <div className="chips" role="group" aria-label="Period">
        {PERIODS.map(([n, label]) => <button key={n} className={'chip' + (days === n ? ' on' : '')} aria-pressed={days === n} onClick={() => setDays(n)}>{label}</button>)}
      </div>

      <div className="dash-stats">
        <div><span aria-hidden="true">🔥</span><b>{fmt(d.avgKcal)}</b><small>avg kcal a day</small></div>
        <div><span aria-hidden="true">💪</span><b>{d.avgProtein == null ? '–' : `${fmt(d.avgProtein)} g`}</b><small>avg protein a day</small></div>
        <div><span aria-hidden="true">🍽</span><b>{d.meals.length}</b><small>meals logged</small></div>
        <div><span aria-hidden="true">📆</span><b>{d.daysLogged}/{days}</b><small>days logged</small></div>
        <div><span aria-hidden="true">❤️</span><b>{savedDishes.length}</b><small>saved dishes</small></div>
        <div><span aria-hidden="true">🧺</span><b>{pantry.length}</b><small>in your kitchen</small></div>
      </div>

      <section className="card">
        <div className="row between"><h3>🔥 Calories per day</h3><span className="muted small">goal line {fmt(goal)}</span></div>
        <div className={'kcal-bars' + (days > 14 ? ' many' : '')} style={{ '--cols': d.days.length }} role="img"
          aria-label={`Calories per day: ${d.days.map(x => `${x.date.slice(5)} ${x.kcal}`).join(', ')}`}>
          {d.days.map(x => (
            <div key={x.date} className={'kcal-col' + (x.kcal > goal ? ' over' : '')}>
              <span className="kcal-val">{x.kcal && days <= 14 ? fmt(x.kcal) : ''}</span>
              <span className="kcal-bar"><span style={{ height: `${(x.kcal / top) * 100}%` }} /><i className="goal-mark" style={{ bottom: `${(goal / top) * 100}%` }} /></span>
              <span className="kcal-day">{days <= 14 ? dayLabel(x.date, today).split(' ')[0] : Number(x.date.slice(8)) % 5 === 0 ? Number(x.date.slice(8)) : ''}</span>
            </div>
          ))}
        </div>
      </section>

      {d.daysLogged > 0 && (
        <div className="dash-grid">
          <section className="card">
            <h3>🥗 Where calories come from</h3>
            <div className="macro-wrap">
              <div className="donut" style={{ background: donut }} role="img" aria-label={`Protein ${s.protein}%, carbs ${s.carbs}%, fat ${s.fat}%`}><span /></div>
              <ul className="macro-legend">
                <li><i className="sw protein" /> Protein <b>{s.protein}%</b> <small>{fmt(d.macros.protein)} g</small></li>
                <li><i className="sw carbs" /> Carbs <b>{s.carbs}%</b> <small>{fmt(d.macros.carbs)} g</small></li>
                <li><i className="sw fat" /> Fat <b>{s.fat}%</b> <small>{fmt(d.macros.fat)} g</small></li>
              </ul>
            </div>
            <p className="muted small">{s.protein < 12 ? 'Protein is on the low side: dals, paneer, eggs or sprouts help.' : s.fat > 35 ? 'Quite a lot from fat: try less oil or ghee in tadkas.' : 'A good balance. Keep it up!'}</p>
          </section>
          <section className="card">
            <h3>🕒 Average by meal</h3>
            {SLOTS.filter(x => d.bySlot[x] != null).map(x => (
              <div key={x} className="bar-row">
                <span className="bar-label">{t(SLOT_LABEL[x])}</span>
                <span className="bar"><span style={{ width: `${(d.bySlot[x] / slotMax) * 100}%` }} /></span>
                <b className="bar-count wide">{fmt(d.bySlot[x])}</b>
              </div>
            ))}
            <p className="muted small">kcal for one serving, on average.</p>
          </section>
        </div>
      )}

      {d.swap && (
        <section className="card swap-card">
          <h3>💡 Lighter swap</h3>
          <p><b>{d.swap.from.name}</b> added the most calories ({fmt(d.swap.from.kcal)} kcal a serving). Next time, try <b>{d.swap.to.name}</b> ({fmt(d.swap.to.kcal)} kcal) and save about <b>{fmt(d.swap.saves)} kcal</b>.</p>
          <button className="btn sm" onClick={() => go('recipe/' + d.swap.to.id)}>See {d.swap.to.name}</button>
        </section>
      )}

      <section className="card">
        <div className="row between"><h3>🍛 Meals and calories</h3><span className="muted small">{d.uncounted ? `${d.uncounted} without calories` : 'per serving'}</span></div>
        {d.meals.length === 0 ? <p className="muted">Nothing logged in this period. Log meals in the Food diary, or finish cooking a recipe.</p> : (
          <div className="table-wrap">
            <table className="meal-table">
              <thead><tr><th>Day</th><th>Meal</th><th>Dish</th><th className="num">kcal</th><th className="num">Protein</th></tr></thead>
              <tbody>
                {d.meals.map((m, i) => (
                  <tr key={(m.id || m.date + m.name) + i}>
                    <td className="nowrap">{dayLabel(m.date, today)}</td>
                    <td>{t(SLOT_LABEL[m.slot] || m.slot || '')}</td>
                    <td>{m.recipeId ? <button className="btn link sm" onClick={() => go('recipe/' + m.recipeId)}>{m.name}</button> : m.name}</td>
                    <td className="num"><MealKcal meal={m} ai={aiStatus.ai} setHistory={setHistory} notify={notify} /></td>
                    <td className="num">{m.protein ? `${fmt(m.protein)} g` : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {d.uncounted > 0 && <p className="muted small">Food from outside or typed by name has no calories yet: add them yourself{aiStatus.ai ? ', or let AI estimate them' : ''}.</p>}
      </section>

      {d.dishes.length > 0 && (
        <section className="card">
          <h3>🏆 Dishes adding the most calories</h3>
          {d.dishes.slice(0, 6).map(x => (
            <div key={x.id || x.name} className="row between top-dish">
              <span>{x.name} <small className="muted">× {x.times}</small></span>
              <span className="muted small">{fmt(x.kcal)} kcal each · <b>{fmt(x.totalKcal)}</b> total</span>
            </div>
          ))}
        </section>
      )}

      <a className="btn whatsapp" href={whatsappLink(report)} target="_blank" rel="noreferrer">Share this summary on WhatsApp</a>
      <p className="muted small center">Calories are one serving of each logged meal, from Ballava's recipe numbers. A rough guide per person, not medical advice.</p>
    </>
  );
}

export default function Dashboard(props) {
  const { view } = props;
  return (
    <div className="screen dashboard">
      <Header title="Dashboard" />
      <div className="segments" role="group" aria-label="Dashboard view">
        <button className={'seg' + (view === 'overview' ? ' on' : '')} aria-pressed={view === 'overview'} onClick={() => go('dashboard')}>📊 Overview</button>
        <button className={'seg' + (view === 'diary' ? ' on' : '')} aria-pressed={view === 'diary'} onClick={() => go('track')}>📖 Food diary</button>
      </div>
      {view === 'diary' ? <Track {...props} embedded /> : <Overview {...props} />}
    </div>
  );
}
