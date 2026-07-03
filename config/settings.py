import os
from pathlib import Path
from urllib.parse import parse_qsl, urlparse, unquote

BASE_DIR = Path(__file__).resolve().parent.parent


def load_local_env(env_path):
    if not env_path.exists():
        return

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_local_env(BASE_DIR / '.env')


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def env_list(name, default=None):
    value = os.environ.get(name)
    if value is None:
        return default or []
    return [item.strip() for item in value.split(',') if item.strip()]


def database_from_url(database_url):
    parsed = urlparse(database_url)
    if parsed.scheme not in {'postgres', 'postgresql'}:
        raise ValueError('DATABASE_URL must use the postgres:// or postgresql:// scheme.')

    config = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': unquote(parsed.path.lstrip('/')),
        'USER': unquote(parsed.username or ''),
        'PASSWORD': unquote(parsed.password or ''),
        'HOST': parsed.hostname or '',
        'PORT': str(parsed.port or ''),
    }

    query_options = dict(parse_qsl(parsed.query))
    sslmode = query_options.pop('sslmode', None)
    if sslmode:
        config['OPTIONS'] = {'sslmode': sslmode}
    if query_options:
        config.setdefault('OPTIONS', {}).update(query_options)
    return config


SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-school-erp-key-change-in-production')
DEBUG = env_bool('DJANGO_DEBUG', True)
ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', ['.localhost', '127.0.0.1', '[::1]'])

# ── Tenant / subdomain settings ────────────────────────────────────────────────
# Set this to your production domain, e.g. 'erpdomain.com'.
# For local development, keep it as 'localhost' and access schools via
# school1.localhost:8000 (add entries to /etc/hosts or use a wildcard DNS tool).
TENANT_BASE_DOMAIN = os.environ.get('TENANT_BASE_DOMAIN', 'localhost')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'schoolapp.apps.SchoolAppConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'schoolapp.middleware.TenantMiddleware',
    'schoolapp.middleware.RequestLoggingMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'],
    'APP_DIRS': True,
    'OPTIONS': {
        'context_processors': [
            'django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth',
            'django.contrib.messages.context_processors.messages',
            'schoolapp.context_processors.software_branding',
        ],
    },
}]

WSGI_APPLICATION = 'config.wsgi.application'

if os.environ.get('DATABASE_URL'):
    default_database = database_from_url(os.environ['DATABASE_URL'])
else:
    default_database = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'postgres'),
        'USER': os.environ.get('POSTGRES_USER', 'schoolerp'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', ''),
        'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
    }

postgres_sslmode = os.environ.get('POSTGRES_SSLMODE')
if postgres_sslmode:
    default_database.setdefault('OPTIONS', {})['sslmode'] = postgres_sslmode

default_database.setdefault('OPTIONS', {}).setdefault(
    'connect_timeout',
    int(os.environ.get('POSTGRES_CONNECT_TIMEOUT', '5')),
)
default_database['CONN_MAX_AGE'] = int(os.environ.get('POSTGRES_CONN_MAX_AGE', '60'))

DATABASES = {
    'default': default_database,
}

AUTH_USER_MODEL = 'schoolapp.User'
AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'en'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

LOGIN_URL = '/login/'

CSRF_TRUSTED_ORIGINS = env_list('DJANGO_CSRF_TRUSTED_ORIGINS')
SECURE_SSL_REDIRECT = env_bool('DJANGO_SECURE_SSL_REDIRECT', False)
SESSION_COOKIE_SECURE = env_bool('DJANGO_SESSION_COOKIE_SECURE', not DEBUG)
CSRF_COOKIE_SECURE = env_bool('DJANGO_CSRF_COOKIE_SECURE', not DEBUG)

LOG_ROOT = BASE_DIR / 'logs'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'request_context': {
            '()': 'schoolapp.logging_utils.RequestContextFilter',
        },
    },
    'formatters': {
        'ist': {
            '()': 'schoolapp.logging_utils.IstFormatter',
            'format': '%(asctime)s %(levelname)s %(name)s [school=%(school_subdomain)s school_id=%(school_id)s user=%(user_label)s ip=%(ip_address)s] %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S %Z',
        },
        'requests': {
            '()': 'schoolapp.logging_utils.IstFormatter',
            'format': '%(asctime)s %(levelname)s %(name)s [school=%(school_subdomain)s school_id=%(school_id)s user=%(user_label)s role=%(user_role)s ip=%(ip_address)s method=%(request_method)s path=%(request_path)s status=%(response_status)s duration_ms=%(duration_ms)s] %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S %Z',
        },
        'simple': {
            'format': '%(asctime)s %(levelname)s %(name)s %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    'handlers': {
        'queue': {
            '()': 'schoolapp.logging_utils.make_queue_handler',
            'filters': ['request_context'],
        },
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'level': 'INFO',
        'handlers': ['queue', 'console'],
    },
    'loggers': {
        'django': {
            'level': 'INFO',
            'handlers': ['queue', 'console'],
            'propagate': False,
        },
        'django.request': {
            'level': 'INFO',
            'handlers': ['queue', 'console'],
            'propagate': False,
        },
        'schoolapp.application': {
            'level': 'INFO',
            'handlers': ['queue', 'console'],
            'propagate': False,
        },
        'schoolapp.activity': {
            'level': 'INFO',
            'handlers': ['queue', 'console'],
            'propagate': False,
        },
        'schoolapp.errors': {
            'level': 'INFO',
            'handlers': ['queue', 'console'],
            'propagate': False,
        },
        'schoolapp.requests': {
            'level': 'INFO',
            'handlers': ['queue', 'console'],
            'propagate': False,
        },
    },
}
