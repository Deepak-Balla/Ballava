"""Django settings for Ballava.

Settings come from environment variables, or from a .env file in the project folder
(copy .env.example to .env). Sensible defaults let it run on your own computer with no setup.
"""
import os
import secrets
from pathlib import Path

from django.utils.csp import CSP
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


def env_flag(name, default=False):
    return os.environ.get(name, '1' if default else '0').strip().lower() in ('1', 'true', 'yes', 'on')


def env_list(name, default=''):
    return [x.strip() for x in os.environ.get(name, default).split(',') if x.strip()]


DATA_DIR = Path(os.environ.get('DATA_DIR', BASE_DIR / 'data'))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Turn DEBUG off on a live website (DJANGO_DEBUG=0). It shows error details that strangers must not see.
DEBUG = env_flag('DJANGO_DEBUG', default=True)


def _secret_key():
    """Signs sign-in cookies. Set DJANGO_SECRET_KEY, or a random one is made once and kept in the data folder."""
    key = os.environ.get('DJANGO_SECRET_KEY')
    if key:
        return key
    path = DATA_DIR / 'secret_key.txt'
    if not path.exists():
        path.write_text(secrets.token_urlsafe(50))
    return path.read_text().strip()


SECRET_KEY = _secret_key()
ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', '*' if DEBUG else 'localhost,127.0.0.1')
CSRF_TRUSTED_ORIGINS = env_list('DJANGO_CSRF_TRUSTED_ORIGINS')

INSTALLED_APPS = [
    'kitchen',  # first, so its version of `createsuperuser` (with the admin password rule) is the one used
    'django.contrib.admin.apps.SimpleAdminConfig',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.csp.ContentSecurityPolicyMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
        'django.template.context_processors.csp',
    ]},
}]

# One database file. Back it up. Change the folder with DATA_DIR.
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': DATA_DIR / 'db.sqlite3',
                         'OPTIONS': {'init_command': 'PRAGMA journal_mode=WAL;', 'transaction_mode': 'IMMEDIATE', 'timeout': 20},
                         # Tests use their own file (never your real data), so each web-server thread gets its own connection.
                         'TEST': {'NAME': DATA_DIR / 'test_db.sqlite3'}}}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
# Fridge photos for AI Chef can be up to 8 MB; each API view also sets its own smaller limit.
DATA_UPLOAD_MAX_MEMORY_SIZE = 9 * 1024 * 1024

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
    {'NAME': 'kitchen.validators.AdminMinimumLengthValidator'},
]

# Sign-in lasts 30 days. Session cookies can't be read by page scripts.
SESSION_COOKIE_AGE = 30 * 24 * 60 * 60
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

# Live website behind https: set DJANGO_SECURE=1.
if env_flag('DJANGO_SECURE'):
    SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = env_flag('DJANGO_SSL_REDIRECT', default=True)
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30

X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'same-origin'
SECURE_CSP = {
    'default-src': [CSP.SELF],
    'style-src': [CSP.SELF, CSP.UNSAFE_INLINE],
    'img-src': [CSP.SELF, 'data:', 'blob:'],
    'frame-ancestors': [CSP.NONE],
    'base-uri': [CSP.SELF],
    'form-action': [CSP.SELF],
}

LANGUAGE_CODE = 'en-in'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# The phone app (built from src/ into dist/) is served from the site root.
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
WHITENOISE_ROOT = BASE_DIR / 'dist'
WHITENOISE_INDEX_FILE = True
WHITENOISE_KEEP_ONLY_HASHED_FILES = False
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}

LOGGING = {
    'version': 1, 'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {'kitchen': {'handlers': ['console'], 'level': 'INFO'}},
}

# ---- Ballava options -------------------------------------------------------
ANTHROPIC_MODEL = os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-5-5')
AI_RATE_LIMIT = int(os.environ.get('AI_RATE_LIMIT', '10'))
SIGNUP_RATE_LIMIT = int(os.environ.get('SIGNUP_RATE_LIMIT', '20'))
# Phone sign-in: OTP_DEV_MODE=1 shows the code on screen (your own computer only), or set the TWILIO_* values.
OTP_DEV_MODE = env_flag('OTP_DEV_MODE') and DEBUG
