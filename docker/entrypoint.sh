#!/bin/sh
# Arranque del contenedor (Docker Compose o Render): espera a la base de datos, crea las tablas,
# carga la demostración si se pide y sirve la aplicación.
set -e

# Si arranca como root: deja las carpetas de datos (también discos montados) al usuario «sysfood»
# y vuelve a ejecutar este script como ese usuario. La aplicación nunca corre como root.
if [ "$(id -u)" = "0" ]; then
    mkdir -p /app/protegido /app/backups
    chown -R sysfood:sysfood /app/protegido /app/backups
    HOME=/home/sysfood exec setpriv --reuid=sysfood --regid=sysfood --init-groups "$0" "$@"
fi

python - <<'PY'
import os, time
import django
from django.db import connection

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sysfood.settings")
django.setup()
motor = connection.vendor
for intento in range(60):
    try:
        connection.ensure_connection()
        break
    except Exception as exc:
        print(f"Esperando a la base de datos ({motor})... {exc.__class__.__name__}", flush=True)
        time.sleep(2)
else:
    raise SystemExit("La base de datos no respondió a tiempo.")
PY

python manage.py migrate --noinput
if [ "${CARGAR_DEMO:-1}" = "1" ]; then
    python manage.py cargar_demo
else
    python manage.py cargar_demo --solo-admin
fi

# Tareas automáticas (vencimientos, puntajes, geocodificación, OCR, reportes): cada hora, en segundo plano.
(
    while true; do
        python manage.py ejecutar_tareas || echo "Falló la ejecución de tareas; se reintenta en una hora."
        sleep "${INTERVALO_TAREAS:-3600}"
    done
) &

# Render asigna el puerto en $PORT; en Docker Compose se usa 8000.
PUERTO="${PORT:-8000}"
echo "SysFood listo en el puerto ${PUERTO}"
# Detrás del proxy de Render (que termina el HTTPS) hay que confiar en X-Forwarded-Proto. Sin esto,
# waitress descarta la cabecera, Django cree que la visita es HTTP y redirige a HTTPS sin fin
# («demasiadas redirecciones»). Es inofensivo en local: allí no hay proxy.
exec waitress-serve --listen=0.0.0.0:${PUERTO} --threads=${HILOS:-8} \
    --trusted-proxy='*' --trusted-proxy-headers='x-forwarded-proto x-forwarded-for' \
    --clear-untrusted-proxy-headers sysfood.wsgi:application
