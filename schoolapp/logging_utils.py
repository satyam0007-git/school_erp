import contextvars
import logging
import logging.handlers
import queue
import threading
import traceback
from datetime import datetime
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone


LOG_QUEUE = queue.SimpleQueue()
_REQUEST_CONTEXT = contextvars.ContextVar('schoolapp_request_context', default={})
_LISTENER = None
_LISTENER_LOCK = threading.Lock()
_SCHOOL_LOG_FILE = 'school.log'
_SUPERUSER_LOG_FILE = 'superuser.log'

_SUPERUSER_AUDIT_ACTIONS = {
    'billing_payment_create',
    'settings_update',
    'school_create',
    'school_update',
    'school_delete',
    'user_create',
    'user_delete',
}


def ensure_log_root():
    base = Path(settings.LOG_ROOT)
    base.mkdir(parents=True, exist_ok=True)
    (base / 'superuser').mkdir(parents=True, exist_ok=True)
    return base


def get_client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '-')


def get_school_subdomain(request=None):
    if request is not None:
        tenant = getattr(request, 'tenant', None)
        subdomain = getattr(tenant, 'subdomain', None)
        if subdomain:
            return subdomain
    context = _REQUEST_CONTEXT.get() or {}
    return context.get('school_subdomain') or 'superuser'


def get_log_scope(request=None):
    if request is not None and getattr(request, 'tenant', None) is None:
        return 'superuser'
    return get_school_subdomain(request) or 'superuser'


def sanitize_value(value):
    if isinstance(value, dict):
        return {str(k): sanitize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [sanitize_value(item) for item in value]
    return value


class RequestContextFilter(logging.Filter):
    def filter(self, record):
        context = _REQUEST_CONTEXT.get() or {}
        record.school_subdomain = context.get('school_subdomain', 'superuser')
        record.school_id = context.get('school_id', '-')
        record.user_id = context.get('user_id', '-')
        record.user_role = context.get('user_role', 'anonymous')
        record.user_label = context.get('user_label', 'anonymous')
        record.ip_address = context.get('ip_address', '-')
        record.request_method = context.get('request_method', '-')
        record.request_path = context.get('request_path', '-')
        record.response_status = getattr(record, 'response_status', '-')
        record.duration_ms = getattr(record, 'duration_ms', '-')
        record.log_scope = context.get('log_scope', 'superuser')
        record.traceback = getattr(record, 'traceback', '-')
        return True


class IstFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        ts = datetime.fromtimestamp(record.created, tz=ZoneInfo('Asia/Kolkata'))
        if datefmt:
            return ts.strftime(datefmt)
        return ts.isoformat(timespec='seconds')


class TenantRotatingFileHandler(logging.Handler):
    def __init__(self, filename, max_bytes=5 * 1024 * 1024, backup_count=5):
        super().__init__()
        self.base_dir = ensure_log_root()
        self.filename = filename
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self._handlers = {}
        self._lock = threading.RLock()

    def _get_handler(self, subdomain):
        folder_name = 'superuser' if subdomain == 'superuser' else subdomain
        file_name = _SUPERUSER_LOG_FILE if folder_name == 'superuser' else self.filename
        log_path = self.base_dir / folder_name / file_name
        key = str(log_path)
        with self._lock:
            handler = self._handlers.get(key)
            if handler is None:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                handler = logging.handlers.RotatingFileHandler(
                    log_path,
                    maxBytes=self.max_bytes,
                    backupCount=self.backup_count,
                    encoding='utf-8',
                )
                if self.formatter:
                    handler.setFormatter(self.formatter)
                self._handlers[key] = handler
            return handler

    def emit(self, record):
        scope = getattr(record, 'log_scope', None) or get_log_scope()
        self._get_handler(scope).handle(record)

    def close(self):
        with self._lock:
            for handler in self._handlers.values():
                handler.close()
            self._handlers.clear()
        super().close()


class RoutingHandler(logging.Handler):
    def __init__(self, application_handler, activity_handler, errors_handler, requests_handler):
        super().__init__()
        self.application_handler = application_handler
        self.activity_handler = activity_handler
        self.errors_handler = errors_handler
        self.requests_handler = requests_handler

    def emit(self, record):
        if record.name == 'django.server':
            return
        if record.name.startswith('schoolapp.activity'):
            self.activity_handler.handle(record)
        elif record.name.startswith('schoolapp.errors'):
            self.errors_handler.handle(record)
        elif record.name.startswith('schoolapp.requests'):
            self.requests_handler.handle(record)
        else:
            self.application_handler.handle(record)


def make_queue_handler():
    handler = logging.handlers.QueueHandler(LOG_QUEUE)
    handler.addFilter(RequestContextFilter())
    return handler


def _current_context_dict(request=None):
    if request is not None:
        tenant = getattr(request, 'tenant', None)
        user = getattr(request, 'user', None)
        school = getattr(user, 'school', None) if user else None
        school_subdomain = getattr(tenant, 'subdomain', None) or getattr(school, 'subdomain', None) or 'superuser'
        school_id = getattr(tenant, 'pk', None) or getattr(school, 'pk', None)
        is_authenticated = bool(getattr(user, 'is_authenticated', False))
        user_id = getattr(user, 'pk', None) if is_authenticated else None
        user_role = getattr(user, 'role', 'anonymous') if is_authenticated else 'anonymous'
        user_label = f'{user_id}:{user_role}' if user_id is not None else user_role
        return {
            'school_subdomain': school_subdomain,
            'school_id': school_id or '-',
            'user_id': user_id or '-',
            'user_role': user_role,
            'user_label': user_label,
            'ip_address': get_client_ip(request),
            'request_method': getattr(request, 'method', '-'),
            'request_path': getattr(request, 'get_full_path', lambda: '-')(),
            'log_scope': school_subdomain or 'superuser',
        }

    context = dict(_REQUEST_CONTEXT.get() or {})
    context.setdefault('school_subdomain', 'superuser')
    context.setdefault('school_id', '-')
    context.setdefault('user_id', '-')
    context.setdefault('user_role', 'anonymous')
    context.setdefault('user_label', 'anonymous')
    context.setdefault('ip_address', '-')
    context.setdefault('request_method', '-')
    context.setdefault('request_path', '-')
    context.setdefault('log_scope', 'superuser')
    return context


def get_request_context(request=None):
    return _current_context_dict(request)


def set_request_context(request):
    return _REQUEST_CONTEXT.set(_current_context_dict(request))


def reset_request_context(token):
    _REQUEST_CONTEXT.reset(token)


def start_logging_listener():
    global _LISTENER
    with _LISTENER_LOCK:
        if _LISTENER is not None:
            return _LISTENER

        application_handler = TenantRotatingFileHandler(_SCHOOL_LOG_FILE)

        unified_formatter = IstFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            '%Y-%m-%d %H:%M:%S',
        )
        application_handler.setFormatter(unified_formatter)

        routing_handler = RoutingHandler(application_handler, application_handler, application_handler, application_handler)
        _LISTENER = logging.handlers.QueueListener(LOG_QUEUE, routing_handler)
        _LISTENER.start()
        return _LISTENER


