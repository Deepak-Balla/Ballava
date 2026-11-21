import React, { useEffect, useMemo, useState } from 'react';
import { SLOTS, SLOT_LABEL, WEEKDAYS, addDays, dayKey, getCatalog } from '../catalog.js';
import { Header, DietDot, Empty } from '../ui.jsx';
import { api, brain, go, useBrain, whatsappLink } from '../lib.js';
import { t, LANGS } from '../i18n.js';

// All the planning happens in Python (kitchen/planner.py). This screen shows the plan and sends taps back.

const dateLabel = (key, today) => {
  if (key === today) return 'Today';
  if (key === addDays(today, 1)) return 'Tomorrow';
  const d = new Date(key + 'T12:00:00');
  return `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${d.toLocaleString('en', { month: 'short' })}`;
};

const dayIds = day => (day ? [...SLOTS.map(s => day[s]), ...Object.values(day.tiffins || {}), ...Object.values(day.fast || {})].filter(Boolean) : []);

// Changing one planned meal: a page of ideas from Python (kitchen/api.py -> alternatives), each new page skipping
// everything already shown, plus a search through the whole recipe book.
function SwapPicker({ date, slot, today, plan, setPlan, family, findRecipe, catalog, notify, onClose }) {
  const current = plan[date]?.[slot];
  const [seen, setSeen] = useState(current ? [current] : []);
  const [page, setPage] = useState({ loading: true, options: [], more: false });
  const [q, setQ] = useState('');
  const label = `${t(SLOT_LABEL[slot])} · ${dateLabel(date, today)}`;

  async function load(exclude) {
    setPage(p => ({ ...p, loading: true }));
    try {
      const r = await brain('alternatives', { ...family, plan, date, slot, start: today, exclude, limit: 6 });
      setPage({ loading: false, options: r.options.filter(o => findRecipe(o.id)), more: r.more });
    } catch (e) { notify(e.message); setPage({ loading: false, options: [], more: false }); }
  }
  useEffect(() => { load(seen); }, []);

  function choose(id) {
    setPlan(p => ({ ...p, [date]: { ...p[date], [slot]: id, locked: [...new Set([...(p[date]?.locked || []), slot])] } }));
    notify(`${findRecipe(id)?.name} for ${label.toLowerCase()} (locked, so a refresh keeps it)`);
    onClose();
  }
  const hidden = new Set(catalog.hidden);
  const found = q.trim().length > 1 ? getCatalog().recipes.filter(r => !hidden.has(r.id) && r.id !== current
    && `${r.name} ${r.alt || ''} ${r.cuisine}`.toLowerCase().includes(q.trim().toLowerCase())).slice(0, 8) : [];

  const Option = ({ r, why = [], missing = [] }) => (
    <button className="swap-option" onClick={() => choose(r.id)}>
      <b><DietDot diet={r.diet} /> {r.name}</b>
      <span className="muted small">{r.time} min{r.nutrition?.kcal != null ? ` · ${r.nutrition.kcal} kcal` : ''}{r.meal.includes(slot) ? '' : ` · usually ${r.meal.join('/')}`}</span>
      {(why.length > 0 || missing.length > 0) && (
        <span className="small">{why.map(w => <span key={w} className="pill good">{w}</span>)}{missing.length > 0 && <span className="pill warn">Need {missing.join(', ')}</span>}</span>
      )}
    </button>
  );

  return (
    <div className="sheet" role="dialog" aria-label={`Change ${label}`} onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="sheet-inner swap-picker">
        <div className="row between"><h3>Change {label}</h3><button className="icon-btn" onClick={onClose} aria-label="Close">✕</button></div>
        {current && findRecipe(current) && <p className="muted small">Now: {findRecipe(current).name}</p>}
        {page.loading ? <p className="muted thinking" role="status">Finding ideas…</p> : page.options.length === 0
          ? <p className="muted">No more ideas that suit everyone this week. Try searching below.</p>
          : <div className="swap-list">{page.options.map(o => <Option key={o.id} r={findRecipe(o.id)} why={o.why} missing={o.missing} />)}</div>}
        <div className="row">
          {page.more && !page.loading && (
            <button className="btn ghost sm" onClick={() => { const next = [...seen, ...page.options.map(o => o.id)]; setSeen(next); load(next); }}>🔁 Show other ideas</button>
          )}
          {page.options[0] && <button className="btn sm" onClick={() => choose(page.options[0].id)}>✨ Just pick for me</button>}
        </div>
        <input className="search" type="search" value={q} onChange={e => setQ(e.target.value)} placeholder="Or search any recipe: biryani, dosa, paneer…" aria-label="Search all recipes" />
        {found.length > 0 && <div className="swap-list">{found.map(r => <Option key={r.id} r={r} />)}</div>}
      </div>
    </div>
  );
}

