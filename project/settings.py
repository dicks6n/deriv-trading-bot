import os  #[cite: 15]
from pathlib import Path  #[cite: 15]
from dotenv import load_dotenv  #[cite: 15]

# Build paths inside the project like this: BASE_DIR / 'subdir'.  #[cite: 15]
BASE_DIR = Path(__file__).resolve().parent.parent  #[cite: 15]
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'  #[cite: 15]
# Load environment variables from .env file  #[cite: 15]
load_dotenv(os.path.join(BASE_DIR, '.env'))  #[cite: 15]

# =============================================
# DERIV API CONFIGURATION
# =============================================
DERIV_APP_ID = os.getenv('DERIV_APP_ID', '33XN84FbZfx1ZO1xDyUzH')  #[cite: 15]
DERIV_API_TOKEN = os.getenv('DERIV_API_TOKEN', 'pat_88425959654f17ccd0a5f09ea440c64761dd130618179d2db744b85e3ce7d385')  #[cite: 15]



# =============================================
# NOWCRYPTO API CONFIGURATION
# =============================================

# settings.py
NOWPAYMENTS_API_KEY = '3PKABWF-B65MP44-K6DR5HH-RB6XGH3'
NOWPAYMENTS_IPN_SECRET = 'cLoO44Lqh4PIGxVbhNcvyFyEHV/8E+97'
NOWPAYMENTS_SANDBOX = True  # Set to False when going live

# =============================================
# SECURITY & DEPLOYMENT
# =============================================
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-ahw@(v2zyav9rjx$yqhgjer+qfa$xiv7k1d37!q$0w8ylwba3k')  #[cite: 15]
DEBUG = True  #[cite: 15]
ALLOWED_HOSTS = ['*']  #[cite: 15]

# =============================================
# APPLICATION DEFINITION
# =============================================
INSTALLED_APPS = [
    'daphne',  #[cite: 15]
    'django.contrib.admin',  #[cite: 15]
    'django.contrib.auth',  #[cite: 15]
    'django.contrib.contenttypes',  #[cite: 15]
    'django.contrib.sessions',  #[cite: 15]
    'django.contrib.messages',  #[cite: 15]
    'django.contrib.staticfiles',  #[cite: 15]
    'store.apps.StoreConfig',  #[cite: 15]
    'channels',  #[cite: 15]
    'django_daraja',  #[cite: 15]
    'django.contrib.sites',  #[cite: 15]
    'allauth',  #[cite: 15]
    'allauth.account',  #[cite: 15]
    'allauth.socialaccount',  #[cite: 15]
    'allauth.socialaccount.providers.google',  #[cite: 15]
    'allauth.socialaccount.providers.apple',  #[cite: 15]
    'rest_framework',
    'rest_framework_simplejwt',
]
SITE_ID = 1  #[cite: 15]

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',  #[cite: 15]
    'allauth.account.auth_backends.AuthenticationBackend',  #[cite: 15]
]

ASGI_APPLICATION = 'project.asgi.application'  #[cite: 15]
WSGI_APPLICATION = 'project.wsgi.application'  #[cite: 15]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',  #[cite: 15]
    'django.contrib.sessions.middleware.SessionMiddleware',  #[cite: 15]
    'django.middleware.common.CommonMiddleware',  #[cite: 15]
    'django.middleware.csrf.CsrfViewMiddleware',  #[cite: 15]
    'django.contrib.auth.middleware.AuthenticationMiddleware',  #[cite: 15]
    'allauth.account.middleware.AccountMiddleware',  #[cite: 15]
    'django.contrib.messages.middleware.MessageMiddleware',  #[cite: 15]
    'django.middleware.clickjacking.XFrameOptionsMiddleware',  #[cite: 15]
]

ROOT_URLCONF = 'project.urls'  #[cite: 15]

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',  #[cite: 15]
        'DIRS': [],  #[cite: 15]
        'APP_DIRS': True,  #[cite: 15]
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',  #[cite: 15]
                'django.contrib.auth.context_processors.auth',  #[cite: 15]
                'django.contrib.messages.context_processors.messages',  #[cite: 15]
            ],
        },
    },
]

# =============================================
# CHANNELS & WEBSOCKET LAYER
# =============================================
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',  #[cite: 15]
    },
}

# =============================================
# DATABASE
# =============================================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',  #[cite: 15]
        'NAME': BASE_DIR / 'db.sqlite3',  #[cite: 15]
    }
}

# =============================================
# PASSWORD VALIDATION
# =============================================
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},  #[cite: 15]
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},  #[cite: 15]
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},  #[cite: 15]
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},  #[cite: 15]
]

# =============================================
# INTERNATIONALIZATION
# =============================================
LANGUAGE_CODE = 'en-us'  #[cite: 15]
TIME_ZONE = 'Africa/Nairobi'  #[cite: 15]
USE_I18N = True  #[cite: 15]
USE_TZ = True  #[cite: 15]

# =============================================
# STATIC & MEDIA FILES
# =============================================
STATIC_URL = '/static/'  #[cite: 15]
STATICFILES_DIRS = [
    BASE_DIR / "store" / "static",  #[cite: 15]
]

MEDIA_URL = '/media/'  #[cite: 15]
MEDIA_ROOT = BASE_DIR / 'media'  #[cite: 15]

# =============================================
# EMAIL BACKEND (FOR FORGOT PASSWORD)
# =============================================
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# =============================================
# REST FRAMEWORK & JWT CONFIGURATION
# =============================================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    )
}

# =============================================
# M-PESA CONFIGURATION
# =============================================
MPESA_CONSUMER_KEY = os.getenv('MPESA_CONSUMER_KEY', 'LFuAPkR8BWp3uQ4NAUdtRPi0umQVYT5sS8XTEbWOgNsgept2')  #[cite: 15]
MPESA_CONSUMER_SECRET = os.getenv('MPESA_CONSUMER_SECRET', 'UCf5kdz3nAe6Gakk2IJb69gBznmX6knNe1eA7MeQD1pzgmoI7PxaxXGWNLiLawtN')  #[cite: 15]
MPESA_PASSKEY = os.getenv('MPESA_PASSKEY', 'bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919')  #[cite: 15]
MPESA_SHORTCODE = os.getenv('MPESA_SHORTCODE', '174379')  #[cite: 15]
MPESA_ENVIRONMENT = os.getenv('MPESA_ENVIRONMENT', 'sandbox')  #[cite: 15]
MPESA_EXPRESS_SHORTCODE = '174379'  #[cite: 15]
if MPESA_ENVIRONMENT == 'production':  #[cite: 15]
    MPESA_BASE_URL = 'https://api.safaricom.co.ke'  #[cite: 15]
else:  #[cite: 15]
    MPESA_BASE_URL = 'https://sandbox.safaricom.co.ke'  #[cite: 15]

MPESA_CALLBACK_URL = os.getenv('MPESA_CALLBACK_URL', 'https://your-domain.com/mpesa/callback/')  #[cite: 15]

# =============================================
# LOGGING CONFIGURATION
# =============================================
LOGGING = {
    'version': 1,  #[cite: 15]
    'disable_existing_loggers': False,  #[cite: 15]
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',  #[cite: 15]
        },
        'file': {
            'level': 'DEBUG',  #[cite: 15]
            'class': 'logging.FileHandler',  #[cite: 15]
            'filename': 'mpesa_debug.log',  #[cite: 15]
        },
    },
    'loggers': {
        'store': {
            'handlers': ['console', 'file'],  #[cite: 15]
            'level': 'DEBUG',  #[cite: 15]
            'propagate': True,  #[cite: 15]
        },
    },
}