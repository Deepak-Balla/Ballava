import React, { useEffect, useState } from 'react';
import { api } from '../lib.js';

function Consent({ value, onChange }) {
  return (
    <label className="check consent">
      <input type="checkbox" checked={value} onChange={e => onChange(e.target.checked)} />
      <span>I agree that Ballava stores my family's food and health details (like diets, allergies and meals) to personalise suggestions. I can download or delete them anytime.</span>
    </label>
  );
}

const csrfToken = () => (document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/) || [])[1] || '';

// Admins sign in to the admin portal (Django's /admin), never to the family app. This form sends them straight there.
function AdminSignIn() {
  const [token, setToken] = useState(csrfToken);
  useEffect(() => { if (!token) api('auth/config').then(() => setToken(csrfToken())).catch(() => {}); }, [token]);
  return (
    <form className="card form admin-signin" method="post" action="admin/login/">
      <p className="muted small">For the people who run Ballava: recipes, ingredients, announcements and users. Family accounts can't sign in here.</p>
      <input type="hidden" name="csrfmiddlewaretoken" value={token} />
      <input type="hidden" name="next" value="/admin/" />
      <label>Admin username<input name="username" autoComplete="username" required /></label>
      <label>Admin password<input name="password" type="password" autoComplete="current-password" required /></label>
      <button className="btn primary big" type="submit">Sign in to admin</button>
      <p className="muted small">Forgot it? On the server, run <code>python manage.py changepassword &lt;username&gt;</code>.</p>
    </form>
  );
}

export default function Login({ onDone, onGuest, server }) {
  const [mode, setMode] = useState('signin'); // signin | signup | phone | admin
  const [form, setForm] = useState({ name: '', email: '', password: '', phone: '', code: '' });
  const [consent, setConsent] = useState(false);
  const [codeSent, setCodeSent] = useState(false);
  const [devCode, setDevCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [config, setConfig] = useState({ phone: false });
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }));

  useEffect(() => { api('auth/config').then(setConfig).catch(() => {}); }, []);

  async function run(fn) {
    setBusy(true); setError('');
    try { await fn(); } catch (e) { setError(e.message); }
    setBusy(false);
  }

  const submit = e => {
    e.preventDefault();
    run(async () => {
      if (mode === 'signup') await api('auth/signup', { name: form.name, email: form.email, password: form.password, consent });
      else if (mode === 'signin') await api('auth/login', { email: form.email, password: form.password });
      else if (!codeSent) {
        const r = await api('auth/otp/request', { phone: form.phone });
        setCodeSent(true);
        if (r.devCode) setDevCode(r.devCode);
        return;
      } else await api('auth/otp/verify', { phone: form.phone, code: form.code, name: form.name, consent });
      await onDone();
    });
  };

  const tab = (id, label) => (
    <button type="button" className={'seg' + (mode === id ? ' on' : '')} aria-pressed={mode === id} onClick={() => { setMode(id); setError(''); setCodeSent(false); }}>{label}</button>
  );

  return (
    <div className="app no-nav">
      <main className="screen">
        <section className="hero">
          <div className="hero-brand">Ballava</div>
          <p className="hero-tag">Cooks with you today. For you tomorrow.</p>
          <p>Stop wondering what to cook. Ballava plans your family's meals, remembers what you made, and keeps everyone's diet in mind.</p>
        </section>

        {!server && <div className="note warn">You seem to be offline. You can still use Ballava on this device.</div>}

        <div className="segments login-tabs" role="group" aria-label="Who is signing in">
          {tab('signin', 'Sign in')}{tab('signup', 'Create account')}{tab('admin', 'Admin')}
        </div>

        {mode === 'admin' ? <AdminSignIn /> : (
        <form className="card form" onSubmit={submit}>
          {config.phone && (
            <div className="chips method" role="group" aria-label="Sign in with">
              <button type="button" className={'chip' + (mode !== 'phone' ? ' on' : '')} aria-pressed={mode !== 'phone'} onClick={() => { setMode(mode === 'phone' ? 'signin' : mode); setCodeSent(false); setError(''); }}>Email</button>
              <button type="button" className={'chip' + (mode === 'phone' ? ' on' : '')} aria-pressed={mode === 'phone'} onClick={() => { setMode('phone'); setError(''); }}>Phone</button>
            </div>
          )}

          {(mode === 'signup' || (mode === 'phone' && codeSent)) && <label>Your name<input value={form.name} onChange={set('name')} autoComplete="name" placeholder="e.g. Asha" /></label>}

          {mode !== 'phone' && <>
            <label>Email<input type="email" value={form.email} onChange={set('email')} autoComplete="email" required /></label>
            <label>Password<input type="password" value={form.password} onChange={set('password')} autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} required minLength={mode === 'signup' ? 8 : undefined} /></label>
          </>}

          {mode === 'phone' && <label>Mobile number<input type="tel" value={form.phone} onChange={set('phone')} autoComplete="tel" placeholder="98765 43210" disabled={codeSent} required /></label>}
          {mode === 'phone' && codeSent && <label>6-digit code<input inputMode="numeric" value={form.code} onChange={set('code')} autoComplete="one-time-code" maxLength={6} required /></label>}
          {devCode && codeSent && <div className="note info">Test mode: no SMS was sent. Your code is <b>{devCode}</b>.</div>}

          {(mode === 'signup' || (mode === 'phone' && codeSent)) && <Consent value={consent} onChange={setConsent} />}
          {mode === 'phone' && codeSent && <p className="muted small">Already have an account on this number? Just enter the code.</p>}

          {error && <div className="note bad" role="alert">{error}</div>}
          <button className="btn primary big" type="submit" disabled={busy}>
            {busy ? 'Please wait…' : mode === 'signin' ? 'Sign in' : mode === 'signup' ? 'Create account' : codeSent ? 'Verify and continue' : 'Send code'}
          </button>
          {mode === 'phone' && <p className="muted small">New or returning, the same code works: a new number creates an account.</p>}
        </form>
        )}

        <button className="btn link center-btn" onClick={onGuest}>Continue without an account</button>
        <p className="muted small center">Without an account, your data stays on this device only and can't be shared with family.</p>
      </main>
    </div>
  );
}
