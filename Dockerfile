# 1. Usar una imagen oficial de Python como base
FROM python:3.11-slim

# 2. Establecer variables de entorno
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 3. Crear y establecer el directorio de trabajo dentro del contenedor
WORKDIR /app

# 4. Instalar dependencias del sistema (para Pillow y psycopg2)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 5. Instalar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copiar el resto del código del proyecto al contenedor
COPY . .

# 7. Crear directorios para los archivos estáticos y multimedia
RUN mkdir -p /app/staticfiles
RUN mkdir -p /app/media

# 8. Exponer el puerto que Gunicorn usará
EXPOSE 8000