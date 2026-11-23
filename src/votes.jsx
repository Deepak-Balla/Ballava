// 🗳 Sharing a plan on WhatsApp so the family can vote on it.
// The message has the plan and a link for every dish: tapping one votes for it, with no account needed.
// (WhatsApp doesn't let other apps create its own polls or read their results, so the votes come to Ballava instead.)
// Results show in the app as they come in, and one tap puts the winners in the plan.
import React, { useEffect, useRef, useState } from 'react';
import { SLOTS, SLOT_LABEL, WEEKDAYS, addDays, dayKey, slotNow } from './catalog.js';
import { api, brain, go, whatsappLink } from './lib.js';

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

export function dayLabel(date, today = dayKey()) {
  if (date === today) return 'Today';
  if (date === addDays(today, 1)) return 'Tomorrow';
  const d = new Date(date + 'T12:00:00');
  return `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${d.toLocaleString('en', { month: 'short' })}`;
}
export const mealLabel = meal => (meal.date ? `${SLOT_LABEL[meal.slot] || meal.title}, ${dayLabel(meal.date)}` : meal.title);

// Links that only work on this computer, or only on the same Wi-Fi.
export function linkReach(base) {
  const host = (() => { try { return new URL(base).hostname; } catch { return ''; } })();
  if (host === 'localhost' || host.startsWith('127.')) return 'computer';
  return /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(host) ? 'wifi' : 'anywhere';
}
export function shareBaseFor(serverBase) {
  return linkReach(location.origin) !== 'anywhere' && serverBase ? serverBase : location.origin;
}

