from django.apps import AppConfig

from .logging_utils import ensure_log_root, start_logging_listener


class SchoolAppConfig(AppConfig):
    name = 'schoolapp'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        ensure_log_root()
        start_logging_listener()
