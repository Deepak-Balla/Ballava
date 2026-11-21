import React, { useState } from 'react';
import { Header } from '../ui.jsx';
import { api, whatsappLink } from '../lib.js';
import { wipeDevice } from '../sync.js';
import { t } from '../i18n.js';

function download(data) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
  const a = document.createElement('a');
  a.href = url; a.download = 'ballava-my-data.json'; a.click();
  URL.revokeObjectURL(url);
}

export default function Account({ auth, loadMe, signedOut, notify }) {
  const { user, household } = auth;
  const [code, setCode] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);

  async function run(fn) {
    setBusy(true);
    try { await fn(); } catch (e) { notify(e.message); }
    setBusy(false);
  }

  if (!user) {
    return (
      <div className="screen">
        <Header title={t('Account')} back="more" />
        <div className="card">
          <h3>You're using Ballava on this device only</h3>
          <p>Sign in to keep your data safe if you change phones, and to share one kitchen with your family.</p>
          <button className="btn primary big" onClick={() => { try { localStorage.removeItem('ballava.guest'); } catch { /* ok */ } location.reload(); }}>{t('Sign in')}</button>
          <p className="muted small">What you've added here moves into your account.</p>
        </div>
      </div>
    );
  }

  const invite = `Join our family kitchen on Ballava! Open ${location.origin}${location.pathname}, go to More, Account, and enter the code ${household?.inviteCode}`;

  return (
    <div className="screen">
      <Header title={t('Account')} back="more" />
      <div className="card">
        <h3>{user.name}</h3>
        <p className="muted">{user.email || user.phone}</p>
        <button className="btn ghost" disabled={busy} onClick={() => run(async () => { await api('auth/logout', {}); signedOut(); })}>{t('Sign out')}</button>
        <p className="muted small">Signing out removes your family's data from this device. It stays safe in your account.</p>
      </div>

      {household && (
        <div className="card">
          <h3>{household.name}</h3>
          <p className="muted small">{household.people.join(', ')}</p>
          <p>Share this code so your family can use the same kitchen, plan and list:</p>
          <div className="invite-code" aria-label="Family code">{household.inviteCode}</div>
          <a className="btn whatsapp" href={whatsappLink(invite)} target="_blank" rel="noreferrer">Invite on WhatsApp</a>
        </div>
      )}

      <form className="card form" onSubmit={e => {
        e.preventDefault();
        run(async () => { await api('household/join', { code }); await loadMe({ rejoined: true }); setCode(''); notify('You joined the family kitchen'); });
      }}>
        <h3>Join a family</h3>
        <label>Family code<input value={code} onChange={e => setCode(e.target.value)} autoCapitalize="characters" /></label>
        <button className="btn primary" type="submit" disabled={busy || !code.trim()}>Join</button>
      </form>

      <div className="card form">
        <h3>Your data</h3>
        <p className="small">Everything you do is saved in your account: your kitchen, family, plan, food diary, saved dishes, calorie goal and chats with Chef. Sign in on any phone or computer and it's all there.</p>
        <p className="muted small">🧹 Kept for 6 months: meals in the diary, saved dishes, AI recipes and chats are deleted 6 months after their date, and an account nobody signs in to for 6 months is deleted with its data. Your kitchen, family and plan stay while you use Ballava.</p>
        <button className="btn ghost" disabled={busy} onClick={() => run(async () => download(await api('account/export')))}>Download my data</button>
        <details>
          <summary className="danger">Delete my account</summary>
          <p className="small">This permanently deletes your account. If nobody else is in your family, your family's data is deleted too. This cannot be undone.</p>
          <label>Type DELETE to confirm<input value={confirm} onChange={e => setConfirm(e.target.value)} /></label>
          <button className="btn bachao" disabled={busy || confirm !== 'DELETE'} onClick={() => run(async () => { await api('account/delete', { confirm }); wipeDevice(); signedOut(); })}>Delete forever</button>
        </details>
      </div>
    </div>
  );
}
