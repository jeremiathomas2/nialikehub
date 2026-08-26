"""
Django settings for the Nialike Digital Invitation & Event Management System.
Reads configuration from environment / .env using the same variable names as the
original PHP application (DB_*, NEXTSMS_*, PALMPESA_*, APP_URL, ...).
"""
from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def envv(key: str, default: str = "") -> str:
    v = os.environ.get(key)
    return v if v not in (None, "") else default


def envb(key: str, default: bool = False) -> bool:
    return os.environ.get(key, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")


SECRET_KEY = envv("SECRET_KEY", "insecure-dev-key-change-me")
DEBUG = envb("DEBUG", True)
ALLOWED_HOSTS = [h.strip() for h in envv("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h.strip()]
APP_URL = envv("APP_URL", "http://127.0.0.1:8000").rstrip("/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "apps.accounts",
    "apps.events",
    "apps.finance",
    "apps.messaging",
    "apps.core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.BruteForceMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.branding",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "HOST": envv("DB_HOST", "127.0.0.1"),
        "PORT": envv("DB_PORT", "3306"),
        "NAME": envv("DB_NAME", "nialike_django"),
        "USER": envv("DB_USER", "root"),
        "PASSWORD": envv("DB_PASS", ""),
        "OPTIONS": {
            "charset": "utf8mb4",
        },
        "CONN_MAX_AGE": 60,
    }
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = envv("APP_TIMEZONE", "Africa/Dar_es_Salaam")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

# Provider defaults (env fallback; runtime values may be overridden in DB via Gateway & System page)
NEXTSMS = {
    "ENABLED": envb("NEXTSMS_ENABLED", False),
    "BASE_URL": envv("NEXTSMS_BASE_URL", "https://messaging-service.co.tz/api").rstrip("/"),
    "API_KEY": envv("NEXTSMS_API_KEY"),
    "SENDER_ID": envv("NEXTSMS_SENDER_ID", "NIALIKE"),
}
PALMPESA = {
    "ENABLED": envb("PALMPESA_ENABLED", False),
    "BASE_URL": envv("PALMPESA_BASE_URL", "https://palmpesa.drmlelwa.co.tz/api").rstrip("/"),
    "USER_ID": envv("PALMPESA_USER_ID"),
    "API_TOKEN": envv("PALMPESA_API_TOKEN"),
    "TOKEN_PATH": envv("PALMPESA_TOKEN_PATH", "/token"),
    "INITIATE_PATH": envv("PALMPESA_INITIATE_PATH", "/palmpesa/initiate"),
    "STATUS_PATH": envv("PALMPESA_STATUS_PATH", "/order-status"),
    "WEBHOOK_SECRET": envv("PALMPESA_WEBHOOK_SECRET"),
}

CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"

SECURE_SSL_REDIRECT = envb("SECURE_SSL_REDIRECT", False)
SECURE_HSTS_SECONDS = int(envv("SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = envb("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = envb("SECURE_HSTS_PRELOAD", False)
SESSION_COOKIE_SECURE = envb("SESSION_COOKIE_SECURE", False)
CSRF_COOKIE_SECURE = envb("CSRF_COOKIE_SECURE", False)
SECURE_CONTENT_TYPE_NOSNIFF = True
