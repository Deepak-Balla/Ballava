"""python manage.py export_data backup.json: everything in the database, in one file.

Use it for backups, and to move to another database (see import_data). The file holds families' private data and password
hashes: keep it somewhere safe, never put it on GitHub, and delete it when you no longer need it."""
from django.core.management import call_command
from django.core.management.base import BaseCommand

LEFT_OUT = ['contenttypes', 'auth.permission', 'sessions', 'kitchen.attempt', 'kitchen.phonecode']  # rebuilt, or only for a few minutes


class Command(BaseCommand):
    help = 'Saves the whole database to a JSON file (for backups, or to move to Postgres).'

    def add_arguments(self, parser):
        parser.add_argument('file')

    def handle(self, *args, file, **options):
        call_command('dumpdata', exclude=LEFT_OUT, use_natural_foreign_keys=True, output=file, verbosity=0)
        self.stdout.write(self.style.SUCCESS(f'Saved to {file}. It holds private family data: keep it safe, and delete it when you are done.'))
