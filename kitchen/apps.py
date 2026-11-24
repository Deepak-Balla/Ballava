from django.apps import AppConfig


class KitchenConfig(AppConfig):
    name = 'kitchen'
    verbose_name = 'Ballava'

    def ready(self):
        from django.db.models.signals import post_migrate

        from . import signals, supabase  # noqa: F401  (signals: keeps the live recipe book up to date)
        from .locks import lock_tables
        supabase.check_keys()
        # Sent after each app's tables are made; the last one to be migrated leaves every table locked.
        post_migrate.connect(lambda using, **kwargs: lock_tables(using), weak=False, dispatch_uid='ballava-lock-tables')
