import os
from pathlib import Path
from datetime import timedelta
import dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env file
dotenv.load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-secret-key')
DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 't')

allowed_hosts_str = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1')
ALLOWED_HOSTS = [h.strip() for h in allowed_hosts_str.split(',') if h.strip()] + ['testserver', '*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party apps
    'corsheaders',
    'rest_framework',

    # Local apps
    'api',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database - Existing MySQL database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('DB_NAME', 'rts_lead_tracker'),
        'USER': os.getenv('DB_USER', 'root'),
        'PASSWORD': os.getenv('DB_PASSWORD', 'Yadav@1977'),
        'HOST': os.getenv('DB_HOST', '127.0.0.1'),
        'PORT': os.getenv('DB_PORT', '3306'),
        'OPTIONS': {
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
APPEND_SLASH = False

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CORS Settings
client_urls = os.getenv('CLIENT_URL', 'http://localhost:5173').split(',')
CORS_ALLOWED_ORIGINS = [u.strip().rstrip('/') for u in client_urls if u.strip()]
CORS_ALLOW_ALL_ORIGINS = True  # Allows smooth development across ports
CORS_ALLOW_CREDENTIALS = False
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'x-import-key',
]

# REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'api.authentication.NestCompatibleJWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser',
    ],
    'EXCEPTION_HANDLER': 'api.exceptions.custom_exception_handler',
}

# Application Custom Secrets
JWT_SECRET = os.getenv('JWT_SECRET', '0f8OvwKykw37CRTEReTT8SObggPxG9xqQVajEtEpneAdQLPik4icHx2/k6GVOvEz')
JWT_EXPIRES_DAYS = int(os.getenv('JWT_EXPIRES_DAYS', '7'))
BCRYPT_ROUNDS = int(os.getenv('BCRYPT_ROUNDS', '12'))
LEAD_IMPORT_SECURITY_KEY = os.getenv('LEAD_IMPORT_SECURITY_KEY', 'qwertyuiopasdfghjklqwertyuiopqwertyuiop')

# AWS S3 Settings
AWS_REGION = os.getenv('AWS_REGION', 'ap-south-1')
AWS_S3_BUCKET_NAME = os.getenv('AWS_S3_BUCKET_NAME', 'asc-computer-services-1109')
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID', '')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY', '')

# Super Admin Env Credentials
SUPER_ADMIN_NAME = os.getenv('SUPER_ADMIN_NAME', 'Saurabh Yadav')
SUPER_ADMIN_EMAIL = os.getenv('SUPER_ADMIN_EMAIL', 'saurabh@gmail.com')
SUPER_ADMIN_PASSWORD = os.getenv('SUPER_ADMIN_PASSWORD', 'Saurabh@2006')
