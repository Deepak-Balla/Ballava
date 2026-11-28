"""Shared set-up for the real-browser tests: a live Django server and a phone-sized Chrome."""
import os
import re
from pathlib import Path

import pytest

# Playwright drives the browser from an event loop, so let Django run its (safe, single-threaded) test queries there.
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

SHOTS = Path(__file__).resolve().parents[2] / 'test-screenshots'
PHONE = {'viewport': {'width': 390, 'height': 844}, 'device_scale_factor': 2, 'is_mobile': True, 'has_touch': True}
DESKTOP = {'viewport': {'width': 1200, 'height': 800}}
EXPECTED_NOISE = re.compile(r'status of 4\d\d|ERR_FAILED|ERR_INTERNET_DISCONNECTED')


def _real_db_name():
    """The database the app itself uses (read before any test database is made), which these tests must never flush."""
    from django.conf import settings
    return str(settings.DATABASES['default']['NAME'])


REAL_DB = _real_db_name()


@pytest.fixture(scope='module')
def site(django_db_setup, django_db_blocker):
    """The real app, served by Django on a random port, using the test database.

    pytest-django's own live_server wipes the database after every test, but these tests build on each other
    (sign up, then plan, then cook...), so this runs a small threaded web server that keeps the data for the whole file."""
    import threading
    from socketserver import ThreadingMixIn
    from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

    from django.contrib.staticfiles.handlers import StaticFilesHandler
    from django.core.wsgi import get_wsgi_application

    class Server(ThreadingMixIn, WSGIServer):
        daemon_threads = True

    class Quiet(WSGIRequestHandler):
        def log_message(self, *args):
            pass

    from django.core.management import call_command
    from django.db import connection, connections
    from django.test.utils import setup_databases, teardown_databases

    with django_db_blocker.unblock():
        # pytest-django only makes a test database when some test is marked as using one. With `pytest -m e2e` alone,
        # none is, so the connection would still be the real database. Make the test database here instead.
        own = None
        if str(connection.settings_dict['NAME']) == REAL_DB:
            own = setup_databases(verbosity=0, interactive=False, aliases={'default'}, serialized_aliases=set())
        if str(connection.settings_dict['NAME']) == REAL_DB:
            raise RuntimeError(f'Refusing to run the browser tests on the real database ({REAL_DB}).')
        call_command('flush', interactive=False, verbosity=0)  # every test file starts from an empty database
        httpd = make_server('localhost', 0, StaticFilesHandler(get_wsgi_application()), server_class=Server, handler_class=Quiet)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        yield f'http://localhost:{httpd.server_port}/'
        httpd.shutdown()
        httpd.server_close()
        connections.close_all()
        if own:
            teardown_databases(own, verbosity=0)


@pytest.fixture(scope='module')
def browser():
    from playwright.sync_api import sync_playwright
    SHOTS.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel=os.environ.get('PW_CHANNEL') or None)
        yield b
        b.close()


@pytest.fixture(scope='module')
def errors():
    return []


@pytest.fixture(scope='module')
def device(browser, errors):
    """Opens a new phone (or desktop) with its own storage, like a separate device."""
    def open_device(options=PHONE):
        page = browser.new_context(**options).new_page()
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('console', lambda m: m.type == 'error' and not EXPECTED_NOISE.search(m.text) and errors.append(m.text))
        return page
    return open_device


def snap(page, name):
    page.screenshot(path=str(SHOTS / f'{name}.png'))


def tab(page, name):
    page.get_by_role('navigation', name='Main').get_by_role('button', name=name, exact=True).click()


def more(page, name):
    tab(page, 'More')
    page.get_by_role('button', name=name, exact=True).click()


def diary(page):
    """The food diary: Dashboard tab, then 'Food diary'."""
    tab(page, 'Dashboard')
    page.get_by_role('button', name='📖 Food diary').click()


def open_chef(page):
    """The 🧑‍🍳 Chef button in the middle of the navigation bar (the sidebar on a computer)."""
    tab(page, 'Ballava Chef')
    page.get_by_role('dialog', name='Ballava Chef').wait_for()


WIDE = {'viewport': {'width': 1440, 'height': 900}}

# A 1x1 picture, for "choose a photo" in tests.
PHOTO = {'name': 'fridge.png', 'mimeType': 'image/png', 'buffer': __import__('base64').b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')}

# A pretend microphone and voice, so hands-free mode can be tested: window.__say('next') is "heard",
# and everything the app reads aloud is collected in window.__spoken.
FAKE_VOICE = """
(() => {
  class FakeRecognition {
    start() { window.__rec = this; setTimeout(() => this.onstart && this.onstart(), 0); }
    stop() { setTimeout(() => this.onend && this.onend(), 0); }
    abort() { this.aborted = true; }
  }
  window.SpeechRecognition = FakeRecognition;
  window.webkitSpeechRecognition = FakeRecognition;
  window.__say = text => {
    const result = [{ transcript: text }];
    result.isFinal = true;
    window.__rec.onresult({ resultIndex: 0, results: [result] });
  };
  window.__spoken = [];
  Object.defineProperty(window, 'speechSynthesis', { configurable: true, value: {
    speaking: false, cancel() {}, getVoices() { return []; },
    speak(u) { window.__spoken.push(u.text); setTimeout(() => u.onend && u.onend(), 5); },
  } });
  window.SpeechSynthesisUtterance = function (text) { this.text = text; };
})();
"""


def no_sideways_scroll(page, where):
    over = page.evaluate('document.documentElement.scrollWidth - window.innerWidth')
    assert over <= 0, f'{where} scrolls sideways by {over}px'
