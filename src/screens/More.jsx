import React from 'react';
import { Header } from '../ui.jsx';
import { go } from '../lib.js';
import { t, LANGS } from '../i18n.js';

export default function More({ prefs, setPrefs, auth, members, savedDishes }) {
  const links = [
    ['saved', '❤️', 'Saved dishes', savedDishes.length ? `${savedDishes.length} saved` : 'Tap ♡ on any dish to keep it here'],
    ['family', '👪', t('Family'), members.length ? `${members.length} added` : 'Diets, allergies and goals'],
    ['bachao', '🛟', 'Bachao!', 'Rescue a dish that went wrong'],
    ['ai', '✨', 'AI Chef', 'Invent a dish, or scan your fridge'],
    ['account', '👤', t('Account'), auth.user ? auth.user.name : 'Sign in to share with family'],
  ];
  return (
    <div className="screen">
      <Header title={t('More')} />
      <div className="menu">
        {links.map(([id, icon, label, hint]) => (
          <button key={id} className="menu-item" onClick={() => go(id)} aria-label={label}>
            <span className="menu-icon" aria-hidden="true">{icon}</span>
            <span><b>{label}</b><span className="muted small">{hint}</span></span>
            <span className="muted" aria-hidden="true">›</span>
          </button>
        ))}
      </div>
      <div className="card">
        <h3>{t('Language')}</h3>
        <div className="chips wrap" role="group" aria-label="Language">
          {LANGS.map(([id, label]) => <button key={id} className={'chip' + ((prefs.lang || 'en') === id ? ' on' : '')} aria-pressed={(prefs.lang || 'en') === id} onClick={() => setPrefs(p => ({ ...p, lang: id }))}>{label}</button>)}
        </div>
        <p className="muted small">Menus and headings change. Recipe steps stay in English for now.</p>
      </div>
    </div>
  );
}
