import React, { useEffect, useState } from 'react';
import { api } from '../lib.js';

function voterId() {
  try {
    let id = localStorage.getItem('ballava.voter');
    if (!id) { id = Date.now().toString(36) + Math.random().toString(36).slice(2, 12); localStorage.setItem('ballava.voter', id); }
    return id;
  } catch { return Math.random().toString(36).slice(2); }
}

// The public voting page: opened from a WhatsApp link, with no account needed.
export default function Vote({ token }) {
  const [poll, setPoll] = useState(null);
  const [mine, setMine] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => { api('polls/' + token).then(setPoll).catch(e => setError(e.message)); }, [token]);

  async function vote(optionId) {
    try { setPoll(await api(`polls/${token}/vote`, { voter: voterId(), optionId })); setMine(optionId); } catch (e) { setError(e.message); }
  }

  return (
    <div className="app no-nav">
      <main className="screen">
        <div className="hero-brand">Ballava</div>
        {error && <div className="note bad">{error}</div>}
        {poll && (
          <section className="card">
            <h2>{poll.title}</h2>
            <p className="muted small">{poll.closed ? 'This vote has closed.' : 'Tap your favourite. You can change your mind.'}</p>
            <div className="stack">
              {poll.options.map(o => (
                <button key={o.id} className={'vote-option' + (mine === o.id ? ' on' : '')} disabled={poll.closed} aria-pressed={mine === o.id} onClick={() => vote(o.id)}>
                  <span>{o.name}</span><b>{o.votes}</b>
                </button>
              ))}
            </div>
            {mine && <p className="center">Thanks! Your vote is in.</p>}
          </section>
        )}
      </main>
    </div>
  );
}
