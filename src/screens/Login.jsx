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

export default function Login({ onDone, onGuest, server }) {
  const [mode, setMode] = useState('signin'); // signin | signup | phone
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

        <form className="card form" onSubmit={submit}>
          <div className="segments" role="group" aria-label="Sign-in method">
            {tab('signin', 'Sign in')}{tab('signup', 'Create account')}{config.phone && tab('phone', 'Phone')}
          </div>

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
        </form>

        <button className="btn link center-btn" onClick={onGuest}>Continue without an account</button>
        <p className="muted small center">Without an account, your data stays on this device only and can't be shared with family.</p>
      </main>
    </div>
  );
}
