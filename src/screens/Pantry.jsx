import React, { useState } from 'react';
import { INGREDIENTS, CATEGORIES, KITS, ASSUMED } from '../../shared/ingredients.mjs';
import { parseIngredients, daysLeft, useSoon } from '../../shared/engine.mjs';
import { Header, ingName, expiryLabel } from '../ui.jsx';
import { SpeechRec, listenOnce } from '../lib.js';

const DAY = 86400000;

export default function Pantry({ pantry, setPantry, addToPantry, notify }) {
  const [text, setText] = useState('');
  const [listening, setListening] = useState(false);
  const [cat, setCat] = useState('Vegetables');
  const [confirmClear, setConfirmClear] = useState(false);
  const have = new Set(pantry.map(p => p.id));

  function addText(t) {
    const { found, unknown } = parseIngredients(t);
    const wanted = found.filter(id => !ASSUMED.includes(id));
    const added = addToPantry(wanted);
    const already = wanted.filter(id => !added.includes(id));
    const parts = [];
    if (added.length) parts.push(`Added ${added.map(ingName).join(', ')}`);
    if (already.length) parts.push(`Already have ${already.map(ingName).join(', ')}`);
    if (unknown.length) parts.push(`Didn't recognise: ${unknown.join(', ')}`);
    notify(parts.join('. ') || 'Type ingredients separated by commas.');
    if (found.length) setText('');
    return added;
  }

  function mic() {
    setListening(true);
    listenOnce(t => { setText(t); addText(t); }, () => setListening(false));
  }

  const toggle = id => {
    if (have.has(id)) setPantry(pantry.filter(p => p.id !== id));
    else addToPantry([id]);
  };
  const shift = (id, days) => setPantry(pantry.map(p => {
    if (p.id !== id) return p;
    const base = p.expiresAt ?? Date.now();
    return { ...p, expiresAt: base + days * DAY };
  }));

  const soonIds = new Set(useSoon(pantry).map(p => p.id));
  const sorted = [...pantry].sort((a, b) => {
    const da = daysLeft(a), db = daysLeft(b);
    return (da ?? 999) - (db ?? 999) || ingName(a.id).localeCompare(ingName(b.id));
  });

  return (
    <div className="screen">
      <Header title="My kitchen" />
      <form className="add-bar" onSubmit={e => { e.preventDefault(); addText(text); }}>
        <input value={text} onChange={e => setText(e.target.value)} aria-label="Add ingredients"
          placeholder="e.g. 2 tamatar, pyaz, paneer, leftover rice" />
        {SpeechRec && <button type="button" className={'icon-btn mic' + (listening ? ' live' : '')} onClick={mic} aria-label="Speak ingredients">🎤</button>}
        <button className="btn primary" type="submit">Add</button>
      </form>
      <p className="muted small">Tip: use any language's names: aloo, palak, kodi, pesarapappu… Salt, oil and water are always assumed.</p>

      <div className="kits">
        {KITS.map(k => (
          <button key={k.id} className="btn ghost sm" onClick={() => { const a = addToPantry(k.items); notify(a.length ? `Added ${a.length} items from ${k.name}` : `${k.name} already added`); }}>+ {k.name}</button>
        ))}
      </div>

      <h3 className="section-title">In your kitchen <span className="count">{pantry.length}</span></h3>
      {pantry.length === 0 && <p className="muted">Nothing yet. Type above, tap a kit, or pick from the list below.</p>}
      <ul className="pantry-list">
        {sorted.map(p => {
          const d = daysLeft(p);
          const lab = expiryLabel(d);
          return (
            <li key={p.id} className={soonIds.has(p.id) ? 'soon' : ''}>
              <span className="p-name">{ingName(p.id)}</span>
              <span className={'p-exp ' + lab.cls}>{lab.text}</span>
              {d !== null && (
                <span className="p-adjust">
                  <button className="icon-btn sm" onClick={() => shift(p.id, -1)} aria-label={`One day less for ${ingName(p.id)}`}>−</button>
                  <button className="icon-btn sm" onClick={() => shift(p.id, 1)} aria-label={`One day more for ${ingName(p.id)}`}>+</button>
                </span>
              )}
              <button className="icon-btn sm remove" onClick={() => toggle(p.id)} aria-label={`Remove ${ingName(p.id)}`}>✕</button>
            </li>
          );
        })}
      </ul>
      {pantry.length > 0 && (
        <button className="btn link danger" onClick={() => { if (confirmClear) { setPantry([]); setConfirmClear(false); notify('Kitchen cleared'); } else { setConfirmClear(true); setTimeout(() => setConfirmClear(false), 4000); } }}>
          {confirmClear ? 'Tap again to clear everything' : 'Clear kitchen'}
        </button>
      )}

      <h3 className="section-title">Pick from the list</h3>
      <div className="chips scroll">
        {CATEGORIES.filter(c => c !== 'Basics & Sauces' || true).map(c => (
          <button key={c} className={'chip' + (cat === c ? ' on' : '')} onClick={() => setCat(c)}>{c}</button>
        ))}
      </div>
      <div className="chips wrap">
        {INGREDIENTS.filter(i => i.category === cat && !ASSUMED.includes(i.id)).map(i => (
          <button key={i.id} className={'chip ing' + (have.has(i.id) ? ' on' : '')} aria-pressed={have.has(i.id)} onClick={() => toggle(i.id)}>
            {have.has(i.id) ? '✓ ' : '+ '}{i.name}
          </button>
        ))}
      </div>
    </div>
  );
}