function Row({ label, recipe, locked, onLock, onSwap, onCooked, cooked }) {
  return (
    <div className="plan-row">
      <span className="plan-slot">{label}</span>
      {recipe ? (
        <button className="plan-dish" onClick={() => go('recipe/' + recipe.id)}><DietDot diet={recipe.diet} /> {recipe.name} <span className="muted small">{recipe.time} min</span></button>
      ) : <span className="muted plan-dish">Nothing suitable found</span>}
      <span className="plan-actions">
        {onCooked && recipe && (cooked ? <span className="pill good" title="Logged">✓</span> : <button className="icon-btn sm" onClick={onCooked} aria-label={`Mark ${recipe.name} as cooked`}>✓</button>)}
        {onLock && <button className={'icon-btn sm' + (locked ? ' on' : '')} onClick={onLock} aria-pressed={!!locked} aria-label={`${locked ? 'Unlock' : 'Lock'} ${label}`}>{locked ? '🔒' : '🔓'}</button>}
        {onSwap && <button className="icon-btn sm" onClick={onSwap} aria-label={`Swap ${label}`}>⇄</button>}
      </span>
    </div>
  );
}

function FamilyVote({ day, date, family, findRecipe, plan, setPlan, notify, signedIn }) {
  const [view, setView] = useState(null);
  const poll = plan[date]?.poll;
  useEffect(() => {
    if (!poll) return undefined;
    let live = true;
    const load = () => api('polls/' + poll.token).then(v => live && setView(v)).catch(() => {});
    load();
    const id = setInterval(load, 15000);
    return () => { live = false; clearInterval(id); };
  }, [poll?.token]);

  async function start() {
    if (!signedIn) { notify('Please sign in to start a family vote'); return; }
    try {
      const { ids } = await brain('recommend', { ...family, slot: 'dinner', date, limit: 3 });
      const current = day.dinner && findRecipe(day.dinner);
      const options = [...(current ? [current] : []), ...ids.map(findRecipe).filter(Boolean)]
        .filter((r, i, a) => a.findIndex(x => x.id === r.id) === i).slice(0, 3).map(r => ({ id: r.id, name: r.name }));
      const { token } = await api('polls', { title: `What should we eat for dinner on ${dateLabel(date, dayKey())}?`, date, slot: 'dinner', options });
      setPlan(p => ({ ...p, [date]: { ...p[date], poll: { token } } }));
    } catch (e) { notify(e.message); }
  }

  function useWinner() {
    const win = [...view.options].sort((a, b) => b.votes - a.votes)[0];
    setPlan(p => {
      const d = { ...p[date], dinner: win.id, locked: [...new Set([...(p[date].locked || []), 'dinner'])] };
      delete d.poll;
      return { ...p, [date]: d };
    });
    notify(`${win.name} it is!`);
  }

  if (!poll) return <button className="btn link small-btn" onClick={start}>🗳 Ask the family about dinner</button>;
  const link = `${location.origin}${location.pathname}#/vote/${poll.token}`;
  return (
    <div className="vote-box">
      <b>{t('Family vote')}</b>
      {view?.options.map(o => <div key={o.id} className="row between small"><span>{o.name}</span><b>{o.votes}</b></div>)}
      <div className="row">
        <a className="btn whatsapp sm" href={whatsappLink(`What should we eat? Vote here: ${link}`)} target="_blank" rel="noreferrer">Share vote</a>
        {view?.total > 0 && <button className="btn sm" onClick={useWinner}>Use the winner</button>}
      </div>
    </div>
  );
}

