#!/usr/bin/env bash
# Inicia SysFood sin Docker (Linux y macOS). Uso: ./iniciar.sh
# La primera vez instala todo; las siguientes solo arranca.
set -e
cd "$(dirname "$0")"

PY=python3
command -v $PY >/dev/null 2>&1 || PY=python
command -v $PY >/dev/null 2>&1 || { echo "Instale Python 3.10 o superior: https://www.python.org/downloads/"; exit 1; }

if [ ! -d .venv ]; then
    echo ">> Creando entorno virtual..."
    $PY -m venv .venv
fi
.venv/bin/python -m pip install -q --upgrade pip
echo ">> Instalando dependencias..."
.venv/bin/python -m pip install -q -r requirements.txt

if [ ! -f .env ]; then
    echo ">> Creando .env (base de datos SQLite para pruebas locales)..."
    sed 's/^DB_ENGINE=mysql/DB_ENGINE=sqlite/' .env.example > .env
fi

.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py cargar_demo

echo ""
echo "=============================================================="
echo " SysFood listo en  http://127.0.0.1:8000"
echo " Usuario: admin@sysfood.local   Contraseña: Sysfood2025*"
echo " (Ctrl+C para detener)"
echo "=============================================================="
.venv/bin/python manage.py runserver 127.0.0.1:8000
