# ARMAS-GADSO

## Resumen

Automatizacion Playwright para programar citas en SEL-SUCAMEC usando un Excel como fuente.

El flujo productivo esta centralizado en `armas_gadso/legacy_flow.py` y se ejecuta desde `run_pipeline.py`.

## Arquitectura

- Entrada de ejecucion: `run_pipeline.py`
- Orquestacion de modo: `armas_gadso/main.py`
- Configuracion y rutas: `armas_gadso/config.py`
- Logica funcional de negocio: `armas_gadso/legacy_flow.py`
- Logging y redireccion de `print`: `armas_gadso/logging_utils.py`

## Estructura del proyecto

```text
ARMAS-GADSO-1.0/
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
├── test/
├── run_pipeline.py
├── run_manual.bat
├── run_scheduled.bat
├── requirements.txt
└── README.md
```

## Flujo funcional (negocio)

`armas_gadso/legacy_flow.py` conserva y ejecuta la logica principal:

1. Lee pendientes desde Excel.
2. Ordena por grupo (`ruc`) y prioridad.
3. Hace login por grupo (SELVA/JV/OTRO) con reintentos y validacion.
4. Navega a CITAS -> RESERVAS DE CITAS.
5. Selecciona tipo de cita (Poligono).
6. Por cada registro:
   - Selecciona sede y fecha.
   - Selecciona hora y valida cupo.
   - Completa datos operativos (tipo operacion, doc vigilante, solicitud).
   - Completa tabla de tipos de arma.
   - Resuelve captcha final.
   - Genera cita y actualiza Excel (estado/observacion).

## Regla de seleccion de hora

La seleccion de hora respeta primero el valor de `hora_rango` del Excel.

- Si la hora exacta tiene cupo: se programa esa hora.
- Si la hora exacta no tiene cupo: recien se activa la logica adaptativa (vecinos y bloque de mediodia, segun configuracion).

Esto evita programar en extremos cuando la hora solicitada si estaba disponible.

## Modo scheduled (produccion)

En `scheduled` se aplica orquestacion multihilo a nivel de workers, manteniendo intacto el flujo base por registro.

- El proceso padre arma unidades de trabajo desde el Excel.
- Cada worker ejecuta el flujo existente en proceso aislado.
- Cada proceso worker trabaja con un Excel temporal filtrado para su unidad.

### Variables del multihilo scheduled

- `SCHEDULED_MULTIWORKER`: `1` habilita multihilo (default en scheduled), `0` lo deshabilita.
- `SCHEDULED_WORKERS`: cantidad de workers (default `4`, maximo `4`).
- `SCHEDULED_WORKER_MODE`: `sticky` (default) o `dynamic`.
- `SCHEDULED_MAX_UNITS`: limite de unidades a procesar (`0` = todas).

## Modos de ejecucion

### Manual

```powershell
python run_pipeline.py --mode manual --hold-browser-open
```

- Permite interaccion humana cuando OCR no resuelve captcha.
- Puede mantener navegador abierto al finalizar.

### Scheduled

```powershell
python run_pipeline.py --mode scheduled
```

- Diseñado para Task Scheduler.
- Sin espera interactiva al cierre.
- Finaliza automaticamente con codigo de salida.

## Scripts BAT

- `run_manual.bat`: ejecuta modo manual.
- `run_scheduled.bat`: ejecuta modo scheduled y redirige salida a `logs/task_scheduler_stdout.log`.

## Logging

Salidas principales:

1. Log de corrida: `logs/run_YYYYMMDD_HHMMSS.log`
2. Salida scheduler: `logs/task_scheduler_stdout.log`

En scheduled multihilo, los artefactos temporales y logs por worker se guardan bajo `logs/.tmp_multihilo_flow_...`.

## Archivo Excel esperado

Ruta por defecto: `data/programaciones-armas.xlsx`.

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

## Variables de entorno principales

Configurar en `.env`:

- `TIPO_DOC`, `NUMERO_DOCUMENTO`, `USUARIO_SEL`, `CLAVE_SEL`
- `SELVA_TIPO_DOC`, `SELVA_NUMERO_DOCUMENTO`, `SELVA_USUARIO_SEL`, `SELVA_CLAVE_SEL`
- `EXCEL_PATH` (opcional)
- `RUN_MODE`, `HOLD_BROWSER_OPEN`
- `MAX_RUN_MINUTES`
- `MAX_LOGIN_RETRIES_PER_GROUP`
- `LOGIN_VALIDATION_TIMEOUT_MS`
- `TERMINAL_CONFIRM_ATTEMPTS`
- `SIN_CUPO_CONFIRM_ATTEMPTS`
- `MAX_UNMAPPED_RETRIES_PER_RECORD`
- `ADAPTIVE_HOUR_SELECTION`
- `ADAPTIVE_HOUR_NOON_FULL_BLOCK`
- `MAX_HOUR_FALLBACK_RETRIES`
- `EASYOCR_LANGS`, `EASYOCR_ALLOWLIST`, `EASYOCR_USE_GPU`

## Instalacion

```powershell
pip install -r requirements.txt
python -m playwright install chromium
```

Dependencias OCR (si no vinieron por `requirements.txt`):

```powershell
pip install easyocr numpy pillow
```

## Ejecucion rapida

Desde terminal en la raiz del proyecto:

```powershell
cmd /c .\run_scheduled.bat
```

## Programador de tareas (Windows)

Configuracion recomendada:

- Programa/script: `C:\Windows\System32\cmd.exe`
- Argumentos: `/c "C:\RUTA\ARMAS-GADSO-1.0\run_scheduled.bat"`
- Iniciar en: `C:\RUTA\ARMAS-GADSO-1.0`
- Ejecutar con privilegios altos: recomendado

Ejemplo por linea de comandos:

```powershell
schtasks /create /tn "ARMAS-GADSO-Test" /sc once /st 11:10 /tr "cmd /c \"C:\Users\fserrano\Desktop\ARMAS-GADSO-1.0\run_scheduled.bat\"" /f
```

## Notas operativas

- En `scheduled` no debe quedar bloqueado esperando `input()` de captcha.
- El flujo aplica reintentos controlados para errores transitorios y de login.
- Si no se puede resolver captcha automaticamente, puede requerirse operacion manual en modo `manual`.
- Archivos `.pyc` en `__pycache__` son cache de Python y se pueden eliminar sin riesgo.
