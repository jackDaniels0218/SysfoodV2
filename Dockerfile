# Imagen de SysFood: Django + Waitress, con Tesseract (OCR en español) y Poppler (PDF a imagen).
# La usan docker-compose.yml (local) y render.yaml (Render).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Dependencias primero: se reutilizan en caché mientras requirements.txt no cambie.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN DB_ENGINE=sqlite DJANGO_DEBUG=1 python manage.py collectstatic --noinput -v0 \
    && chmod +x docker/entrypoint.sh

# La aplicación no corre como root: entrypoint.sh ajusta los permisos de las carpetas de datos
# (también si son discos montados) y pasa al usuario «sysfood» con setpriv antes de iniciar nada.
RUN useradd --create-home --uid 1000 sysfood \
    && mkdir -p protegido backups \
    && chown -R sysfood:sysfood protegido backups

EXPOSE 8000
ENTRYPOINT ["docker/entrypoint.sh"]
