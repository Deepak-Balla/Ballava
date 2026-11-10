"""`python manage.py createsuperuser`, with Ballava's rule that admin passwords are at least 12 characters.

Django checks the new password before the account exists, so it can't tell it's for an admin.
This marks the whole command as "creating an admin" so the 12-character rule applies.
"""
from django.contrib.auth.management.commands import createsuperuser

from kitchen import validators


class Command(createsuperuser.Command):
    help = 'Create an admin login. Use your email as the username. Admin passwords need at least 12 characters.'

    def handle(self, *args, **options):
        validators.creating_admin = True
        try:
            return super().handle(*args, **options)
        finally:
            validators.creating_admin = False
