"""Sign-in with Supabase Auth (optional): email with a code, password reset, and Google.

How it works: the sign-in screen talks to Supabase directly (src/supabase.js). Supabase checks the password, the emailed
code or Google, and gives the browser a short-lived token. The browser hands that token to us once; we ask Supabase who it
belongs to, and then start our own session (a cookie that page scripts can't read), exactly as before. Everything else in
Ballava (families, data, admins) stays in our own database.

Switched on by SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY. SUPABASE_SECRET_KEY is optional, and is only used on the server,
so that deleting a Ballava account also deletes its sign-in at Supabase. Without any of them, Ballava uses its own
email-and-password accounts.
"""
import base64
import json
import logging
import time
import urllib.error
import urllib.request
import uuid

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .security import ApiError

log = logging.getLogger('kitchen')
_settings = {'at': 0.0, 'data': None}
SETTINGS_SECONDS = 300
UNREACHABLE = 'The sign-in service could not be reached. Please try again in a minute.'


def enabled():
    return bool(settings.SUPABASE_URL and settings.SUPABASE_PUBLISHABLE_KEY)


def check_keys():
    """The publishable key goes to every browser. A secret key in its place would give strangers full control: refuse to start."""
    key = settings.SUPABASE_PUBLISHABLE_KEY
    role = ''
    if key.count('.') == 2:
        try:
            part = key.split('.')[1]
            role = json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4))).get('role', '')
        except (ValueError, AttributeError):
            role = ''
    if key.startswith('sb_secret_') or role == 'service_role':
        raise ImproperlyConfigured('SUPABASE_PUBLISHABLE_KEY holds a SECRET key. Use the publishable (or anon) key there, and change the secret key in Supabase.')


def _call(path, method='GET', token=None, secret=False, timeout=10):
    """(status, JSON) from the Supabase Auth API."""
    key = settings.SUPABASE_SECRET_KEY if secret else settings.SUPABASE_PUBLISHABLE_KEY
    headers = {'apikey': key, 'User-Agent': 'ballava-server'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    elif secret and key.startswith('eyJ'):  # the older kind of key is also a token
        headers['Authorization'] = 'Bearer ' + key
    req = urllib.request.Request(settings.SUPABASE_AUTH_URL + path, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, json.loads(res.read() or b'{}')
    except urllib.error.HTTPError as err:
        try:
            return err.code, json.loads(err.read() or b'{}')
        except ValueError:
            return err.code, {}
    except (OSError, ValueError) as err:
        log.warning('Supabase could not be reached: %s', err)
        raise ApiError(503, UNREACHABLE) from err


def project_settings():
    """What's switched on in the Supabase project (Google, email confirmation...). Remembered for a few minutes."""
    if _settings['data'] is not None and time.monotonic() - _settings['at'] < SETTINGS_SECONDS:
        return _settings['data']
    try:
        status, data = _call('/settings', timeout=5)
    except ApiError:
        status, data = 0, {}
    if status == 200 and isinstance(data, dict):
        _settings.update(at=time.monotonic(), data=data)
        return data
    return _settings['data'] or {}


def public_config():
    """What the sign-in screen needs, or None when Supabase isn't used."""
    if not enabled():
        return None
    s = project_settings()
    return {'url': settings.SUPABASE_AUTH_URL, 'key': settings.SUPABASE_PUBLISHABLE_KEY, 'google': bool((s.get('external') or {}).get('google')),
            'signup': not s.get('disable_signup')}


def person(token):
    """Who this token belongs to: {'id', 'email', 'name', 'proven'}. Asks Supabase, so a made-up, expired or foreign token fails.
    `proven`: we can be sure the email address is theirs (they clicked or typed what was emailed, or Google says so)."""
    token = str(token or '')
    if not 20 < len(token) < 5000 or any(c.isspace() for c in token):
        raise ApiError(401, 'Please sign in again.')
    status, u = _call('/user', token=token)
    if status != 200 or not isinstance(u, dict):
        raise ApiError(401, 'That sign-in has expired. Please sign in again.')
    email = str(u.get('email') or '').strip().lower()
    if u.get('is_anonymous') or not email:
        raise ApiError(403, 'Please sign in with an email address.')
    if not (u.get('email_confirmed_at') or u.get('confirmed_at')):
        raise ApiError(403, 'Please confirm your email address first.')
    try:
        uid = uuid.UUID(str(u.get('id')))
    except ValueError:
        raise ApiError(502, UNREACHABLE) from None
    meta = u.get('user_metadata') if isinstance(u.get('user_metadata'), dict) else {}
    # If "Confirm email" is switched off in the Supabase project, an address is marked confirmed without anyone checking it.
    # Then only Google's word counts for opening an account that already exists here.
    by_google = any((i or {}).get('provider') == 'google' and str(((i or {}).get('identity_data') or {}).get('email') or '').lower() == email
                    and ((i or {}).get('identity_data') or {}).get('email_verified') is True for i in u.get('identities') or [])
    checked = project_settings().get('mailer_autoconfirm') is False
    return {'id': uid, 'email': email, 'name': str(meta.get('name') or meta.get('full_name') or '').strip()[:60], 'proven': checked or by_google}


def delete_person(supabase_id):
    """Removes someone's sign-in at Supabase when their Ballava account goes. Never stops the deletion here."""
    if not (supabase_id and enabled() and settings.SUPABASE_SECRET_KEY):
        return False
    try:
        status, _ = _call(f'/admin/users/{supabase_id}', method='DELETE', secret=True)
    except ApiError:
        status = 0
    if status not in (200, 204, 404):
        log.warning('Could not delete a sign-in at Supabase (status %s). Remove it in the Supabase dashboard.', status)
        return False
    return True
