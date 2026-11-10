import React, { useEffect, useState } from 'react';
import { getCatalog } from '../catalog.js';
import { api } from '../lib.js';
import { Header } from '../ui.jsx';

// Offline fallback: a simple word search over the fixes kept on the phone.
const localSearch = q => {
  const words = q.toLowerCase().split(/W+/).filter(w => w.length > 2);
  const all = getCatalog().rescues;
  return words.length ? all.filter(r => words.some(w => (r.title + ' ' + r.keywords).toLowerCase().includes(w))) : all;
};

export function BachaoList() {
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(null);
  const [items, setItems] = useState(() => getCatalog().rescues);
  useEffect(() => {
    // Python (kitchen/engine.py -> find_rescue) finds the best fixes.
    let live = true;
    const timer = setTimeout(() => {
      api('rescue', { text: q }).then(r => live && setItems(r)).catch(() => live && setItems(localSearch(q)));
    }, q ? 200 : 0);
    return () => { live = false; clearTimeout(timer); };
  }, [q]);
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
