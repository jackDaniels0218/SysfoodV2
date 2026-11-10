#!/bin/sh
# Arranque del contenedor: espera a MySQL, crea las tablas, carga la demostración y sirve la aplicación.
set -e

python - <<'PY'
import os, time
import pymysql
for intento in range(60):
    try:
        pymysql.connect(host=os.environ.get("DB_HOST", "db"), port=int(os.environ.get("DB_PORT", "3306")),
                        user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"]).close()
        break
    except Exception:
        print("Esperando a MySQL...", flush=True)
        time.sleep(2)
else:
    raise SystemExit("MySQL no respondió a tiempo.")
PY

python manage.py migrate --noinput
if [ "${CARGAR_DEMO:-1}" = "1" ]; then
    python manage.py cargar_demo
fi

# Tareas automáticas (vencimientos, puntajes, geocodificación, OCR, reportes): cada hora, en segundo plano.
(
    while true; do
        python manage.py ejecutar_tareas || echo "Falló la ejecución de tareas; se reintenta en una hora."
        sleep "${INTERVALO_TAREAS:-3600}"
    done
) &

echo "SysFood listo en http://localhost:${PUERTO:-8000}"
exec waitress-serve --listen=0.0.0.0:8000 --threads=24 sysfood.wsgi:application
