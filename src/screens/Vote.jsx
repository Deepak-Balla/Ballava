import React, { useEffect, useRef, useState } from 'react';
import { MealVote, castVote, getBallot } from '../votes.jsx';

const savedName = () => { try { return localStorage.getItem('ballava.voterName') || ''; } catch { return ''; } };

// The public voting page, opened from a WhatsApp link with no account needed.
// A link to one dish (`choice`, like "0-2": meal 0, dish 2) votes for it straight away.
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

  const done = ballot?.meals.filter(m => m.mine).length || 0;
  return (
    <div className="app no-nav vote-page">
      <main className="screen">
        <div className="hero-brand">Ballava</div>
        {error && <div className="note bad" role="alert">{error}</div>}
        {justVoted && !error && <div className="note info" role="status">✓ Your vote for <b>{justVoted}</b> is in. You can change your mind.</div>}
        {ballot && (
          <>
            <form className="card row nowrap" onSubmit={saveName}>
              <input aria-label="Your name" value={name} maxLength={30} onChange={e => setName(e.target.value)} placeholder="Your name (optional)" />
              <button className="btn sm" type="submit">Save</button>
            </form>
            <section className="card">
              <h2>What should we eat?</h2>
              <p className="muted small">{ballot.meals.every(m => m.closed) ? 'This vote has closed.' : `Tap your favourite${ballot.meals.length > 1 ? ` for each meal (${done} of ${ballot.meals.length} done)` : ''}.`}</p>
              {ballot.meals.map(m => <MealVote key={m.token} meal={m} onVote={vote} />)}
            </section>
          </>
        )}
      </main>
    </div>
  );
}
