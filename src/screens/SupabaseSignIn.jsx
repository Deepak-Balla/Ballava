import React, { useEffect, useState } from 'react';
import { api } from '../lib.js';
import { checkCode, finish, hasReturned, resendCode, sendReset, setPassword, signIn, signUp, startGoogle, takeReturned } from '../supabase.js';

// Signing in with Supabase: email and password (with an emailed code for new accounts and forgotten passwords), or Google.
// `mode` is 'signin' or 'signup'. `Consent` is the same agreement every new account sees.
export default function SupabaseSignIn({ config, mode, setMode, onDone, Consent }) {
  const [stage, setStage] = useState('form'); // form | code | forgot | reset | newpass | consent
  const [form, setForm] = useState({ name: '', email: '', password: '', code: '' });
  const [consent, setConsent] = useState(false);
  const [token, setToken] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }));
  const go = (next, note = '') => { setStage(next); setInfo(note); setError(''); setForm(f => ({ ...f, code: '', password: next === 'form' || next === 'code' ? f.password : '' })); };

  async function run(fn) {
    setBusy(true); setError('');
    try { await fn(); } catch (e) { setError(e.message); }
    setBusy(false);
  }
  // Hand Supabase's token to our own server, which starts the session. New people agree to how their data is stored first.
  async function enter(t, agreed = consent) {
    const r = await api('auth/supabase', { accessToken: t, name: form.name, consent: agreed });
    if (r.needsConsent) {
      setToken(t);
      setForm(f => ({ ...f, name: f.name || r.name, email: r.email }));
      go('consent');
      return;
    }
    finish(config, t);
    await onDone();
  }

  useEffect(() => { // back from Google, or from a link in an email
    if (!hasReturned()) return;
    run(async () => {
      const r = await takeReturned(config);
      if (r.type === 'recovery') { setToken(r.token); go('newpass'); } else await enter(r.token);
    });
  }, []);
  useEffect(() => { setStage(s => (s === 'consent' || s === 'newpass' ? s : 'form')); setError(''); setInfo(''); }, [mode]);

  const submit = e => {
    e.preventDefault();
    run(async () => {
      const email = form.email.trim().toLowerCase();
      if (stage === 'consent') return enter(token, true);
      if (stage === 'forgot') { await sendReset(config, email); return go('reset', `If ${email} has an account, an email is on its way. Tap its link, or type its code here. Check spam too.`); }
      if (stage === 'code') return enter(await checkCode(config, { email, token: form.code, type: 'signup' }), true);
      if (stage === 'reset') { // the code works once, so keep what it gave us even if the new password is refused
        const t = await checkCode(config, { email, token: form.code, type: 'recovery' });
        setToken(t);
        setStage('newpass');
        setInfo('');
        await setPassword(config, t, form.password);
        return enter(t);
      }
      if (stage === 'newpass') { await setPassword(config, token, form.password); return enter(token); }
      if (mode === 'signup') {
        if (!consent) throw new Error("Please agree to how Ballava stores your family's food and health details.");
        const t = await signUp(config, { email, password: form.password, name: form.name.trim() });
        return t ? enter(t, true) : go('code', `We sent an email to ${email}. Tap the link in it, or type its code here. Check spam too.`);
      }
      try { return await enter(await signIn(config, { email, password: form.password })); } catch (err) {
        if (err.code !== 'email_not_confirmed') throw err;
        await resendCode(config, email);
        return go('code', `Your email isn't confirmed yet. We sent a new email to ${email}: tap its link, or type its code here.`);
      }
    });
  };

  const email = <label>Email<input type="email" value={form.email} onChange={set('email')} autoComplete="email" required disabled={stage === 'code' || stage === 'reset'} /></label>;
  const password = label => <label>{label}<input type="password" value={form.password} onChange={set('password')} autoComplete={label === 'Password' && mode === 'signin' ? 'current-password' : 'new-password'} required minLength={label === 'Password' && mode === 'signin' ? undefined : 8} /></label>;
  const code = <label>Code from the email<input inputMode="numeric" value={form.code} onChange={set('code')} autoComplete="one-time-code" maxLength={10} required autoFocus /></label>;
  const name = <label>Your name<input value={form.name} onChange={set('name')} autoComplete="name" placeholder="e.g. Asha" required /></label>;
  const label = { consent: 'Agree and continue', forgot: 'Email me a code', code: 'Confirm and continue', reset: 'Set new password', newpass: 'Set new password', form: mode === 'signup' ? 'Create account' : 'Sign in' }[stage];
  const titles = { consent: 'Welcome to Ballava!', code: 'Confirm your email', forgot: 'Forgot your password?', reset: 'Choose a new password', newpass: 'Choose a new password' };

  return (
    <form className="card form" onSubmit={submit}>
      {titles[stage] && <h3>{titles[stage]}</h3>}
      {info && <div className="note info" role="status">{info}</div>}

      {stage === 'form' && config.google && window.isSecureContext && ( /* Google needs https (or localhost) */
        <>
          <button type="button" className="btn big google" disabled={busy} onClick={() => run(() => startGoogle(config))}>
            <svg viewBox="0 0 48 48" width="20" height="20" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.9 6.2C12.4 13.7 17.7 9.5 24 9.5z" /><path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.7 6C44.1 38 46.5 31.8 46.5 24.5z" /><path fill="#FBBC05" d="M10.5 28.6c-.5-1.5-.8-3-.8-4.6s.3-3.2.8-4.6l-7.9-6.2C.9 16.5 0 20.1 0 24s.9 7.5 2.6 10.8l7.9-6.2z" /><path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.7-6c-2.2 1.5-5 2.3-8.2 2.3-6.3 0-11.6-4.2-13.5-9.9l-7.9 6.2C6.5 42.6 14.6 48 24 48z" /></svg>
            Continue with Google
          </button>
          <p className="muted small center">or with your email</p>
        </>
      )}

      {stage === 'form' && mode === 'signup' && name}
      {(stage === 'form' || stage === 'forgot' || stage === 'code' || stage === 'reset') && email}
      {stage === 'form' && password('Password')}
      {(stage === 'code' || stage === 'reset') && code}
      {(stage === 'reset' || stage === 'newpass') && password('New password')}
      {stage === 'consent' && <>{form.email && <p className="muted small">{form.email}</p>}{name}</>}
      {((stage === 'form' && mode === 'signup') || stage === 'consent') && <Consent value={consent} onChange={setConsent} />}

      {error && <div className="note bad" role="alert">{error}</div>}
      <button className="btn primary big" type="submit" disabled={busy || (stage === 'consent' && !consent)}>{busy ? 'Please wait…' : label}</button>

      {stage === 'form' && mode === 'signin' && <button type="button" className="btn link center-btn" onClick={() => go('forgot')}>Forgot your password?</button>}
      {stage === 'code' && (
        <>
          <button type="button" className="btn link center-btn" disabled={busy} onClick={() => run(async () => { await resendCode(config, form.email.trim().toLowerCase()); setInfo('A new email is on its way.'); })}>Send the email again</button>
          <p className="muted small center">No email? If you already have an account, nothing is sent. Sign in, or reset your password, instead.</p>
        </>
      )}
      {stage !== 'form' && <button type="button" className="btn link center-btn" onClick={() => { setToken(''); go('form'); setMode('signin'); }}>Back to sign in</button>}
    </form>
  );
}