export default function Plan({ pantry, log, plan, setPlan, pins, setPins, prefs, setPrefs, catalog, family, findRecipe, addToShopping, logMeal, notify, auth }) {
  const today = dayKey();
  const [lang, setMenuLang] = useState(prefs.menuLang || 'hi');
  const [busy, setBusy] = useState(false);
  const [changing, setChanging] = useState(null); // { date, slot } while the swap picker is open
  const observed = prefs.observed || [];
  const days = useMemo(() => Array.from({ length: 7 }, (_, i) => addDays(today, i)), [today]);
  const planned = days.some(d => dayIds(plan[d]).length > 0);
  // Prep reminders, groceries, the cook's menu and portion tips, all from Python.
  const info = useBrain('plan-info', { ...family, plan, lang }, planned);
  const { prep = [], groceries = [], menu = null, plateTips = 0 } = info.data || {};
  const upcoming = catalog.festivals.filter(f => f.date >= today).slice(0, 6);

  async function makePlan() {
    setBusy(true);
    try {
      const { plan: fresh } = await brain('plan', { ...family, start: today, existing: plan, observed });
      // Keep the last 60 days so the dashboard and repeat checks have history.
      const cutoff = addDays(today, -60);
      const kept = Object.fromEntries(Object.entries(plan).filter(([d]) => d >= cutoff && !fresh[d]));
      for (const [d, day] of Object.entries(fresh)) if (plan[d]?.poll) day.poll = plan[d].poll;
      setPlan({ ...kept, ...fresh });
      notify('Your week is planned. Lock what you like, swap what you don\'t.');
    } catch (e) { notify(e.message); }
    setBusy(false);
  }

  const toggleLock = (date, slot) => setPlan(p => {
    const locked = p[date].locked || [];
    return { ...p, [date]: { ...p[date], locked: locked.includes(slot) ? locked.filter(s => s !== slot) : [...locked, slot] } };
  });

  const swap = (date, slot) => setChanging({ date, slot });

  const cookedToday = (id, slot) => log.some(e => e.recipeId === id && e.date === today && e.slot === slot);

  function addGroceries() {
    addToShopping(groceries.map(g => g.id));
    notify(`Added ${groceries.length} item(s) to your shopping list`);
  }

  return (
    <div className="screen">
      <Header title={t('Weekly plan')} />
      {changing && <SwapPicker {...changing} today={today} plan={plan} setPlan={setPlan} family={family} findRecipe={findRecipe} catalog={catalog}
        notify={notify} onClose={() => setChanging(null)} />}
      <button className="btn primary big" onClick={makePlan} disabled={busy}>{busy ? 'Planning your week…' : planned ? 'Refresh unlocked meals' : t('Plan my week')}</button>
      {!pantry.length && <p className="muted small">Tip: add your kitchen items first, so the plan uses what you already have.</p>}

      {prep.length > 0 && (
        <div className="card prep-card">
          <h3>🌙 {t('Prep for tomorrow')}</h3>
          {prep.map(p => <p key={p.recipeId}><b>{p.name}:</b> {p.text}</p>)}
        </div>
      )}

      {!planned && <Empty title="No plan yet">Tap the button above. Ballava plans 7 days of meals around your kitchen, your family's diets and what you ate recently.</Empty>}

      <div className="plan-grid">
      {planned && days.map(date => {
        const day = plan[date];
        if (!day) return null;
        const lock = day.locked || [];
        const canLog = date === today;
        return (
          <section key={date} className="card plan-day">
            <div className="row between"><h3>{dateLabel(date, today)}</h3>{day.festival && <span className="pill warn">{day.festival}</span>}</div>
            {SLOTS.map(slot => (
              <Row key={slot} label={t(SLOT_LABEL[slot])} recipe={day[slot] && findRecipe(day[slot])} locked={lock.includes(slot)}
                onLock={() => toggleLock(date, slot)} onSwap={() => swap(date, slot)} cooked={cookedToday(day[slot], slot)}
                onCooked={canLog ? () => { const r = findRecipe(day[slot]); logMeal({ recipeId: r.id, name: r.name, date, slot }); notify(`Logged ${r.name}`); } : undefined} />
            ))}
            {Object.entries(day.tiffins || {}).map(([who, id]) => <Row key={'t' + who} label={`Tiffin · ${who}`} recipe={findRecipe(id)} />)}
            {Object.entries(day.fast || {}).map(([who, id]) => <Row key={'f' + who} label={`Vrat · ${who}`} recipe={findRecipe(id)} />)}
            {date === today && plateTips > 0 && <p className="muted small">🍽 {plateTips} portion tip{plateTips > 1 ? 's' : ''} today. Open a dish to see who needs what.</p>}
            <FamilyVote day={day} date={date} family={family} findRecipe={findRecipe} plan={plan} setPlan={setPlan} notify={notify} signedIn={!!auth.user} />
          </section>
        );
      })}
      </div>

      {planned && (
        <div className="card">
          <h3>🛒 Groceries for this plan</h3>
          {info.loading && !info.data ? <p className="muted">Working out what you need…</p> : groceries.length === 0 ? <p className="muted">You have everything for this plan.</p> : (
            <>
              <p className="muted small">{groceries.slice(0, 8).map(g => g.name).join(', ')}{groceries.length > 8 ? ` and ${groceries.length - 8} more` : ''}</p>
              <button className="btn ghost" onClick={addGroceries}>+ Add {groceries.length} items to shopping list</button>
            </>
          )}
        </div>
      )}

      {plan[today] && menu && (
        <div className="card">
          <h3>👩‍🍳 Send today's menu to your cook</h3>
          <div className="row">
            <select value={lang} aria-label="Menu language" onChange={e => { setMenuLang(e.target.value); setPrefs(p => ({ ...p, menuLang: e.target.value })); }}>
              {LANGS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
            </select>
            <a className="btn whatsapp" href={whatsappLink(menu)} target="_blank" rel="noreferrer">Share on WhatsApp</a>
          </div>
        </div>
      )}

      {pins.length > 0 && (
        <div className="card">
          <h3>⭐ Family traditions</h3>
          <p className="muted small">These always come first on their day, and never count as repeats.</p>
          {pins.map(p => (
            <div key={p.recipeId + p.weekday} className="row between">
              <span>{WEEKDAYS[p.weekday]}: {findRecipe(p.recipeId)?.name || p.recipeId}</span>
              <button className="btn link danger" onClick={() => setPins(pins.filter(x => x !== p))}>Remove</button>
            </div>
          ))}
        </div>
      )}

      {upcoming.length > 0 && (
        <div className="card">
          <h3>🪔 Festivals and fasts</h3>
          <p className="muted small">Tick the fasts your family keeps. Ballava plans a vrat meal for those days.</p>
          {upcoming.map(f => (
            <label key={f.id} className="check">
              {f.fast && <input type="checkbox" checked={observed.includes(f.id)} onChange={e => setPrefs(p => ({ ...p, observed: e.target.checked ? [...observed, f.id] : observed.filter(x => x !== f.id) }))} />}
              <span>{f.name} <span className="muted small">{dateLabel(f.date, today)}</span></span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
