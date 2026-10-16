@echo off
REM Inicia SysFood sin Docker en Windows. Doble clic sobre este archivo.
REM La primera vez instala todo; las siguientes solo arranca.
cd /d "%~dp0"
chcp 65001 >nul

where python >nul 2>nul
if errorlevel 1 (
    echo Instale Python 3.10 o superior desde https://www.python.org/downloads/
    echo y marque la casilla "Add Python to PATH" durante la instalacion.
    pause
    exit /b 1
)

if not exist .venv (
    echo ^>^> Creando entorno virtual...
    python -m venv .venv || goto error
)
echo ^>^> Instalando dependencias...
.venv\Scripts\python -m pip install -q --upgrade pip
.venv\Scripts\python -m pip install -q -r requirements.txt || goto error

if not exist .env (
    echo ^>^> Creando .env ^(base de datos SQLite para pruebas locales^)...
    powershell -NoProfile -Command "(Get-Content .env.example) -replace '^DB_ENGINE=mysql','DB_ENGINE=sqlite' | Set-Content .env -Encoding UTF8"
)

.venv\Scripts\python manage.py migrate --noinput || goto error
.venv\Scripts\python manage.py cargar_demo || goto error

echo.
echo ==============================================================
echo  SysFood listo en  http://127.0.0.1:8000
echo  Usuario: admin@sysfood.local   Contrasena: Sysfood2025*
echo  (Cierre esta ventana o presione Ctrl+C para detener)
echo ==============================================================
start "" http://127.0.0.1:8000
.venv\Scripts\python manage.py runserver 127.0.0.1:8000
goto :eof

:error
echo.
echo Ocurrio un error. Revise los mensajes de arriba.
pause
exit /b 1
