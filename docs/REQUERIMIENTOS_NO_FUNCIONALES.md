# Cómo cambiar un requerimiento no funcional

Todos los valores de los requerimientos no funcionales están en un solo archivo: [`sysfood/rnf.py`](../sysfood/rnf.py). Ningún otro archivo los repite: la configuración de Django, las vistas, los validadores, las pruebas, el script del contenedor y la integración continua los leen de ahí.

## Pasos

1. Abra `sysfood/rnf.py`, cambie el valor y guarde.
2. Reinicie el sistema:
   - **En local:** cierre y vuelva a abrir `iniciar.bat` (o `iniciar.sh`).
   - **En Render:** `git commit` y `git push`; Render vuelve a desplegar solo.
3. Compruebe con las pruebas: `python manage.py test`. Las pruebas leen los mismos valores, así que siguen pasando con el valor nuevo.

Si el valor no es válido (por ejemplo, `TAM_MAX_ARCHIVO_MB = 99`), el sistema no arranca y dice qué valor corregir.

## Qué se puede cambiar

| RNF | Valor en `rnf.py` | Efecto | Cómo demostrarlo |
| --- | --- | --- | --- |
| 17 Seguridad | `INTENTOS_INGRESO` ★ | Intentos fallidos antes de bloquear la cuenta | Equivocarse esa cantidad de veces al ingresar |
| 17 Seguridad | `MINUTOS_BLOQUEO` ★ | Duración del bloqueo | Aparece en el mensaje de cuenta bloqueada |
| 17 Seguridad | `VIGENCIA_TOKEN_MINUTOS` ★ | Vigencia del enlace de recuperación | Aparece en el correo de recuperación |
| 17 Seguridad | `SESION_MINUTOS` | Duración de la sesión | Herramientas del navegador › Cookies › `sessionid` › vencimiento |
| 17 Seguridad | `SESION_POR_INACTIVIDAD` | `True`: la sesión se cierra tras `SESION_MINUTOS` sin actividad | Con `SESION_MINUTOS = 1`, esperar un minuto sin tocar nada y recargar |
| 17 Seguridad | `SESION_CERRAR_CON_NAVEGADOR` | `True`: la sesión termina al cerrar el navegador | Cerrar y abrir el navegador |
| 17 Seguridad | `CONTRASENA_LONGITUD_MINIMA` | Longitud mínima de la contraseña | Registrarse con una contraseña más corta |
| 17 Seguridad | `CONTRASENA_EXIGE_MAYUSCULA`, `_MINUSCULA`, `_NUMERO`, `_ESPECIAL` | Tipos de carácter exigidos | Registrarse sin ese tipo de carácter; el asistente de ayuda también actualiza los requisitos |
| 17 Seguridad | `CONTRASENA_ITERACIONES_PBKDF2` | Iteraciones del hash con sal | En la base, la columna de la contraseña muestra `pbkdf2_sha256$<iteraciones>$…` después de ingresar |
| 17 Seguridad | `HSTS_SEGUNDOS` | Tiempo de HSTS (con `DJANGO_HTTPS=1`) | Cabecera `Strict-Transport-Security` en Render |
| 18 Protección de datos | `TAM_MAX_ARCHIVO_MB` ★ | Tamaño máximo de un documento (1 a 25) | Cargar un archivo más grande |
| 18 Protección de datos | `FORMATOS_PERMITIDOS` ★ | Formatos aceptados (pdf, jpg, png) | Cargar un formato quitado de la lista |
| 18 Protección de datos | `MAPA_DESPLAZAMIENTO_M` ★ | Metros que se mueven los puntos al exportar el mapa | Exportar el mapa y comparar coordenadas |
| 16 Rendimiento | `TIEMPO_MAX_RESPUESTA_S` | Tiempo máximo por página que exige la prueba | `python manage.py test core.tests.test_core.RendimientoTests` |
| 16 Rendimiento | `TIEMPO_MAX_CARGA_DOCUMENTO_S` | Tiempo máximo para cargar un documento del tamaño máximo | La misma prueba |
| 16 Rendimiento | `REGISTROS_POR_PAGINA` | Registros por página de cada lista | Abrir la lista y contar |
| 16 Rendimiento | `HILOS_SERVIDOR` | Peticiones simultáneas del servidor (contenedor) | Registro de arranque en Render |
| 16 Rendimiento | `INTERVALO_TAREAS_S` | Cada cuánto corren las tareas automáticas (contenedor) | Sistema › Tareas automáticas › última ejecución |
| 16 Rendimiento | `TIEMPO_ESPERA_GEOCODIFICACION_S` | Espera máxima al servicio de mapas | — |
| 16 Rendimiento | `LIMITE_FORMULARIO_MB`, `LIMITE_ARCHIVO_EN_MEMORIA_MB` | Límites de las peticiones | — |
| 20 y 21 | `IDIOMA`, `ZONA_HORARIA` | Idioma y zona horaria | Formato de fechas y horas |
| 31 Calidad | `COBERTURA_MINIMA` | Cobertura mínima que exige la integración continua | GitHub › Actions |

★ También aparece en **Sistema › Parámetros**. Al arrancar, si el valor cambió en `rnf.py`, se copia a Parámetros y queda en la bitácora («desde sysfood/rnf.py»). Mientras no se cambie en el código, se respeta lo que el administrador haya puesto en pantalla.

## Lo que se cambia por variables de entorno

Lo que depende del servidor y no del código se configura en `.env` (local) o en **Render › Environment**: HTTPS (`DJANGO_HTTPS`), base de datos (`DATABASE_URL`, `DB_ENGINE`), correo (`EMAIL_*`), hosts permitidos y modo de depuración. Ver [.env.example](../.env.example).

## Pruebas

`core/tests/test_rnf.py` comprueba que la configuración sale de `rnf.py`, que la paginación y las reglas de la contraseña cambian con él, y que un cambio en el código llega a Parámetros sin pisar el valor que haya puesto el administrador.
