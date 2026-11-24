"""Entry point for production web servers such as gunicorn (used in Docker)."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
application = get_wsgi_application()

# Load every page now, so the first visitor doesn't wait for it.
from django.urls import get_resolver  # noqa: E402

get_resolver().url_patterns  # noqa: B018
