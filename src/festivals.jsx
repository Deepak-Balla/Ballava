// 🪔 Festivals and fasts added in the admin portal: shown on the Dashboard and the Plan tab.
import React from 'react';
import { SLOTS, WEEKDAYS, addDays, dayKey } from './catalog.js';
import { brain } from './lib.js';

export const festivalsOn = (catalog, date) => catalog.festivals.filter(f => f.date === date);

export function whenLabel(date, today = dayKey()) {
  const days = Math.round((new Date(date + 'T12:00:00') - new Date(today + 'T12:00:00')) / 86400000);
  const d = new Date(date + 'T12:00:00');
  const name = `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${d.toLocaleString('en', { month: 'short' })}`;
  return days === 0 ? `Today, ${name}` : days === 1 ? `Tomorrow, ${name}` : `${name}, in ${days} days`;
}

/** `within`: only festivals this many days ahead (the Dashboard). Without it, the next six (the Plan tab). */
export function FestivalCard({ catalog, prefs, setPrefs, plan, setPlan, family, notify, within = null }) {
  const today = dayKey();
  const last = within == null ? null : addDays(today, within);
  const coming = catalog.festivals.filter(f => f.date >= today && (!last || f.date <= last)).slice(0, 6);
  const observed = prefs.observed || [];
  if (!coming.length) return null;

  // Keeping a fast adds a separate vrat meal to that day's plan straight away. Every other planned meal stays as it is.
  async function keep(f, on) {
    const next = on ? [...observed, f.id] : observed.filter(x => x !== f.id);
    setPrefs(p => ({ ...p, observed: next }));
    if (!plan[f.date] || f.date > addDays(today, 6)) {
      notify(on ? `Noted. Ballava adds a vrat meal for ${f.name} when you plan that day.` : `${f.name} is no longer kept as a fast.`);
      return;
    }
    try {
      const existing = Object.fromEntries(Object.entries(plan).map(([d, day]) => [d, { ...day, locked: SLOTS.filter(s => day[s]) }]));
      const made = await brain('plan', { ...family, start: today, existing, observed: next });
      if (made.offline) return;
      const fresh = made.plan[f.date] || {};
      setPlan(p => ({ ...p, [f.date]: { ...p[f.date], fast: fresh.fast || {}, festival: fresh.festival } }));
      notify(on ? `Added a vrat meal for ${f.name} to your plan.` : `Removed the vrat meal for ${f.name}.`);
    } catch (e) { notify(e.message); }
  }

  return (
    <section className="card festival-card">
      <h3>🪔 Festivals and fasts</h3>
      {coming.map(f => (
        <div key={f.id} className="festival-row">
          <span><b>{f.name}</b> <span className="muted small">{whenLabel(f.date, today)}</span></span>
          {f.fast && (
            <label className="switch small"><input type="checkbox" checked={observed.includes(f.id)} onChange={e => keep(f, e.target.checked)} /> We keep this fast</label>
          )}
        </div>
      ))}
      {coming.some(f => f.fast) && <p className="muted small">Tick a fast to get a vrat meal planned for that day.</p>}
    </section>
  );
}
