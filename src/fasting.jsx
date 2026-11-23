// 🪔 Fasting days: weekly fasts (Family), festivals marked as fasts in the admin portal, and days the family picks.
// Python decides who fasts and which dishes suit (kitchen/planner.py -> fast_on, vrat_ideas). `ctx.fasts` is its answer for
// the next month: { date: { all, who: [names], festival, key, ideas: [dish ids] } }. Taps here change the choice, and the
// meals planned for that day follow.
import React, { useState } from 'react';
import { SLOTS, WEEKDAYS, addDays, dayKey } from './catalog.js';
import { brain, go } from './lib.js';

export const festivalsOn = (catalog, date) => catalog.festivals.filter(f => f.date === date);
const listNames = names => (names.length < 2 ? names.join('') : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`);
export const whoFasts = fast => (fast.all ? 'Everyone' : listNames(fast.who));
const one = fast => fast.all || fast.who.length === 1; // "Dad fasts", "Dad and Amma fast"
export const fastsText = fast => `${whoFasts(fast)} ${one(fast) ? 'fasts' : 'fast'}`;
export const fastingText = fast => `${whoFasts(fast)} ${one(fast) ? 'is' : 'are'} fasting`;
export const isFasting = (fast, name) => !!fast && (fast.all || fast.who.includes(name));
// The day's meals were planned for different people fasting than now (a new festival, a changed weekly fast...).
export const planNeedsFast = (date, { plan, fasts, fastsLoading }) => !!fasts && !fastsLoading && SLOTS.some(s => plan[date]?.[s]) && (plan[date].fastFor || '') !== (fasts[date]?.key || '');

export function dayLabel(date, today = dayKey()) {
  if (date === today) return 'Today';
  if (date === addDays(today, 1)) return 'Tomorrow';
  const d = new Date(date + 'T12:00:00');
  return `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${d.toLocaleString('en', { month: 'short' })}`;
}

function whenLabel(date, today) {
  const days = Math.round((new Date(date + 'T12:00:00') - new Date(today + 'T12:00:00')) / 86400000);
  const d = new Date(date + 'T12:00:00');
  const name = `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${d.toLocaleString('en', { month: 'short' })}`;
  return days === 0 ? `Today, ${name}` : days === 1 ? `Tomorrow, ${name}` : `${name}, in ${days} days`;
}

// What the family chose for a day, as it will be once the server has answered (so a tap shows at once).
export function chosenFor(date, { prefs, members, fasts }) {
  const names = members.map(m => m.name);
  const pick = prefs.fastDays?.[date];
  if (Array.isArray(pick)) {
    const everyone = pick.includes('*');
    const who = everyone ? names : names.filter(n => pick.includes(n));
    return { any: everyone || who.length > 0, all: everyone || (names.length > 0 && who.length === names.length), who };
  }
  const fast = fasts?.[date];
  return { any: !!fast, all: !!fast?.all, who: fast ? (fast.all ? names : fast.who) : [] };
}

// Puts a freshly planned day in place of the old one, keeping everything that isn't about fasting (votes, tiffins...).
// Going to a full fast remembers the usual meals and their locks, so changing your mind brings them back.
function withFast(old, fresh) {
  const { vrat: _v, fastFor, festival: _f, fast: _o, usual, ...rest } = old;
  const meals = d => Object.fromEntries(SLOTS.filter(s => d[s]).map(s => [s, d[s]]));
  const locks = old.locked || [];
  const before = usual || (fastFor === 'all' ? null : { ...meals(old), locked: locks.filter(s => SLOTS.includes(s)) });
  const out = { ...rest };
  if (fresh.fastFor === 'all') {
    Object.assign(out, meals(fresh));
    if (before) out.usual = before;
    out.locked = locks.filter(s => out[s] && out[s] === old[s]); // a lock stays only on a dish that stays
  } else {
    Object.assign(out, meals(before || fresh));
    out.locked = [...(before?.locked || []), ...locks.filter(s => s.startsWith('vrat:') && fresh.vrat?.[s.slice(5)] === old.vrat?.[s.slice(5)])];
  }
  if (fresh.fastFor) {
    out.fastFor = fresh.fastFor;
    if (fresh.vrat) out.vrat = fresh.vrat;
    if (fresh.festival) out.festival = fresh.festival;
  }
  return out;
}

export function fastingActions(ctx) {
  const { prefs, setPrefs, plan, setPlan, family, findRecipe, log, notify } = ctx;
  const today = dayKey();
  const recent = days => Object.fromEntries(Object.entries(days || {}).filter(([d]) => d >= today));

  // Plan one day's meals again for who fasts now. Meals already cooked today stay, and so do locked fasting dishes.
  // (A locked prawn curry doesn't stay on a day everyone fasts. It comes back if the fast is called off.)
  async function replan(date, change = {}) {
    const day = plan[date];
    if (!day || !SLOTS.some(s => day[s]) || date < today || date > addDays(today, 6)) return null;
    const cooked = date === today ? SLOTS.filter(s => log.some(e => e.date === today && e.slot === s && e.recipeId === day[s])) : [];
    const keep = day.fastFor === 'all' ? [] : (day.locked || []).filter(s => s.startsWith('vrat:') || findRecipe(day[s])?.tags?.includes('vrat'));
    const existing = { ...plan, [date]: { ...day, locked: [...new Set([...keep, ...cooked])] } };
    const made = await brain('plan', { ...family, ...change, start: date, days: 1, existing });
    const fresh = made.offline ? null : made.plan[date];
    if (fresh) setPlan(p => (p[date] ? { ...p, [date]: withFast(p[date], fresh) } : p));
    return fresh;
  }

  async function change(date, next, saved) {
    setPrefs(p => ({ ...p, ...next }));
    try {
      const fresh = await replan(date, next);
      const label = dayLabel(date, today);
      if (!fresh) notify(saved);
      else if (fresh.fastFor === 'all') notify(`${label}: fasting dishes for everyone.`);
      else if (fresh.fastFor) notify(`${label}: fasting dishes for ${fresh.fastFor}. The others eat as usual.`);
      else notify(`${label}: back to your usual meals.`);
    } catch (e) { notify(e.message); }
  }

  return {
    replan: date => replan(date).then(fresh => fresh && notify(`${dayLabel(date, today)}'s meals are updated.`)).catch(e => notify(e.message)),
    /** `who`: ['*'] for everyone, names, or [] for nobody. */
    choose: (date, who) => change(date, { fastDays: { ...recent(prefs.fastDays), [date]: who } },
      who.length ? `Noted. Ballava suggests fasting dishes ${date === today ? 'today' : `on ${dayLabel(date, today)}`}.` : 'Noted. No fasting that day.'),
    /** "We keep this fast" for a festival. */
    keep(f, on) {
      const { [f.date]: _gone, ...fastDays } = recent(prefs.fastDays);
      const notKept = (prefs.notKept || []).filter(id => id !== f.id);
      return change(f.date, { fastDays, notKept: on ? notKept : [...notKept, f.id] }, on ? `Fasting dishes for ${f.name}.` : `${f.name} is no longer kept as a fast.`);
    },
  };
}

