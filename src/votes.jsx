// 🗳 Sharing a plan on WhatsApp so the family can vote on it.
// The message is short, with one link. The link opens a page with every meal in it, where the family taps their
// favourites, with no account needed. (WhatsApp doesn't let other apps create its own polls or read their results.)
// Results show in the app as they come in, and one tap puts the winners in the plan.
import React, { useEffect, useRef, useState } from 'react';
import { SLOTS, SLOT_LABEL, addDays, dayKey, slotNow } from './catalog.js';
import { api, brain, go, whatsappLink } from './lib.js';
import { dayLabel } from './fasting.jsx';
import { DietDot } from './ui.jsx';

export function voterId() {
  try {
    let id = localStorage.getItem('ballava.voter');
    if (!id) { id = Date.now().toString(36) + Math.random().toString(36).slice(2, 12); localStorage.setItem('ballava.voter', id); }
    return id;
  } catch { return Math.random().toString(36).slice(2); }
}
export const getBallot = group => api(`ballots/${group}?voter=${voterId()}`);
export const castVote = (meal, optionId, name) => api(`polls/${meal.token}/vote`, { voter: voterId(), optionId, name });
export const ballotOf = day => day?.vote || day?.poll?.token || null; // `poll` is a vote started by an older version

// "Dinner", or "Dinner (Nomulu)" on a day everyone fasts. (Votes from older versions had other titles.)
export const slotTitle = meal => (meal.title?.startsWith(SLOT_LABEL[meal.slot]) ? meal.title : SLOT_LABEL[meal.slot] || meal.title);
export const mealLabel = meal => (meal.date ? `${slotTitle(meal)}, ${dayLabel(meal.date)}` : meal.title);

// Links that only work on this computer, or only on the same Wi-Fi.
export function linkReach(base) {
  const host = (() => { try { return new URL(base).hostname; } catch { return ''; } })();
  if (host === 'localhost' || host.startsWith('127.')) return 'computer';
  return /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(host) ? 'wifi' : 'anywhere';
}
export function shareBaseFor(serverBase) {
  return linkReach(location.origin) !== 'anywhere' && serverBase ? serverBase : location.origin;
}

const orList = names => (names.length < 2 ? names.join('') : `${names.slice(0, -1).join(', ')} or ${names[names.length - 1]}`);

// Short enough to read at a glance: what it's about, the note, and the one link that has everything.
export function voteMessage(ballot, base) {
  const { meals, note } = ballot;
  const days = [...new Set(meals.map(m => m.date))].sort();
  const lines = ['🍽 *What should we eat?*'];
  if (note) lines.push(note);
  if (meals.length <= 3) {
    for (const m of meals) lines.push(`${mealLabel(m)}: ${orList(m.options.map(o => o.name))}`);
  } else {
    const slots = SLOTS.filter(s => meals.some(m => m.slot === s)).map(s => SLOT_LABEL[s].toLowerCase());
    const span = days.length > 1 ? `${dayLabel(days[0])} to ${dayLabel(days[days.length - 1])}` : dayLabel(days[0]);
    lines.push(`${meals.length} meals, ${span} (${slots.join(', ')})`);
  }
  lines.push('', `👉 Tap to vote: ${base}/v/${ballot.group}`);
  return lines.join('\n');
}

// Follows the votes of several shared plans, so results appear as the family votes.
export function useBallots(groups, onNewVote) {
  const key = [...new Set(groups.filter(Boolean))].sort().join(',');
  const [ballots, setBallots] = useState({});
  const totals = useRef({});
  const notifyNew = useRef(onNewVote);
  notifyNew.current = onNewVote;
  useEffect(() => {
    if (!key) return undefined;
    let live = true;
    const load = () => key.split(',').forEach(group => getBallot(group).then(b => {
      if (!live) return;
      const total = b.meals.reduce((n, m) => n + m.total, 0);
      if (totals.current[group] != null && total > totals.current[group]) notifyNew.current?.(total - totals.current[group]);
      totals.current[group] = total;
      setBallots(s => ({ ...s, [group]: b }));
    }).catch(() => {}));
    load();
    const id = setInterval(() => document.visibilityState === 'visible' && load(), 8000);
    return () => { live = false; clearInterval(id); };
  }, [key]);
  // Your own vote in the app: shown straight away, and not announced as a new family vote.
  const update = (group, meal) => {
    const before = ballots[group];
    if (!before) return;
    const meals = before.meals.map(m => (m.token === meal.token ? meal : m));
    totals.current[group] = meals.reduce((n, m) => n + m.total, 0);
    setBallots(s => ({ ...s, [group]: { ...before, meals } }));
  };
  return [ballots, update];
}

