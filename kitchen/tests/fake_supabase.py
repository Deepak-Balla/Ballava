"""A stand-in for Supabase Auth, so tests need no internet. It answers like the real one (checked against supabase/gotrue
v2.198.0), but every emailed code is 123456 and "Google" lets everyone in as google.asha@example.com."""
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

PUBLISHABLE, SECRET, CODE = 'sb_publishable_test', 'sb_secret_test', '123456'


class FakeSupabase:
    def __init__(self):
        self.users, self.tokens, self.pkce, self.emails, self.calls = {}, {}, {}, [], []
        self.autoconfirm, self.google, self.down = False, True, False
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def answer(self, status, data=None, headers=()):
                body = json.dumps(data if data is not None else {}).encode()
                self.send_response(status)
                for k, v in [('Content-Type', 'application/json'), ('Access-Control-Allow-Origin', '*'), ('Access-Control-Allow-Headers', '*, authorization, apikey, content-type'),
                             ('Access-Control-Allow-Methods', '*, PUT, DELETE'), ('Content-Length', str(len(body))), *headers]:
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def handle_one(self):
                url = urlsplit(self.path)
                query = {k: v[0] for k, v in parse_qs(url.query).items()}
                raw = self.rfile.read(int(self.headers.get('Content-Length') or 0))
                body = json.loads(raw) if raw else {}
                token = (self.headers.get('Authorization') or '').removeprefix('Bearer ')
                fake.calls.append((self.command, url.path))
                self.answer(*fake.handle(self.command, url.path, query, body, self.headers.get('apikey'), token))

            do_GET = do_POST = do_PUT = do_DELETE = handle_one

            def do_OPTIONS(self):
                self.answer(204)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    # ---- helpers for tests
    def add(self, email, password='kadai-masala-42', confirmed=True, name='', provider='email', email_verified=True):
        u = {'id': str(uuid.uuid4()), 'email': email, 'email_confirmed_at': '2026-11-24T00:00:00Z' if confirmed else None, 'user_metadata': {'name': name},
             'identities': [{'provider': provider, 'identity_data': {'email': email, 'email_verified': email_verified}}], 'is_anonymous': False, '_password': password}
        self.users[email] = u
        return u

    def token(self, user):
        t = 'token-' + uuid.uuid4().hex
        self.tokens[t] = user['email']
        return t

    def handle(self, method, path, query, body, apikey, token):
        error = lambda status, code, msg='': (status, {'code': status, 'error_code': code, 'msg': msg or code})  # noqa: E731
        session = lambda u: (200, {'access_token': self.token(u), 'token_type': 'bearer', 'expires_in': 3600, 'refresh_token': 'r'})  # noqa: E731
        public = lambda u: {k: v for k, v in u.items() if not k.startswith('_')}  # noqa: E731
        email = str(body.get('email') or '').lower()
        u = self.users.get(email)
        if self.down:
            return 500, {}
        if path == '/authorize':  # the browser itself comes here, without a key
            g = self.users.get('google.asha@example.com') or self.add('google.asha@example.com', name='Asha Google', provider='google')
            code = uuid.uuid4().hex
            self.pkce[code] = (g['email'], query['code_challenge'])
            return 302, {}, [('Location', f"{query['redirect_to']}?code={code}")]
        if apikey not in (PUBLISHABLE, SECRET):
            return error(401, 'no_api_key')
        if (method, path) == ('GET', '/settings'):
            return 200, {'external': {'google': self.google, 'email': True}, 'disable_signup': False, 'mailer_autoconfirm': self.autoconfirm}
        if path == '/signup':
            if len(body.get('password') or '') < 8:
                return error(422, 'weak_password')
            if u and u['email_confirmed_at']:
                return error(422, 'user_already_exists') if self.autoconfirm else (200, {'id': str(uuid.uuid4()), 'email': email, 'identities': []})
            u = self.add(email, body['password'], confirmed=self.autoconfirm, name=(body.get('data') or {}).get('name', ''))
            if self.autoconfirm:
                return session(u)
            self.emails.append(email)
            return 200, public(u)
        if path == '/token' and query.get('grant_type') == 'password':
            if not u or u['_password'] != body.get('password'):
                return error(400, 'invalid_credentials')
            return session(u) if u['email_confirmed_at'] else error(400, 'email_not_confirmed')
        if path == '/token' and query.get('grant_type') == 'pkce':
            import base64
            import hashlib
            who, challenge = self.pkce.pop(body.get('auth_code'), (None, None))
            made = base64.urlsafe_b64encode(hashlib.sha256(str(body.get('code_verifier')).encode()).digest()).rstrip(b'=').decode()
            return session(self.users[who]) if who and made == challenge else error(400, 'bad_code_verifier')
        if path == '/verify':
            if not u or body.get('token') != CODE:
                return error(403, 'otp_expired')
            u['email_confirmed_at'] = '2026-11-24T00:00:00Z'
            return session(u)
        if path in ('/resend', '/recover'):
            if u:
                self.emails.append(email)
            return 200, {}
        if path.startswith('/admin/users/'):
            if apikey != SECRET:
                return error(401, 'no_authorization')
            found = next((x for x in self.users.values() if path.endswith(x['id'])), None)
            if found:
                del self.users[found['email']]
            return (200, {}) if found else error(404, 'user_not_found')
        me = self.users.get(self.tokens.get(token))
        if not me:
            return error(403, 'bad_jwt')
        if (method, path) == ('GET', '/user'):
            return 200, public(me)
        if (method, path) == ('PUT', '/user'):
            me['_password'] = body['password']
            return 200, public(me)
        if path == '/logout':
            self.tokens.pop(token, None)
            return 204, {}
        return error(404, 'not_found')
