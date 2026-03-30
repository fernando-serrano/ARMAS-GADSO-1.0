# ARMAS-GADSO

## Resumen tecnico

Este repositorio ejecuta un flujo Playwright para programacion de citas en SEL-SUCAMEC usando datos de Excel.

La arquitectura actual separa:

- Entrada de ejecucion: `run_pipeline.py`
- Orquestacion y modo de corrida: `armas_gadso/main.py`
- Carga de configuracion: `armas_gadso/config.py`
- Flujo legado (logica funcional): `armas_gadso/legacy_flow.py`
- Logger y redireccion de `print`: `armas_gadso/logging_utils.py`

El archivo `pipeline-armas.py` puede conservarse como referencia historica, pero la ejecucion real usa `armas_gadso/legacy_flow.py`.

## Estructura del proyecto

```text
ARMAS-GADSO/
├── armas_gadso/
│   ├── __init__.py
│   ├── config.py
│   ├── legacy_flow.py
│   ├── logging_utils.py
│   └── main.py
├── data/
│   └── programaciones-armas.xlsx
├── logs/
├── screenshots/
├── .env.example
├── .gitignore
├── README.md
├── requirements.txt
├── test/
│   ├── run_test_captcha.py
│   ├── run_test_easyocr.py
│   ├── run_test_easyocr_base.py
│   └── run_test_hora_flexible.py
├── run_manual.bat
├── run_pipeline.py
└── run_scheduled.bat
```

## Flujo funcional implementado

`armas_gadso/legacy_flow.py` conserva la logica operativa del pipeline original:

1. Carga pendientes desde Excel.
2. Ordena por grupo RUC y prioridad.
3. Hace login por grupo (SELVA/JV/OTRO) con reintentos.
4. Navega a CITAS -> RESERVAS DE CITAS.
5. Selecciona tipo de cita (Poligono).
6. Para cada registro:
	- Selecciona sede y fecha.
	- Busca hora, valida cupo.
	- Completa paso 2 (tipo operacion, doc vigilante, nro solicitud).
	- Completa tabla de tipos de arma.
	- Resuelve captcha de fase 3.
	- Genera cita con reintentos de captcha final.
	- Actualiza Excel (estado u observacion segun resultado).

## Recuperacion ante desincronizacion UI

Se agrego manejo para estados transitorios de UI (latencia/servidor/estado intermedio):

- Si el contexto de reserva no esta listo (formulario ausente o combo de cita no confirmado), el flujo marca `RELOGIN_UI_DESYNC`.
- En ese caso no se registra error de negocio inmediato: se reloguea el grupo y se reintenta.
- Si al volver el registro ya no esta en estado pendiente, se omite y se continua.

Esto evita falsos negativos cuando la pagina queda en estado intermedio.

## Modos de ejecucion

### Manual

Comando:

```powershell
python run_pipeline.py --mode manual --hold-browser-open
```

Comportamiento:

- Permite interaccion humana para captcha si OCR falla.
- Puede mantener navegador abierto al finalizar (`--hold-browser-open`).

### Scheduled

Comando:

```powershell
python run_pipeline.py --mode scheduled
```

Comportamiento:

- No debe bloquearse al final por espera interactiva.
- Finaliza automaticamente al terminar (exito o error).
- Pensado para Programador de tareas.

## Scripts BAT

- `run_manual.bat` -> ejecuta modo manual.
- `run_scheduled.bat` -> ejecuta modo scheduled y redirige salida a `logs/task_scheduler_stdout.log`.
- `run_test_hora_flexible.py` -> runner de prueba para selección horaria adaptativa y replanificación por cupos ocupados.
- `run_test_easyocr.py` -> runner de prueba OCR con EasyOCR para captcha de login y captcha final.

Para pruebas EasyOCR (opcional):

```powershell
pip install easyocr numpy pillow
```

## Variables de entorno principales

Configurar en `.env`:

