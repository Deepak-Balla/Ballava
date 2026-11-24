"""How the production web server starts (used in Docker and online). Settings come from environment variables.

Everything is loaded once, before any visitor is let in, and the database is brought up to date in the same process.
On a small free server that makes waking up several times faster than starting Python twice."""
import os

bind = '0.0.0.0:' + os.environ.get('PORT', '8000')
workers = int(os.environ.get('WEB_CONCURRENCY') or 2)
threads = 4
timeout = 120  # an AI answer can take a while
accesslog = '-'
preload_app = True


def on_starting(server):
    from django.core.management import call_command
    from django.db import connections
    from django.db.migrations.executor import MigrationExecutor

    from kitchen.locks import lock_tables
    executor = MigrationExecutor(connections['default'])
    if executor.migration_plan(executor.loader.graph.leaf_nodes()):
        server.log.info('Updating the database tables...')
        call_command('migrate', interactive=False, verbosity=0)
    lock_tables()
    connections.close_all()  # each web process opens its own
