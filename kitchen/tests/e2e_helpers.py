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
    from django.db import connections

    with django_db_blocker.unblock():
        call_command('flush', interactive=False, verbosity=0)  # every test file starts from an empty database
        httpd = make_server('localhost', 0, StaticFilesHandler(get_wsgi_application()), server_class=Server, handler_class=Quiet)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        yield f'http://localhost:{httpd.server_port}/'
        httpd.shutdown()
        httpd.server_close()
        connections.close_all()


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


def open_ai(page):
    """The ✨ AI button in the middle of the navigation bar."""
    tab(page, 'AI assistant')
    page.get_by_role('dialog', name='Ballava AI').wait_for()


def no_sideways_scroll(page, where):
    over = page.evaluate('document.documentElement.scrollWidth - window.innerWidth')
    assert over <= 0, f'{where} scrolls sideways by {over}px'
