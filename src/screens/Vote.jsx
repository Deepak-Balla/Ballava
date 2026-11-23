import React, { useEffect, useRef, useState } from 'react';
import { dayLabel } from '../fasting.jsx';
import { MealVote, castVote, getBallot, slotTitle } from '../votes.jsx';

const savedName = () => { try { return localStorage.getItem('ballava.voterName') || ''; } catch { return ''; } };

// The public voting page, opened from the WhatsApp link with no account needed: every meal that was shared, day by day.
// (Older messages had a link per dish: `choice`, like "0-2", is meal 0, dish 2, and votes for it straight away.)
export default function Vote({ group, choice }) {
  const [ballot, setBallot] = useState(null);
  const [name, setName] = useState(savedName);
  const [justVoted, setJustVoted] = useState('');
  const [error, setError] = useState('');
  const started = useRef('');

  const put = meal => setBallot(b => ({ ...b, meals: b.meals.map(m => (m.token === meal.token ? meal : m)) }));
  async function vote(meal, optionId, as = name) {
    try {
      put(await castVote(meal, optionId, as.trim()));
      setError('');
      setJustVoted(meal.options.find(o => o.id === optionId)?.name || '');
    } catch (e) { setError(e.message); }
  }

  useEffect(() => {
    let live = true;
    const load = () => getBallot(group).then(b => { if (live) setBallot(b); return b; });
    load().then(b => {
      const [m, o] = (choice || '').split('-').map(Number);
      const meal = b.meals[m];
      if (!choice || !meal?.options[o] || started.current === choice) return;
      started.current = choice;
      window.history.replaceState(null, '', `#/vote/${group}`); // a reload must not vote again over a changed mind
      vote(meal, meal.options[o].id);
    }).catch(e => setError(e.message));
    const id = setInterval(() => load().catch(() => {}), 10000);
    return () => { live = false; clearInterval(id); };
  }, [group, choice]);

  // The name is optional; adding it later puts it on the votes already cast.
  function saveName(e) {
    e.preventDefault();
    try { localStorage.setItem('ballava.voterName', name.trim()); } catch { /* private mode */ }
    for (const m of ballot.meals) if (m.mine && !m.closed) vote(m, m.mine);
  }

  const meals = ballot?.meals || [];
  const done = meals.filter(m => m.mine).length;
  const closed = meals.length > 0 && meals.every(m => m.closed);
  const dates = [...new Set(meals.map(m => m.date))];
  return (
    <div className="app no-nav vote-page">
      <main className="screen">
        <div className="hero-brand">Ballava</div>
        {error && <div className="note bad" role="alert">{error}</div>}
        {ballot && (
          <>
            <form className="card row nowrap" onSubmit={saveName}>
              <input aria-label="Your name" value={name} maxLength={30} onChange={e => setName(e.target.value)} placeholder="Your name (optional)" />
              <button className="btn sm" type="submit">Save</button>
            </form>
            <h2>What should we eat?</h2>
            {ballot.note && <p className="vote-note">“{ballot.note}”</p>}
            <p className="muted small">{closed ? 'This vote has closed.' : `Tap your favourite${meals.length > 1 ? ' for each meal' : ''}. Votes are sent as you tap.`}</p>
            {dates.map(d => (
              <section key={d} className="card">
                {d && <h3>{dayLabel(d)}</h3>}
                {meals.filter(m => m.date === d).map(m => <MealVote key={m.token} meal={m} onVote={vote} title={d ? slotTitle(m) : m.title} facts />)}
              </section>
            ))}
            {!closed && (
              <div className="vote-status" role="status">
                <b>{done === meals.length ? '🎉 All done! ' : ''}{done} of {meals.length} chosen</b>
                <span>{justVoted ? <>✓ Your vote for <b>{justVoted}</b> is in. You can change your mind.</> : 'Your votes show up for the family at once.'}</span>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