/** One meal of a vote, with live results. Tap a dish to vote. */
export function MealVote({ meal, onVote, title = mealLabel(meal), facts = false }) {
  const most = Math.max(1, ...meal.options.map(o => o.votes));
  return (
    <div className="meal-vote">
      {title && <b className="meal-vote-title">{title} {meal.closed && <span className="pill">Closed</span>}</b>}
      {meal.options.map(o => (
        <button key={o.id} className={'vote-option' + (meal.mine === o.id ? ' on' : '')} disabled={meal.closed || !onVote} aria-pressed={meal.mine === o.id} onClick={() => onVote(meal, o.id)}>
          <span className="vote-bar" style={{ width: `${(o.votes / most) * 100}%` }} aria-hidden="true" />
          <span className="vote-name">
            <span>{meal.leaders.includes(o.id) ? '🏆 ' : ''}{o.name}</span>
            {facts && o.time != null && <small><DietDot diet={o.diet} /> {o.kcal != null ? `${o.kcal} kcal · ` : ''}{o.time} min</small>}
            {o.voters.length > 0 && <small className="voters">{o.voters.join(', ')}</small>}
          </span>
          <b>{meal.mine === o.id && '✓ '}{o.votes}</b>
        </button>
      ))}
    </div>
  );
}

/** Results inside the app: for one day of the plan (`date`), or everything in the vote. */
export function VoteResults({ ballot, date, ctx, onUpdate }) {
  const { plan, setPlan, findRecipe, notify, auth } = ctx;
  // Only meals still waiting for a result (using a winner takes that day out of the vote).
  const meals = ballot.meals.filter(m => (date ? m.date === date : m.date >= dayKey()) && ballotOf(plan[m.date]) === ballot.group);
  const leading = m => m.options.filter(o => m.leaders.includes(o.id)).map(o => o.name).join(' or ');
  const total = meals.reduce((n, m) => n + m.total, 0);
  if (!meals.length) return null;

  async function vote(meal, optionId) {
    try { onUpdate(ballot.group, await castVote(meal, optionId, auth.user?.name)); } catch (e) { notify(e.message); }
  }
  function applyWinners() {
    setPlan(p => {
      const next = { ...p };
      for (const m of meals.filter(x => x.leaders.length)) { // days nobody voted on yet stay open
        const day = { ...(next[m.date] || {}) };
        // A tie keeps the dish already in the plan, if it's one of the winners.
        day[m.slot] = m.leaders.includes(day[m.slot]) ? day[m.slot] : m.leaders[0];
        day.locked = [...new Set([...(day.locked || []), m.slot])];
        delete day.vote; delete day.poll;
        next[m.date] = day;
      }
      return next;
    });
    const names = [...new Set(meals.filter(m => m.leaders.length).map(m => {
      const now = plan[m.date]?.[m.slot];
      const id = m.leaders.includes(now) ? now : m.leaders[0];
      return findRecipe(id)?.name || m.options.find(o => o.id === id)?.name;
    }))];
    notify(`${names.join(', ')} it is! Your plan is updated.`);
  }
  const base = shareBaseFor(ballot.shareBase);
  return (
    <div className="vote-box">
      <div className="row between"><b>🗳 Family vote</b><span className="muted small">{total} vote{total === 1 ? '' : 's'} so far</span></div>
      {meals.length <= 2 ? meals.map(m => <MealVote key={m.token} meal={m} onVote={vote} />) : meals.map(m => (
        <details key={m.token} className="vote-fold">
          <summary><b>{mealLabel(m)}</b> <span className="muted small">{m.total ? `🏆 ${leading(m)} (${m.total} vote${m.total > 1 ? 's' : ''})` : 'No votes yet'}</span></summary>
          <MealVote meal={m} onVote={vote} title="" />
        </details>
      ))}
      <div className="row">
        {total > 0 && <button className="btn sm primary" onClick={applyWinners}>{meals.length > 1 ? 'Use the winners' : 'Use the winner'}</button>}
        <a className="btn whatsapp sm" href={whatsappLink(voteMessage(ballot, base))} target="_blank" rel="noreferrer">Share vote</a>
        <button className="btn link sm" onClick={() => setPlan(p => Object.fromEntries(Object.entries(p).map(([d, day]) => {
          if (!meals.some(m => m.date === d)) return [d, day];
          const { vote: _v, poll: _p, ...rest } = day;
          return [d, rest];
        })))}>Remove</button>
      </div>
    </div>
  );
}

