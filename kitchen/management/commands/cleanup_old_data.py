"""`python manage.py cleanup_old_data`: remove what's older than DATA_RETENTION_DAYS (6 months) right now.

The app also does this by itself once a day. See kitchen/retention.py for exactly what is removed.
"""
from django.core.management.base import BaseCommand

from kitchen import retention
from kitchen.models import Housekeeping


class Command(BaseCommand):
    help = 'Delete diary meals, saved dishes, AI recipes, chats and unused accounts older than DATA_RETENTION_DAYS (default 180).'

    def handle(self, *args, **options):
        if not retention.days():
            self.stdout.write('DATA_RETENTION_DAYS is 0, so nothing is ever removed.')
            return
        done = retention.cleanup()
        from django.utils import timezone
        Housekeeping.objects.update_or_create(name='retention', defaults={'last_run': timezone.localdate(), 'details': done})
        self.stdout.write(self.style.SUCCESS(f'Removed data older than {retention.days()} days: ' + ', '.join(f'{v} {k}' for k, v in done.items())))
