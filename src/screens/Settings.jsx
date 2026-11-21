// ⚙️ Settings: everything you can make your own. Saved in your account (prefs), so it follows you everywhere.
import React, { useState } from 'react';
import { Header } from '../ui.jsx';
import { api, go, speak } from '../lib.js';
import { LANGS, t } from '../i18n.js';
import { ACCENTS, CHEF_LANGUAGES, CHEF_LENGTHS, START_PAGES, TEXT_SIZES, THEMES, VOICE_SPEEDS } from '../look.js';

function Choice({ label, options, value, onChange, hint }) {
  return (
    <fieldset className="setting">
      <legend>{label}</legend>
      <div className="chips wrap" role="group" aria-label={label}>
        {options.map(([v, text]) => (
          <button key={String(v)} type="button" className={'chip' + (value === v ? ' on' : '')} aria-pressed={value === v} onClick={() => onChange(v)}>{text}</button>
        ))}
      </div>
      {hint && <p className="muted small">{hint}</p>}
    </fieldset>
  );
}

function Toggle({ label, checked, onChange, hint }) {
  return (
    <label className="setting switch">
      <input type="checkbox" checked={!!checked} onChange={e => onChange(e.target.checked)} />
      <span><b>{label}</b>{hint && <span className="muted small"> {hint}</span>}</span>
    </label>
  );
}

const DEFAULTS = { theme: 'system', accent: 'saffron', textSize: 1, reduceMotion: false, showCalories: true, startPage: 'dashboard',
  readAloud: false, handsFree: false, voiceRate: 0.95, chefLength: 'normal', chefLanguage: 'auto', kcalGoal: 1800 };

export default function Settings({ prefs, setPrefs, filters, setFilters, notify, auth }) {
  const p = { ...DEFAULTS, ...prefs };
  const set = (key, value) => setPrefs(old => ({ ...old, [key]: value }));
  const [goal, setGoal] = useState(String(p.kcalGoal));

  async function clearChats() {
    try { localStorage.removeItem('ballava.chats'); } catch { /* nothing saved */ }
    if (auth.user) { try { await api('chats/delete', { all: true }); } catch (e) { notify(e.message); return; } }
    notify('Your chats with Chef are deleted.');
  }

  return (
    <div className="screen settings">
      <Header title={'⚙️ ' + t('Settings')} back="more" />
      <p className="muted small">{auth.user ? 'Saved in your account, so they follow you to every phone and computer.' : 'Saved on this device. Sign in to keep them everywhere.'}</p>

      <section className="card">
        <h3>🎨 Look</h3>
        <Choice label="Theme" options={THEMES} value={p.theme} onChange={v => set('theme', v)} />
        <fieldset className="setting">
          <legend>Colour</legend>
          <div className="swatches" role="group" aria-label="Colour">
            {ACCENTS.map(([id, name, hex]) => (
              <button key={id} type="button" className={'swatch' + (p.accent === id ? ' on' : '')} style={{ '--sw': hex }} aria-pressed={p.accent === id}
                aria-label={name} title={name} onClick={() => set('accent', id)}><span aria-hidden="true" />{name}</button>
            ))}
          </div>
        </fieldset>
        <Choice label="Text size" options={TEXT_SIZES} value={p.textSize} onChange={v => set('textSize', v)} hint="Larger text is easier to read from across the kitchen." />
        <Toggle label="Less movement" checked={p.reduceMotion} onChange={v => set('reduceMotion', v)} hint="Turns off animations." />
        <Toggle label="Show calories" checked={p.showCalories} onChange={v => set('showCalories', v)} hint="On dishes, recipes and your kitchen. The Dashboard always shows them." />
      </section>

      <section className="card">
        <h3>🏠 Starting the app</h3>
        <Choice label="Open the app on" options={START_PAGES} value={p.startPage} onChange={v => set('startPage', v)} />
        <fieldset className="setting">
          <legend>{t('Language')} (menus)</legend>
          <div className="chips wrap" role="group" aria-label="Language">
            {LANGS.map(([id, label]) => <button key={id} type="button" className={'chip' + ((prefs.lang || 'en') === id ? ' on' : '')} aria-pressed={(prefs.lang || 'en') === id} onClick={() => set('lang', id)}>{label}</button>)}
          </div>
        </fieldset>
      </section>

      <section className="card">
        <h3>🍳 Cooking</h3>
        <Toggle label="Read steps aloud" checked={p.readAloud} onChange={v => set('readAloud', v)} hint="Switched on whenever you start cooking." />
        <Toggle label="Hands-free voice commands" checked={p.handsFree} onChange={v => set('handsFree', v)} hint={'Switched on whenever you start cooking: say "next", "back", "timer 5 minutes".'} />
        <Choice label="Voice speed" options={VOICE_SPEEDS} value={p.voiceRate} onChange={v => { set('voiceRate', v); }} />
        <button className="btn sm" type="button" onClick={() => speak('Step 1. Heat oil in a pan and add the mustard seeds.')}>🔊 Hear it</button>
      </section>

      <section className="card">
        <h3>🥗 Food and health</h3>
        <Toggle label="Vegetarian dishes only" checked={filters.veg} onChange={v => setFilters(f => ({ ...f, veg: v }))} hint="Hides egg, meat and fish everywhere you choose dishes." />
        <form className="setting row" onSubmit={e => { e.preventDefault(); const n = Number(goal); if (n >= 800 && n <= 5000) { set('kcalGoal', n); notify(`Daily goal: ${n} kcal`); } else notify('Choose between 800 and 5000 kcal.'); }}>
          <label>Daily calorie goal per person <input type="number" min="800" max="5000" step="50" value={goal} onChange={e => setGoal(e.target.value)} /></label>
          <button className="btn sm" type="submit">Save</button>
        </form>
        <button className="btn link sm" type="button" onClick={() => go('family')}>Diets, allergies and health goals: Family →</button>
      </section>

      <section className="card">
        <h3>🧑‍🍳 Chef</h3>
        <Choice label="Answers" options={CHEF_LENGTHS} value={p.chefLength} onChange={v => set('chefLength', v)} />
        <Choice label="Chef replies in" options={CHEF_LANGUAGES} value={p.chefLanguage} onChange={v => set('chefLanguage', v)} />
        <button className="btn link sm danger" type="button" onClick={clearChats}>Delete all my chats</button>
      </section>

      <section className="card">
        <h3>🔒 Your data</h3>
        <p className="muted small">Kept for 6 months: diary meals, saved dishes, AI recipes and chats go 6 months after their date.</p>
        <button className="btn link sm" type="button" onClick={() => go('account')}>Download or delete my data: Account →</button>
      </section>

      <button className="btn ghost" type="button" onClick={() => { setPrefs(old => ({ lang: old.lang, name: old.name, observed: old.observed, menuLang: old.menuLang })); notify('Settings are back to normal.'); }}>Reset settings</button>
    </div>
  );
}
