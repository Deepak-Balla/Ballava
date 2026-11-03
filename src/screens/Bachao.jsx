import React, { useState } from 'react';
import { findRescue } from '../../shared/engine.mjs';
import { Header } from '../ui.jsx';

export function BachaoList() {
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(null);
  const items = findRescue(q);
  return (
    <div className="bachao">
      <input className="search" value={q} onChange={e => setQ(e.target.value)} placeholder="Search: salty, burnt, watery, spicy…" aria-label="Search problems" />
      {items.length === 0 && <p className="muted">No match. Try "salty", "burnt" or "safe".</p>}
      <div className="rescue-list">
        {items.map(r => (
          <div key={r.id} className={'rescue' + (open === r.id ? ' open' : '')}>
            <button className="rescue-head" onClick={() => setOpen(open === r.id ? null : r.id)} aria-expanded={open === r.id}>
              {r.title}<span aria-hidden="true">{open === r.id ? '−' : '+'}</span>
            </button>
            {open === r.id && (
              <div className="rescue-body">
                <ol>{r.fixes.map((f, i) => <li key={i}>{f}</li>)}</ol>
                {r.myth && <div className="note info"><b>Myth check:</b> {r.myth}</div>}
                {r.safety && <div className="note bad"><b>Safety:</b> {r.safety}</div>}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Bachao() {
  return (
    <div className="screen">
      <Header title="Bachao! Kitchen rescue" />
      <p className="muted">Something went wrong? Don't panic. Most dishes can be saved.</p>
      <BachaoList />
    </div>
  );
}
