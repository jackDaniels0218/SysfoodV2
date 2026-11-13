"""Requerimientos no funcionales de SysFood: todos los valores en un solo archivo.

CÓMO CAMBIAR UN REQUERIMIENTO NO FUNCIONAL
1. Cambie el valor aquí y guarde el archivo.
2. Reinicie el sistema:
   - En local, cierre y vuelva a abrir iniciar.bat (o iniciar.sh).
   - En Render, haga commit y push: Render vuelve a desplegar solo.
3. Verifique con las pruebas:  python manage.py test
   Las pruebas leen estos mismos valores, así que siguen en verde con el valor nuevo.

Los valores marcados con [Parámetro] también se ven en Sistema › Parámetros. Al arrancar, si el
valor de este archivo cambió, se copia a Parámetros y queda en la bitácora. Mientras no lo cambie
aquí, se respeta lo que el administrador haya puesto en pantalla.

Este archivo no importa nada de Django: lo leen la configuración, las vistas, las pruebas, el
script del contenedor y la integración continua.
"""

# ============================================================================================
# RNF 17 · Seguridad
# ============================================================================================

# Bloqueo de la cuenta
INTENTOS_INGRESO = 5  # [Parámetro] Intentos fallidos antes de bloquear la cuenta (1 a 20).
MINUTOS_BLOQUEO = 15  # [Parámetro] Minutos que dura el bloqueo (1 a 1440).
VIGENCIA_TOKEN_MINUTOS = 60  # [Parámetro] Vigencia del enlace de recuperación de contraseña (5 a 1440).

# Sesión
SESION_MINUTOS = 480  # Tiempo de vida de la sesión: 480 minutos = 8 horas.
SESION_POR_INACTIVIDAD = False  # True: el tiempo se cuenta desde el último clic (cierre por inactividad).
SESION_CERRAR_CON_NAVEGADOR = False  # True: la sesión termina al cerrar el navegador.

# Contraseñas
CONTRASENA_LONGITUD_MINIMA = 8
CONTRASENA_EXIGE_MAYUSCULA = True
CONTRASENA_EXIGE_MINUSCULA = True
CONTRASENA_EXIGE_NUMERO = True
CONTRASENA_EXIGE_ESPECIAL = True
# Iteraciones de PBKDF2 (hash con sal). Más iteraciones = más difícil de romper, pero el ingreso es
# más lento. Las contraseñas guardadas se actualizan solas la próxima vez que el usuario ingresa.
CONTRASENA_ITERACIONES_PBKDF2 = 1_000_000

# HTTPS (se activa con la variable de entorno DJANGO_HTTPS=1)
HSTS_SEGUNDOS = 31_536_000  # Un año: el navegador solo usará HTTPS con el sitio durante ese tiempo.

# ============================================================================================
# RNF 18 · Protección de datos
# ============================================================================================

TAM_MAX_ARCHIVO_MB = 5  # [Parámetro] Tamaño máximo de cada documento cargado (1 a 25).
FORMATOS_PERMITIDOS = "pdf,jpg,png"  # [Parámetro] Solo se admiten pdf, jpg y png, separados por comas.
MAPA_DESPLAZAMIENTO_M = 300  # [Parámetro] Metros que se mueven los puntos al exportar el mapa (0 a 5000).

# ============================================================================================
# RNF 16 · Rendimiento
# ============================================================================================

# Límites que exigen las pruebas automáticas (core/tests/test_core.py::RendimientoTests).
TIEMPO_MAX_RESPUESTA_S = 2  # Cada página común debe responder en este tiempo o menos.
TIEMPO_MAX_CARGA_DOCUMENTO_S = 5  # Cargar un documento del tamaño máximo debe tardar menos que esto.

# Registros que se muestran en cada página de las listas.
REGISTROS_POR_PAGINA = {
    "catalogo": 12,  # Catálogo de productos del beneficiario
    "inventario": 24,  # Inventario (tarjetas)
    "donaciones_admin": 20,  # Donaciones (administrador)
    "mis_donaciones": 15,  # Mis donaciones (donante)
    "solicitudes_admin": 20,  # Solicitudes (administrador)
    "mis_solicitudes": 15,  # Mis solicitudes (beneficiario)
    "entregas": 20,  # Entregas
    "usuarios": 20,  # Usuarios (administrador)
    "notificaciones": 20,  # Notificaciones
    "trazabilidad": 30,  # Bitácora y trazabilidad
}

# Servidor y procesos automáticos (los lee docker/entrypoint.sh)
HILOS_SERVIDOR = 8  # Peticiones que el servidor atiende al mismo tiempo.
INTERVALO_TAREAS_S = 3600  # Cada cuánto corren las tareas automáticas en el contenedor (1 hora).
TIEMPO_ESPERA_GEOCODIFICACION_S = 8  # Segundos de espera al servicio de mapas antes de reintentar.

# Tamaño máximo del cuerpo de una petición sin contar los archivos (formularios).
LIMITE_FORMULARIO_MB = 30
# Hasta este tamaño un archivo cargado se procesa en memoria; si es mayor, en disco.
LIMITE_ARCHIVO_EN_MEMORIA_MB = 10

# ============================================================================================
# RNF 20 · Usabilidad y RNF 21 · Tecnología
# ============================================================================================

IDIOMA = "es-co"
ZONA_HORARIA = "America/Bogota"

# ============================================================================================
# RNF 31 · Calidad del software
# ============================================================================================

COBERTURA_MINIMA = 80  # Porcentaje mínimo de código cubierto por pruebas (lo exige la integración continua).


# --------------------------------------------------------------------------------------------
# No modificar: relación entre los valores [Parámetro] y su clave en Sistema › Parámetros.
PARAMETROS = {
    "intentos_ingreso": INTENTOS_INGRESO,
    "minutos_bloqueo": MINUTOS_BLOQUEO,
    "vigencia_token_minutos": VIGENCIA_TOKEN_MINUTOS,
    "tam_max_archivo_mb": TAM_MAX_ARCHIVO_MB,
    "formatos_permitidos": FORMATOS_PERMITIDOS,
    "mapa_desplazamiento_m": MAPA_DESPLAZAMIENTO_M,
}


def por_pagina(lista):
    """Registros por página de una lista; 20 si la lista no está en REGISTROS_POR_PAGINA."""
    return REGISTROS_POR_PAGINA.get(lista, 20)


def requisitos_contrasena():
    """Requisitos de la contraseña en palabras, según los valores de este archivo."""
    exigidos = [
        texto
        for exige, texto in (
            (CONTRASENA_EXIGE_MAYUSCULA, "mayúsculas"),
            (CONTRASENA_EXIGE_MINUSCULA, "minúsculas"),
            (CONTRASENA_EXIGE_NUMERO, "números"),
            (CONTRASENA_EXIGE_ESPECIAL, "un símbolo"),
        )
        if exige
    ]
    frase = f"tener al menos {CONTRASENA_LONGITUD_MINIMA} caracteres"
    if exigidos:
        lista = exigidos[0] if len(exigidos) == 1 else ", ".join(exigidos[:-1]) + " y " + exigidos[-1]
        frase += f", con {lista}"
    return frase
