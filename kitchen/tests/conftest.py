"""Shared test helpers."""
import json

import pytest
from django.contrib.auth.models import User
from django.test import Client

from kitchen import catalog, engine


@pytest.fixture(autouse=True)
def fresh_catalog():
    """Each test starts with only the built-in recipes, ingredients and Bachao fixes."""
    catalog._live['stamp'] = None
    engine.apply_catalog()
    yield
    catalog._live['stamp'] = None
    engine.apply_catalog()


@pytest.fixture(autouse=True)
def no_real_ai(monkeypatch, settings):
    """Tests never call a real AI or use your real keys, whatever is in your .env. AI tests plug in fakes."""
    for name in ('ANTHROPIC_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY'):
        monkeypatch.delenv(name, raising=False)
    settings.AI_PROVIDER = 'claude'


class Api(Client):
    """A test browser that speaks JSON to /api/."""

    def get_json(self, path):
        r = self.get('/api/' + path)
        return r.status_code, r.json()

    def post_json(self, path, body=None, **extra):
        r = self.post('/api/' + path, data=json.dumps(body or {}), content_type='application/json', **extra)
        return r.status_code, r.json()


@pytest.fixture
def api():
    return Api()


@pytest.fixture
def make_user(db):
    counter = {'n': 0}

    def make(**extra):
        counter['n'] += 1
        c = Api()
        email = f'user{counter["n"]}@ballava.test'
        status, data = c.post_json('auth/signup', {'name': f'User {counter["n"]}', 'email': email, 'password': 'kadai-masala-42', 'consent': True, **extra})
        assert status == 200, data
        c.email, c.id = email, data['user']['id']
        return c
    return make


ADMIN = {'username': 'admin@ballava.test', 'password': 'admin-secret-pass-123'}


@pytest.fixture
def admin_client(db):
    User.objects.create_superuser(ADMIN['username'], ADMIN['username'], ADMIN['password'])
    c = Client()
    r = c.post('/admin/login/', {**ADMIN, 'next': '/admin/'})
    assert r.status_code == 302, 'admin should be signed in'
    return c
