from django.apps import AppConfig


class KitchenConfig(AppConfig):
    name = 'kitchen'
    verbose_name = 'Ballava'

    def ready(self):
        from . import signals  # noqa: F401  (keeps the live recipe book up to date)