const KEYCAPS = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣'];
export function voteMessage(ballot, base, findRecipe) {
  const link = `${base}/v/${ballot.group}`;
  const count = ballot.meals.reduce((n, m) => n + m.options.length, 0);
  const direct = count <= 12; // a whole week would be too many links for one message
  const lines = ['🍽 *What should we eat?*', direct ? 'Tap a link to vote for that dish:' : 'Here is the plan. Tap the link at the end to vote:'];
  ballot.meals.forEach((m, mi) => {
    lines.push('', `*${mealLabel(m)}*`);
    m.options.forEach((o, oi) => {
      const kcal = findRecipe(o.id)?.nutrition?.kcal;
      lines.push(`${KEYCAPS[oi] || '•'} ${o.name}${kcal != null ? ` (${kcal} kcal)` : ''}`);
      if (direct) lines.push(`${link}/${mi}-${oi}`);
    });
  });
  lines.push('', direct ? 'See the votes, or change yours:' : '👉 Vote here:', link);
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

/** The meals of one vote, with live results. Tap a dish to vote. */
export function MealVote({ meal, onVote, heading = true }) {
  const most = Math.max(1, ...meal.options.map(o => o.votes));
  return (
    <div className="meal-vote">
      {heading && <b className="meal-vote-title">{mealLabel(meal)}{meal.closed && <span className="pill">Closed</span>}</b>}
      {meal.options.map(o => (
        <button key={o.id} className={'vote-option' + (meal.mine === o.id ? ' on' : '')} disabled={meal.closed || !onVote} aria-pressed={meal.mine === o.id} onClick={() => onVote(meal, o.id)}>
          <span className="vote-bar" style={{ width: `${(o.votes / most) * 100}%` }} aria-hidden="true" />
          <span className="vote-name">{meal.leaders.includes(o.id) ? '🏆 ' : ''}{o.name}{o.voters.length > 0 && <small>{o.voters.join(', ')}</small>}</span>
          <b>{o.votes}</b>
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
          <MealVote meal={m} onVote={vote} heading={false} />
        </details>
      ))}
      <div className="row">
        {total > 0 && <button className="btn sm primary" onClick={applyWinners}>{meals.length > 1 ? 'Use the winners' : 'Use the winner'}</button>}
        <a className="btn whatsapp sm" href={whatsappLink(voteMessage(ballot, base, findRecipe))} target="_blank" rel="noreferrer">Share vote</a>
        <button className="btn link sm" onClick={() => setPlan(p => Object.fromEntries(Object.entries(p).map(([d, day]) => {
          if (!meals.some(m => m.date === d)) return [d, day];
          const { vote: _v, poll: _p, ...rest } = day;
          return [d, rest];
        })))}>Remove</button>
      </div>
    </div>
  );
}

/** Share a day (or the week) on WhatsApp, with a vote on each meal. */
export function ShareSheet({ date = null, ctx, onClose }) {
  const { plan, setPlan, family, findRecipe, notify, auth } = ctx;
  const today = dayKey();
  // A day that already has a vote keeps it, so sharing the week never hides votes that are coming in.
  const week = Array.from({ length: 7 }, (_, i) => addDays(today, i)).filter(d => plan[d] && !ballotOf(plan[d]));
  const planned = s => (date ? !!plan[date]?.[s] : week.some(d => plan[d]?.[s]));
  const still = s => date !== today || SLOTS.indexOf(s) >= SLOTS.indexOf(slotNow()); // not a meal that's over for today
  const [slots, setSlots] = useState(date ? SLOTS.filter(s => planned(s) && still(s)) : ['dinner']);
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(null); // { text, base } once the vote exists
  const toggle = s => setSlots(x => (x.includes(s) ? x.filter(y => y !== s) : SLOTS.filter(y => y === s || x.includes(y))));

  async function prepare() {
    setBusy(true);
    try {
      const wanted = (date ? [date] : week).flatMap(d => slots.filter(s => plan[d]?.[s]).map(s => ({ date: d, slot: s })));
      const meals = [];
      const used = []; // so the same alternative isn't offered for two meals
      for (const m of wanted) {
        const current = findRecipe(plan[m.date][m.slot]);
        const { options } = await brain('alternatives', { ...family, plan, date: m.date, slot: m.slot, start: today, exclude: used, limit: 2 });
        const others = (options || []).map(o => findRecipe(o.id)).filter(Boolean);
        used.push(...others.map(r => r.id));
        meals.push({ ...m, options: [current, ...others].filter(Boolean).map(r => ({ id: r.id, name: r.name })) });
      }
      const ballot = await api('ballots', { meals });
      setPlan(p => {
        const next = { ...p };
        for (const d of new Set(ballot.meals.map(m => m.date))) next[d] = { ...next[d], vote: ballot.group };
        return next;
      });
      const base = shareBaseFor(ballot.shareBase);
      setReady({ text: voteMessage(ballot, base, findRecipe), base });
    } catch (e) { notify(e.message); }
    setBusy(false);
  }

  const reach = ready && linkReach(ready.base);
  const title = date ? `Share ${dayLabel(date).replace('Today', 'today').replace('Tomorrow', 'tomorrow')}` : 'Share the week';
  return (
    <div className="sheet" role="dialog" aria-label="Share the plan on WhatsApp" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="sheet-inner swap-picker">
        <div className="row between"><h3>{title} and vote</h3><button className="icon-btn" onClick={onClose} aria-label="Close">✕</button></div>
        {!auth.user ? (
          <>
            <p>Sign in to let your family vote: the votes come back to your account.</p>
            <button className="btn primary" onClick={() => go('account')}>Sign in</button>
          </>
        ) : !ready && !date && !week.length ? (
          <p>Every planned day already has a vote. Tap "Share vote" on a day to send it again.</p>
        ) : !ready ? (
          <>
            <p className="muted small">Which meals should the family vote on? Each gets your planned dish and two more ideas that suit everyone.</p>
            <div className="chips wrap" role="group" aria-label="Meals to vote on">
              {SLOTS.filter(planned).map(s => <button key={s} className={'chip' + (slots.includes(s) ? ' on' : '')} aria-pressed={slots.includes(s)} onClick={() => toggle(s)}>{SLOT_LABEL[s]}</button>)}
            </div>
            <button className="btn primary big" disabled={busy || !slots.length} onClick={prepare}>{busy ? 'Getting the vote ready…' : 'Make the vote'}</button>
          </>
        ) : (
          <>
            <p className="muted small">This is what your family will get. They tap a dish, and the vote shows up in Ballava.</p>
            <pre className="share-preview">{ready.text}</pre>
            {reach === 'wifi' && <p className="note warn">These links open only on your home Wi-Fi ({ready.base}). For family elsewhere, open Ballava from its https address and share from there (README: "Use Ballava on your phone").</p>}
            {reach === 'computer' && <p className="note warn">These links open only on this computer. Open Ballava from its Wi-Fi or https address to share it (README: "Use Ballava on your phone").</p>}
            <a className="btn whatsapp big" href={whatsappLink(ready.text)} target="_blank" rel="noreferrer" onClick={onClose}>Send on WhatsApp</a>
          </>
        )}
      </div>
    </div>
  );
}
