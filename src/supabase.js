// Talks to Supabase Auth (email with a code, password reset, Google). Used only when the server has it switched on.
// Nothing from Supabase is kept on this device: the short-lived token it gives goes straight to our own server
// (api('auth/supabase')), which starts the normal Ballava session.

const MESSAGES = {
  invalid_credentials: 'That email or password is not right.',
  email_not_confirmed: 'Please confirm your email first. We can send you a new code.',
  user_already_exists: 'An account with this email already exists. Please sign in.',
  email_exists: 'An account with this email already exists. Please sign in.',
  otp_expired: 'That code is not right, or it has expired. Please check it, or ask for a new one.',
  weak_password: 'Please choose a stronger password (at least 8 characters, not a common one).',
  same_password: 'That is already your password. Please choose a different one.',
  over_email_send_rate_limit: 'Too many emails were sent just now. Please wait a few minutes and try again.',
  over_request_rate_limit: 'Too many tries. Please wait a few minutes and try again.',
  signup_disabled: 'New accounts are closed right now.',
  email_address_invalid: 'Please enter a valid email address.',
  email_address_not_authorized: "Emails can't be sent to this address yet. (For the owner: set up custom SMTP in Supabase.)",
  user_banned: 'This account cannot sign in.',
};

async function call(config, path, body, { method = 'POST', token } = {}) {
  let res;
  try {
    res = await fetch(config.url + path, {
      method, headers: { 'Content-Type': 'application/json', apikey: config.key, ...(token ? { Authorization: 'Bearer ' + token } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch { throw new Error('The sign-in service could not be reached. Please check your connection and try again.'); }
  let data = {};
  try { data = await res.json(); } catch { /* an empty answer */ }
  if (!res.ok) {
    const code = data.error_code || data.error || '';
    throw Object.assign(new Error(MESSAGES[code] || (res.status === 429 ? MESSAGES.over_request_rate_limit : data.msg || data.error_description || 'Signing in did not work. Please try again.')), { code });
  }
  return data;
}

const back = () => location.origin + '/';

/** A token straight away, or null when an emailed code must be typed first. */
export async function signUp(config, { email, password, name }) {
  const data = await call(config, `/signup?redirect_to=${encodeURIComponent(back())}`, { email, password, data: { name } });
  return data.access_token || null;
}
export const signIn = (config, { email, password }) => call(config, '/token?grant_type=password', { email, password }).then(d => d.access_token);
export const resendCode = (config, email) => call(config, `/resend?redirect_to=${encodeURIComponent(back())}`, { email, type: 'signup' });
export const sendReset = (config, email) => call(config, `/recover?redirect_to=${encodeURIComponent(back())}`, { email });
/** `type`: 'signup' or 'recovery'. */
export const checkCode = (config, { email, token, type }) => call(config, '/verify', { email, token: token.trim(), type }).then(d => d.access_token);
export const setPassword = (config, token, password) => call(config, '/user', { password }, { method: 'PUT', token });
// Our own session has started, so this sign-in at Supabase isn't needed any more.
export const finish = (config, token) => call(config, '/logout?scope=local', null, { token }).catch(() => {});

// ---- Google (the browser goes to Google and comes back with a one-time code; only this browser holds the key to use it)
const VERIFIER = 'ballava.pkce';
const base64 = bytes => btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
export async function startGoogle(config) {
  const verifier = base64(crypto.getRandomValues(new Uint8Array(48)));
  const challenge = base64(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))));
  localStorage.setItem(VERIFIER, verifier);
  location.href = `${config.url}/authorize?${new URLSearchParams({ provider: 'google', redirect_to: back(), code_challenge: challenge, code_challenge_method: 's256' })}`;
}
async function finishGoogle(config, code) {
  const verifier = localStorage.getItem(VERIFIER);
  localStorage.removeItem(VERIFIER);
  if (!verifier) throw new Error('Please sign in again from this browser.');
  return (await call(config, '/token?grant_type=pkce', { auth_code: code, code_verifier: verifier })).access_token;
}

// ---- Coming back from Google, or from a link in an email
let returned = null;
/** Call once, before the app starts: takes the sign-in details out of the address bar. */
export function captureReturn() {
  const query = new URLSearchParams(location.search);
  const hash = new URLSearchParams(location.hash.replace(/^#\/?/, ''));
  if (hash.get('access_token')) returned = { token: hash.get('access_token'), type: hash.get('type') || '' };
  else if (query.get('code')) returned = { code: query.get('code') };
  else if (query.get('error') || hash.get('error')) {
    const from = query.get('error') ? query : hash;
    returned = { error: from.get('error_code') === 'otp_expired' ? 'That link has expired or was already used. Please sign in, or ask for a new code.' : from.get('error_description') || 'Signing in was cancelled.' };
  }
  if (returned) window.history.replaceState(null, '', location.pathname);
}
export const hasReturned = () => !!returned;
/** {token, type} from what came back, once. Throws when it failed. */
export async function takeReturned(config) {
  const r = returned;
  returned = null;
  if (!r) return null;
  if (r.error) throw new Error(r.error);
  return r.token ? r : { token: await finishGoogle(config, r.code), type: 'google' };
}