def stop_logging_listener():
    global _LISTENER
    with _LISTENER_LOCK:
        if _LISTENER is None:
            return
        _LISTENER.stop()
        _LISTENER = None


def log_activity_event(request, module, action, record_id=None, status='success', old_values=None, new_values=None, details=None, extra=None):
    if getattr(request, 'tenant', None) is None and module == 'superuser' and action not in _SUPERUSER_AUDIT_ACTIONS:
        return

    payload = {
        'timestamp': timezone.localtime().isoformat(timespec='seconds'),
        'module': module,
        'action': action,
        'record_id': record_id,
        'status': status,
        'user_id': getattr(request.user, 'pk', None) if getattr(request, 'user', None) and getattr(request.user, 'is_authenticated', False) else None,
        'user_role': getattr(request.user, 'role', 'anonymous') if getattr(request, 'user', None) and getattr(request.user, 'is_authenticated', False) else 'anonymous',
        'school_id': getattr(getattr(request, 'tenant', None), 'pk', None) or getattr(getattr(request.user, 'school', None), 'pk', None),
        'school_subdomain': get_school_subdomain(request),
        'log_scope': get_log_scope(request),
    }
    if old_values is not None:
        payload['old_values'] = sanitize_value(old_values)
    if new_values is not None:
        payload['new_values'] = sanitize_value(new_values)
    if details is not None:
        payload['details'] = sanitize_value(details)
    if extra:
        payload['extra'] = sanitize_value(extra)

    logger = logging.getLogger('schoolapp.activity')
    if str(status).lower() == 'success':
        logger.info('%s.%s: %s', module, action, payload)
    else:
        error_logger = logging.getLogger('schoolapp.errors')
        error_logger.error('%s.%s failed: %s', module, action, payload)


def log_request_event(request, response=None, started_at=None, exc=None):
    context = get_request_context(request)
    if started_at is not None:
        context['duration_ms'] = int((timezone.now() - started_at).total_seconds() * 1000)
    context['response_status'] = getattr(response, 'status_code', 500 if exc else '-')
    logging.getLogger('schoolapp.requests').info('request completed: %s', context)


def log_unhandled_exception(request, exc):
    context = get_request_context(request)
    context['traceback'] = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    context['response_status'] = 500
    logging.getLogger('schoolapp.errors').error(
        'Unhandled exception for %s %s: %s',
        getattr(request, 'method', '-'),
        getattr(request, 'get_full_path', lambda: '-')(),
        exc,
        exc_info=exc,
    )


def audit_action(module, action, record_id_getter=None, details_getter=None):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            try:
                response = view_func(request, *args, **kwargs)
            except Exception as exc:
                record_id = record_id_getter(request, *args, **kwargs) if callable(record_id_getter) else None
                details = details_getter(request, *args, **kwargs) if callable(details_getter) else None
                log_activity_event(
                    request,
                    module=module,
                    action=action,
                    record_id=record_id,
                    status='failure',
                    details=details,
                    extra={'error': str(exc)},
                )
                raise

            record_id = record_id_getter(request, *args, **kwargs) if callable(record_id_getter) else None
            details = details_getter(request, *args, **kwargs) if callable(details_getter) else None
            if getattr(response, 'status_code', 200) < 400:
                log_activity_event(
                    request,
                    module=module,
                    action=action,
                    record_id=record_id,
                    status='success',
                    details=details,
                )
            return response

        return wrapped

    return decorator


def log_request_exception(request, exc):
    log_unhandled_exception(request, exc)
