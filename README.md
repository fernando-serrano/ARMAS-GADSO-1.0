# ARMAS-GADSO

## Resumen

Automatizacion Playwright para programar citas en SEL-SUCAMEC usando un Excel como fuente.

El flujo productivo se ejecuta desde `run_pipeline.py`, entra por `armas_gadso/main.py` y orquesta el pipeline actual desde `armas_gadso/flows/orchestration_flow/`.

## Arquitectura

- Entrada de ejecucion: `run_pipeline.py`
- Orquestacion de modo: `armas_gadso/main.py`
- Configuracion y rutas: `armas_gadso/config.py`
- Dominio compartido: `armas_gadso/exceptions.py`, `armas_gadso/utils.py`, `armas_gadso/excel.py`
- Flujos refactorizados por dominio: `armas_gadso/flows/`
- Orquestacion principal: `armas_gadso/flows/orchestration_flow/`
- Logging y redireccion de `print`: `armas_gadso/flows/logging_flow/`
- Compatibilidad legacy: `armas_gadso/legacy_flow.py`, `armas_gadso/logging_utils.py`

## Estructura del proyecto

```text
ARMAS-GADSO-1.0/
+-- armas_gadso/
|   +-- __init__.py
|   +-- config.py
|   +-- excel.py
|   +-- exceptions.py
|   +-- legacy_flow.py
|   +-- logging_utils.py
|   +-- main.py
|   +-- utils.py
|   +-- flows/
|       +-- captcha_flow/
|       +-- cita_flow/
|       |   +-- step_1_reserva_cupos/
|       |   +-- step_2_datos_tramite/
|       |   +-- step_3_validacion_final/
|       |   +-- step_4_confirmacion/
|       +-- evidence_flow/
|       +-- logging_flow/
|       +-- login_flow/
|       +-- orchestration_flow/
|           +-- group_runner.py
|           +-- legacy_pipeline.py
|           +-- monitoring.py
|           +-- navigation.py
|           +-- pipeline.py
|           +-- runtime.py
|           +-- workers.py
+-- data/
+-- logs/
+-- screenshots/
+-- test/
+-- run_pipeline.py
+-- run_manual.bat
+-- run_scheduled.bat
+-- requirements.txt
+-- README.md
```

## Flujo funcional

`armas_gadso/flows/orchestration_flow/legacy_pipeline.py` conserva y ejecuta la logica principal actual. `armas_gadso/legacy_flow.py` se mantiene solo como wrapper de compatibilidad para tests o imports antiguos.

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

## Modo scheduled

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

### Scheduled

```powershell
python run_pipeline.py --mode scheduled
```

## Logging

Cada ejecucion crea una carpeta con formato `aaaammdd_hhmmss` dentro de `logs/`.

- Log de corrida: `logs/aaaammdd_hhmmss/run_aaaammdd_hhmmss.log`
- Salida scheduler: `logs/aaaammdd_hhmmss/task_scheduler_stdout.log`
- En scheduled multihilo: `logs/aaaammdd_hhmmss/logs_w1/`, `logs/aaaammdd_hhmmss/logs_w2/`, etc.

La carpeta `logs/` conserva como maximo 10 carpetas de corrida; al generarse una nueva, se elimina la mas antigua.

## Screenshots

Cada ejecucion crea tambien una carpeta con el mismo formato dentro de `screenshots/`.

- Evidencias de corrida: `screenshots/aaaammdd_hhmmss/`
- En scheduled multihilo: `screenshots/aaaammdd_hhmmss/screenshots_w1/`, `screenshots/aaaammdd_hhmmss/screenshots_w2/`, etc.

Cuando no hay cupos disponibles, el flujo toma una captura de la tabla de programacion antes de limpiar el formulario.

La carpeta `screenshots/` conserva como maximo 10 carpetas de corrida; al generarse una nueva, se elimina la mas antigua.

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

Dependencias OCR adicionales:

```powershell
pip install easyocr numpy pillow
```

## Ejecucion rapida

```powershell
cmd /c .\run_scheduled.bat
```

## Notas operativas

- En `scheduled` no debe quedar bloqueado esperando `input()` de captcha.
- El flujo aplica reintentos controlados para errores transitorios y de login.
- Si no se puede resolver captcha automaticamente, puede requerirse operacion manual en modo `manual`.
- Archivos `.pyc` en `__pycache__` son cache de Python y se pueden eliminar sin riesgo.