/** Choose what to send (days, meals, a note), and share it on WhatsApp as one voting link. */
export function ShareSheet({ date = null, ctx, onClose }) {
  const { plan, setPlan, family, findRecipe, notify, auth } = ctx;
  const today = dayKey();
  const planned = (d, s) => !!plan[d]?.[s] && !!findRecipe(plan[d][s]);
  const still = (d, s) => d !== today || SLOTS.indexOf(s) >= SLOTS.indexOf(slotNow()); // not a meal that's over for today
  const all = Array.from({ length: 7 }, (_, i) => addDays(today, i)).filter(d => SLOTS.some(s => planned(d, s)));
  const voted = d => !!ballotOf(plan[d]); // it has a vote already
  const [days, setDays] = useState(date ? [date] : all.filter(d => !voted(d)));
  const [slots, setSlots] = useState(date ? SLOTS.filter(s => planned(date, s) && still(date, s)) : ['dinner']);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(null); // { text, base } once the vote exists
  const toggle = (list, x, order) => (list.includes(x) ? list.filter(y => y !== x) : order.filter(y => y === x || list.includes(y)));
  const meals = days.flatMap(d => slots.filter(s => planned(d, s) && still(d, s)).map(s => ({ date: d, slot: s })));
  const again = days.filter(voted);

  async function prepare() {
    setBusy(true);
    try {
      // Python picks the choices: your dish and two more that suit everyone (fasting dishes on a fasting day).
      const { meals: choices, offline } = await brain('vote-options', { ...family, plan, start: today, meals });
      if (offline) throw new Error("You're offline. Connect to the internet to share a vote.");
      const ballot = await api('ballots', { note: note.trim(), meals: choices });
      setPlan(p => {
        const next = { ...p };
        for (const d of new Set(ballot.meals.map(m => m.date))) { const { poll: _p, ...day } = next[d] || {}; next[d] = { ...day, vote: ballot.group }; }
        return next;
      });
      const base = shareBaseFor(ballot.shareBase);
      setReady({ text: voteMessage(ballot, base), base });
    } catch (e) { notify(e.message); }
    setBusy(false);
  }

  const reach = ready && linkReach(ready.base);
  const chip = (key, on, onClick, label) => <button key={key} type="button" className={'chip' + (on ? ' on' : '')} aria-pressed={on} onClick={onClick}>{label}</button>;
  return (
    <div className="sheet" role="dialog" aria-label="Share the plan on WhatsApp" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="sheet-inner swap-picker share-sheet">
        <div className="row between"><h3>Share on WhatsApp and vote</h3><button className="icon-btn" onClick={onClose} aria-label="Close">✕</button></div>
        {!auth.user ? (
          <>
            <p>Sign in to let your family vote: the votes come back to your account.</p>
            <button className="btn primary" onClick={() => go('account')}>Sign in</button>
          </>
        ) : !ready ? (
          <>
            <p className="muted small">Choose what to send. It all goes in one link, with your planned dish and two more ideas for every meal.</p>
            <b className="small">Days</b>
            <div className="chips wrap" role="group" aria-label="Days to vote on">
              {all.map(d => chip(d, days.includes(d), () => setDays(toggle(days, d, all)), `${voted(d) ? '🗳 ' : ''}${dayLabel(d, today)}`))}
            </div>
            <b className="small">Meals</b>
            <div className="chips wrap" role="group" aria-label="Meals to vote on">
              {SLOTS.map(s => chip(s, slots.includes(s), () => setSlots(toggle(slots, s, SLOTS)), SLOT_LABEL[s]))}
            </div>
            <label className="small share-note">Add a note (optional)
              <input value={note} maxLength={200} onChange={e => setNote(e.target.value)} placeholder="e.g. Guests on Sunday, choose by tonight!" />
            </label>
            {again.length > 0 && <p className="note warn">{again.map(d => dayLabel(d, today)).join(', ')} already {again.length > 1 ? 'have' : 'has'} a vote (🗳). Sharing again starts a new one for {again.length > 1 ? 'those days' : 'that day'}.</p>}
            <button className="btn primary big" disabled={busy || !meals.length} onClick={prepare}>{busy ? 'Getting the vote ready…' : meals.length ? `Make one link for ${meals.length} meal${meals.length > 1 ? 's' : ''}` : 'Choose at least one meal'}</button>
          </>
        ) : (
          <>
            <p className="muted small">This is what your family will get. The link opens every meal, and their votes show up in Ballava.</p>
            <pre className="share-preview">{ready.text}</pre>
            {reach === 'wifi' && <p className="note warn">This link opens only on your home Wi-Fi ({ready.base}). For family elsewhere, open Ballava from its https address and share from there (README: "Use Ballava on your phone").</p>}
            {reach === 'computer' && <p className="note warn">This link opens only on this computer. Open Ballava from its Wi-Fi or https address to share it (README: "Use Ballava on your phone").</p>}
            <a className="btn whatsapp big" href={whatsappLink(ready.text)} target="_blank" rel="noreferrer" onClick={onClose}>Send on WhatsApp</a>
            <button className="btn link" onClick={() => { const link = ready.text.slice(ready.text.lastIndexOf('http')); navigator.clipboard?.writeText(link).then(() => notify('Link copied'), () => notify(link)); }}>Copy just the link</button>
          </>
        )}
      </div>
    </div>
  );
}