/** Who is fasting that day? Nobody, everyone, or tap names. */
export function FastPicker({ date, ctx }) {
  const { choose } = fastingActions(ctx);
  const now = chosenFor(date, ctx);
  const names = ctx.members.map(m => m.name);
  const chip = (key, on, pick, label) => <button key={key} type="button" className={'chip' + (on ? ' on' : '')} aria-pressed={on} onClick={() => choose(date, pick)}>{label}</button>;
  const toggled = n => {
    const next = names.filter(x => (x === n ? !now.who.includes(x) : now.who.includes(x)));
    return next.length === names.length ? ['*'] : next;
  };
  return (
    <div className="fast-picker" role="group" aria-label={`Who is fasting: ${dayLabel(date)}`}>
      <span className="muted small">Who is fasting?</span>
      <div className="chips wrap">
        {chip('none', !now.any, [], names.length ? 'Nobody' : 'Not fasting')}
        {chip('all', now.all, ['*'], names.length === 1 ? names[0] : names.length ? 'Everyone' : 'Fasting')}
        {names.length > 1 && names.map(n => chip('n' + n, now.who.includes(n), toggled(n), n))}
      </div>
    </div>
  );
}

/** The "🪔 Fasting?" button of a day. Its picker opens under it. */
export function FastToggle({ date, ctx }) {
  const [open, setOpen] = useState(false);
  const now = chosenFor(date, ctx);
  const fast = now.any && { all: now.all, who: now.who };
  return (
    <>
      <button type="button" className="btn link sm fast-toggle" aria-expanded={open} aria-label={`Fasting: ${dayLabel(date)}`} onClick={() => setOpen(o => !o)}>🪔 {fast ? fastsText(fast) : 'Fasting?'}</button>
      {open && <FastPicker date={date} ctx={ctx} />}
    </>
  );
}

/** `within`: only festivals this many days ahead (the Dashboard). Without it, the next six (the Plan tab). */
export function FestivalCard({ ctx, within = null }) {
  const { catalog, prefs, fasts, fastsLoading, findRecipe } = ctx;
  const { keep, replan } = fastingActions(ctx);
  const today = dayKey();
  const last = within == null ? null : addDays(today, within);
  const coming = catalog.festivals.filter(f => f.date >= today && (!last || f.date <= last)).slice(0, 6);
  if (!coming.length) return null;
  const nobody = date => Array.isArray(prefs.fastDays?.[date]) && prefs.fastDays[date].length === 0;
  const kept = f => !(prefs.notKept || []).includes(f.id) && !nobody(f.date);
  return (
    <section className="card festival-card">
      <h3>🪔 Festivals and fasts</h3>
      {coming.map(f => {
        const fast = f.fast && kept(f) ? fasts?.[f.date] : null;
        const ideas = (fast?.ideas || []).map(id => findRecipe(id)).filter(Boolean);
        return (
          <div key={f.id} className="festival-item">
            <div className="festival-row">
              <span><b>{f.name}</b> <span className="muted small">{whenLabel(f.date, today)}</span></span>
              {f.fast && <label className="switch small"><input type="checkbox" checked={kept(f)} onChange={e => keep(f, e.target.checked)} /> We keep this fast</label>}
            </div>
            {f.fast && kept(f) && f.date <= addDays(today, 30) && fasts && !fastsLoading && (fast
              ? <FastToggle date={f.date} ctx={ctx} />
              : <><p className="muted small">Children, and people who are pregnant or diabetic, keep their usual meals unless you choose them.</p><FastPicker date={f.date} ctx={ctx} /></>)}
            {ideas.length > 0 && (
              <>
                <p className="muted small">Fasting dishes that suit you:</p>
                <div className="chips wrap">{ideas.map(r => <button key={r.id} type="button" className="chip" onClick={() => go('recipe/' + r.id)}>{r.name}</button>)}</div>
              </>
            )}
            {f.fast && f.date <= addDays(today, 6) && planNeedsFast(f.date, ctx) && (
              <button type="button" className="btn sm primary" onClick={() => replan(f.date)}>{fast ? 'Plan fasting meals for this day' : 'Plan usual meals for this day'}</button>
            )}
          </div>
        );
      })}
    </section>
  );
}