- `TIPO_DOC`
- `NUMERO_DOCUMENTO`
- `USUARIO_SEL`
- `CLAVE_SEL`
- `SELVA_TIPO_DOC`
- `SELVA_NUMERO_DOCUMENTO`
- `SELVA_USUARIO_SEL`
- `SELVA_CLAVE_SEL`
- `EXCEL_PATH` (opcional, por defecto `data/programaciones-armas.xlsx`)
- `VALIDAR_FECHA_PROGRAMACION_HOY` (`1` por defecto)
- `RUN_MODE` (`manual` o `scheduled`, normalmente lo inyecta `main.py`)
- `HOLD_BROWSER_OPEN` (`0/1`, normalmente lo inyecta `main.py`)
- `MAX_RUN_MINUTES` (opcional, `0` = sin límite)
- `MAX_LOGIN_RETRIES_PER_GROUP` (opcional, por defecto `12`)
- `LOGIN_VALIDATION_TIMEOUT_MS` (opcional, por defecto `6000`)
- `TERMINAL_CONFIRM_ATTEMPTS` (opcional, por defecto `2`)
- `SIN_CUPO_CONFIRM_ATTEMPTS` (opcional, por defecto `1`)
- `MAX_UNMAPPED_RETRIES_PER_RECORD` (opcional, por defecto `4`; `0` = sin limite)
- `ADAPTIVE_HOUR_SELECTION` (opcional, `1` activa selección flexible de horario; por defecto `0`)
- `ADAPTIVE_HOUR_NOON_FULL_BLOCK` (opcional, por defecto `1`; si la hora está entre `11:45-13:00`, evalúa todo el bloque y elige mayor cupo)
- `MAX_HOUR_FALLBACK_RETRIES` (opcional, por defecto `8`; reintentos máximos cuando al final aparece "cupos ocupados")

## Excel esperado

Columnas clave:

- `estado`
- `sede`
- `fecha` (y opcional `fecha_programacion`)
- `hora_rango`
- `tipo_operacion`
- `nro_solicitud`
- `doc_vigilante` (o `dni`)
- `tipo_arma`
- `arma`
- `ruc`
- `prioridad`

El flujo deduplica trabajos y mantiene trazabilidad con indices relacionados para actualizar varias filas cuando corresponde.

## Logging

Hay dos salidas:

1. Archivo por corrida: `logs/run_YYYYMMDD_HHMMSS.log`
2. Salida scheduler: `logs/task_scheduler_stdout.log` (si se usa `run_scheduled.bat`)

`armas_gadso/logging_utils.py` incluye manejo robusto para evitar recursiones de logging cuando hay errores de codificacion en consola Windows.

## Programador de tareas (Windows)

Configuracion recomendada:

- Programa/script: `C:\Windows\System32\cmd.exe`
- Argumentos: `/c "C:\RUTA\ARMAS-GADSO\run_scheduled.bat"`
- Iniciar en: `C:\RUTA\ARMAS-GADSO`
- Ejecutar con privilegios mas altos: recomendado

## Instalacion

```powershell
pip install -r requirements.txt
python -m playwright install chromium
```

## Nota operativa

El portal puede requerir verificacion visual. Si no es posible resolver captcha automaticamente, el flujo puede requerir operacion manual.

En modo `scheduled`, el flujo ahora evita quedar bloqueado esperando `input()` manual de captcha: si OCR no resuelve, finaliza con error controlado para que el scheduler no quede colgado.

El login inicial ahora usa:

- Reintentos finitos por grupo (`MAX_LOGIN_RETRIES_PER_GROUP`) para evitar saturación del servidor.
- Backoff incremental entre intentos.
- Validación de acceso con timeout configurable (`LOGIN_VALIDATION_TIMEOUT_MS`) y fallback por URL de inicio para reducir falsos negativos.

El procesamiento de registros usa una cola iterativa: errores transitorios se reencolan y las causas terminales se registran por confirmación.

- `SIN_CUPO` usa `SIN_CUPO_CONFIRM_ATTEMPTS` (por defecto `1`).
- Otras causales terminales (`NRO_SOLICITUD`, `DOC_VIGILANTE`, `HORA_NO_DISPONIBLE`, `FECHA_NO_DISPONIBLE`) usan `TERMINAL_CONFIRM_ATTEMPTS` (por defecto `2`).
- Los errores no mapeados tienen tope por registro con `MAX_UNMAPPED_RETRIES_PER_RECORD` para evitar ciclos infinitos de reintento.

## Archivo pyc

Archivos como `run_pipeline.cpython-314.pyc` son cache de bytecode Python en `__pycache__`.

- No se editan.
- Se pueden borrar sin riesgo.
- Python los regenera automaticamente.

# ¿Cómo levantamos el proyecto?
    Para levantar el proyecto desde su archivo run_scheduled.bat requerimos el siguiente comando desde la terminal de tu editar de código:
    cmd /c .\run_scheduled.bat

# ¿Cómo programo una tarea desde el cmd de Windows?
	Para programar usa el siguiente comando: schtasks /create /tn "ARMAS-GADSO-Test" /sc once /st 13:03 /tr "cmd /c \"C:\RUTA\ARMAS-GADSO-1.0\run_scheduled.bat\"" /f

    Para ello solo se debe cambiar el campo de la fecha
    