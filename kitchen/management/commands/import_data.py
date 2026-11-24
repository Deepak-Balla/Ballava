"""python manage.py import_data backup.json: puts an export (see export_data) into this database, which must be new."""
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from kitchen.models import FamilyData, Household, Recipe


class Command(BaseCommand):
    help = 'Loads a file made by export_data into a new, empty database.'

    def add_arguments(self, parser):
        parser.add_argument('file')

    def handle(self, *args, file, **options):
        db = settings.DATABASES['default']
        where = f"{db['ENGINE'].rsplit('.', 1)[-1]} at {db.get('HOST') or db['NAME']}"
        if any(m.objects.exists() for m in (User, Household, FamilyData, Recipe)):
            raise CommandError(f'This database ({where}) already has data, so nothing was changed. Import only into a new one.')
        call_command('loaddata', file, verbosity=0)
        self.stdout.write(self.style.SUCCESS(f'Done, into {where}: {User.objects.count()} accounts, {Household.objects.count()} families, '
                                             f'{Recipe.objects.count()} admin recipes.'))
