"""AK DeviceLock settings. Secrets come from environment variables, never from the APK."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.environ.get("AKDL_DEBUG", "1") == "1"
SECRET_KEY = os.environ.get("AKDL_SECRET_KEY", "dev-only-insecure-key" if DEBUG else None)
if not SECRET_KEY:
    raise RuntimeError("AKDL_SECRET_KEY must be set when AKDL_DEBUG=0")
ALLOWED_HOSTS = os.environ.get("AKDL_ALLOWED_HOSTS", "*" if DEBUG else "").split(",")

# Shared secret that authorizes a new device to register (set per deployment).
ENROLLMENT_KEY = os.environ.get("AKDL_ENROLLMENT_KEY", "dev-enrollment-key" if DEBUG else "")
# ECDSA P-256 private key (PEM) used to sign commands.
SIGNING_KEY_PATH = os.environ.get("AKDL_SIGNING_KEY_PATH", str(BASE_DIR / "secrets" / "command_signing_key.pem"))
ONLINE_WINDOW_SECONDS = 180
DEFAULT_COMMAND_TTL = 3600
MAX_COMMAND_TTL = 7 * 24 * 3600

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "rest_framework",
    "devices", "commands", "notifications", "audit",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "akdl.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR.parent / "admin-panel" / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "akdl.wsgi.application"

# SQLite for development. Production: switch to PostgreSQL via env (see deployment docs).
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/admin/login/"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAdminUser"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle", "rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": "30/min", "user": "120/min", "device": "60/min"},
    "EXCEPTION_HANDLER": "akdl.errors.safe_exception_handler",
}

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
