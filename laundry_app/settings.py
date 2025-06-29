# settings.py

import os
from pathlib import Path
from dotenv import load_dotenv # <--- AÑADIR ESTA LÍNEA

# Cargar variables de entorno desde .env
load_dotenv() # <--- AÑADIR ESTA LÍNEA

BASE_DIR = Path(__file__).resolve().parent.parent

# --- CAMBIO IMPORTANTE: Cargar la clave secreta desde el entorno ---
SECRET_KEY = os.getenv('SECRET_KEY')

# --- CAMBIO IMPORTANTE: Controlar el modo DEBUG desde el entorno ---
# El '1' como string significa True. Cualquier otra cosa es False.
DEBUG = os.getenv('DEBUG') == '1'

# --- CAMBIO IMPORTANTE: Cargar los hosts permitidos desde el entorno ---
ALLOWED_HOSTS_str = os.getenv('ALLOWED_HOSTS', '')
ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS_str.split(',') if host.strip()]

# ... (resto de tus apps instaladas) ...
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
    'django_select2',
]
# ...

# --- CAMBIO IMPORTANTE: Configuración de la Base de Datos PostgreSQL ---
# Reemplaza tu configuración de DATABASES con esto.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB'),
        'USER': os.getenv('POSTGRES_USER'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD'),
        'HOST': os.getenv('DATABASE_HOST'), # Esto será 'db', el nombre del servicio en docker-compose
        'PORT': 5432,
    }
}

# ... (resto de la configuración) ...

# --- CAMBIO IMPORTANTE: Configuración de archivos estáticos y de medios ---
# Tu STATIC_URL ya está bien.
STATIC_URL = 'static/'
# STATICFILES_DIRS le dice a Django dónde encontrar tus archivos estáticos durante el desarrollo.
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
# STATIC_ROOT es la carpeta a la que `collectstatic` copiará todos los archivos estáticos para producción.
STATIC_ROOT = BASE_DIR / 'staticfiles' # <--- AÑADIR ESTA LÍNEA

MEDIA_URL = '/media/'
# MEDIA_ROOT apunta a la carpeta que definimos en el Dockerfile y docker-compose.yml
MEDIA_ROOT = BASE_DIR / 'media' # <--- ASEGURARSE QUE ESTÉ ASÍ

# ...

# --- AÑADIR AL FINAL PARA PRODUCCIÓN SEGURA (OPCIONAL PERO RECOMENDADO) ---
CSRF_TRUSTED_ORIGINS = [f'https://{host}' for host in ALLOWED_HOSTS if host not in ['localhost']]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True