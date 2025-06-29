# Usar una imagen base de Python
FROM python:3.12-slim

# Establecer variables de entorno
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Establecer el directorio de trabajo
WORKDIR /app

# Instalar dependencias
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código del proyecto
COPY . /app/

# Exponer el puerto en el que correrá Gunicorn
EXPOSE 8000

# Comando para ejecutar la aplicación
CMD ["gunicorn", "laundry_app.wsgi:application", "--bind", "0.0.0.0:8000"]