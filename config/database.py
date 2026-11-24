"""Which database to use. Without DATABASE_URL: one SQLite file in the data folder. With it: Postgres (Supabase, Neon...)."""
from urllib.parse import parse_qs, unquote, urlsplit


def from_url(url):
    """'postgresql://user:pass@host:5432/name' -> Django's settings for it."""
    u = urlsplit(url)
    if u.scheme not in ('postgres', 'postgresql') or not u.hostname:
        raise ValueError('DATABASE_URL must look like postgresql://user:password@host:5432/postgres')
    query = {k: v[0] for k, v in parse_qs(u.query).items()}
    nearby = u.hostname in ('localhost', '127.0.0.1') or '.' not in u.hostname  # this computer, or another container
    db = {
        'ENGINE': 'django.db.backends.postgresql', 'NAME': unquote(u.path.lstrip('/')) or 'postgres',
        'USER': unquote(u.username or ''), 'PASSWORD': unquote(u.password or ''), 'HOST': u.hostname, 'PORT': str(u.port or 5432),
        # Over the internet the connection is always encrypted.
        'OPTIONS': {'sslmode': query.get('sslmode') or ('prefer' if nearby else 'require'), 'connect_timeout': 15},
        'CONN_MAX_AGE': 60, 'CONN_HEALTH_CHECKS': True,
    }
    if u.port == 6543:  # Supabase's "transaction" pooler: connections are shared between requests
        db.update(CONN_MAX_AGE=0, DISABLE_SERVER_SIDE_CURSORS=True)
    return db
