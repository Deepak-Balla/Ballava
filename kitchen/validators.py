from django.core.exceptions import ValidationError

# Set by `manage.py createsuperuser` while it runs (see kitchen/management/commands/createsuperuser.py).
creating_admin = False


class AdminMinimumLengthValidator:
    """Admins hold the keys to everything, so their passwords must be at least 12 characters."""

    min_length = 12

    def validate(self, password, user=None):
        is_admin = creating_admin or (user is not None and getattr(user, 'is_staff', False))
        if is_admin and len(password) < self.min_length:
            raise ValidationError(f'Admin passwords must be at least {self.min_length} characters.', code='admin_password_too_short')

    def get_help_text(self):
        return f'Admin passwords must be at least {self.min_length} characters.'
