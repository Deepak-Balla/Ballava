import React from 'react';
import { BY_ID } from '../shared/ingredients.mjs';

export const ingName = id => BY_ID[id]?.name || id;

export function DietDot({ diet }) {
  const label = diet === 'veg' ? 'Vegetarian' : diet === 'egg' ? 'Contains egg' : 'Non-vegetarian';
  return <span className={'diet-dot ' + diet} title={label} aria-label={label} />;
}

export function Spice({ level }) {
  return <span className="spice" title={['', 'Mild', 'Medium', 'Hot'][level]}>{['', 'Mild', 'Medium', 'Hot'][level]}</span>;
}

export function Stars({ value = 0, onChange, size = 'md' }) {
  return (
    <div className={'stars ' + size} role="radiogroup" aria-label="Rating">
      {[1, 2, 3, 4, 5].map(n => (
        <button key={n} type="button" role="radio" aria-checked={value === n} aria-label={`${n} star${n > 1 ? 's' : ''}`}
          className={n <= value ? 'on' : ''} onClick={() => onChange && onChange(n)} disabled={!onChange}>★</button>
      ))}
    </div>
  );
}

export function Header({ title, back, right }) {
  return (
    <header className="topbar">
      {back ? <button className="icon-btn" onClick={() => { location.hash = '#/' + (typeof back === 'string' ? back : 'home'); }} aria-label="Back">‹</button> : <span className="brand-mark">B</span>}
      <h1>{title}</h1>
      <div className="topbar-right">{right}</div>
    </header>
  );
}

export function Empty({ title, children }) {
  return <div className="empty"><h3>{title}</h3>{children}</div>;
}

export function expiryLabel(days) {
  if (days === null) return { text: 'Keeps well', cls: 'ok' };
  if (days < 0) return { text: 'Expired', cls: 'bad' };
  if (days === 0) return { text: 'Use today', cls: 'bad' };
  if (days === 1) return { text: '1 day left', cls: 'warn' };
  if (days === 2) return { text: '2 days left', cls: 'warn' };
  return { text: `${days} days left`, cls: 'ok' };
}
