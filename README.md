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
- Notificaciones por Microsoft Graph: `armas_gadso/flows/notifications/`
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
|       +-- notifications/
|       |   +-- builders/
|       |   +-- services/
|       |   +-- graph_client.py
|       |   +-- mail_config.py
|       |   +-- mail_logging.py
|       |   +-- manifest_store.py
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
   - Genera cita, toma evidencias y actualiza Excel (estado/observacion).

## Regla de seleccion de hora

La seleccion de hora respeta primero el valor de `hora_rango` del Excel.

- Si la hora exacta tiene cupo: se programa esa hora.
- Si la hora exacta no tiene cupo: recien se activa la logica adaptativa (vecinos y bloque de mediodia, segun configuracion).

## Modo scheduled

En `scheduled` se aplica orquestacion multihilo a nivel de workers, manteniendo intacto el flujo base por registro.

- El proceso padre arma unidades de trabajo desde el Excel.
- Cada worker ejecuta el flujo existente en proceso aislado.
- Cada proceso worker trabaja con un Excel temporal filtrado para su unidad.
- Los workers persisten eventos de correo en manifiestos JSONL.
- El proceso padre consolida y envia los correos al finalizar la corrida.

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

Evidencias relevantes del flujo:

- Paso 1: tabla de programacion de cupos.
- Paso 2: evidencia cuando falla `doc_vigilante` o `nro_solicitud`.
- Paso 4: panel final de confirmacion de cita generada.

En Paso 1, la captura de la tabla usa un recorte rapido por `bounding_box` sobre el area visible de la tabla y deja `locator.screenshot(...)` solo como respaldo. Esto reduce bloqueos en escenarios donde Playwright tarda al esperar fuentes del sitio.

La carpeta `screenshots/` conserva como maximo 10 carpetas de corrida; al generarse una nueva, se elimina la mas antigua.

## Notificaciones por correo

El proyecto puede enviar correos por Microsoft Graph usando autenticacion de aplicacion (`client_credentials`).

La implementacion esta segmentada por responsabilidad:

- `mail_config.py`: lectura de `.env` y validacion de configuracion.
- `graph_client.py`: token OAuth2 y envio HTTP a Graph.
- `mail_logging.py`: resumen de contexto para logs.
- `manifest_store.py`: persistencia de eventos de workers en multihilo.
- `builders/`: asunto y cuerpo HTML por tipo de correo.
- `services/`: logica de negocio por tipo de correo.

### Tipos de correo soportados

1. `SIN_CUPO`
- Se envia cuando el caso queda confirmado como terminal sin vacantes.
- En manual: envio inmediato por caso.
- En scheduled multihilo: correo consolidado al final.
- Adjunta una evidencia representativa por caso, priorizando `sin_cupo` y usando `tabla_inicial` como respaldo.

2. `CONFIRMACION`
- Se envia cuando la cita fue generada correctamente.
- En manual: envio inmediato por caso.
- En scheduled multihilo: correo consolidado al final.
- Adjunta una captura final de confirmacion por caso.

3. `NRO_SOLICITUD`
- Se envia cuando el caso queda confirmado como terminal por no encontrar `Nro. Solicitud` / codigo de pago.
- No se dispara por el primer intento fallido: espera a la confirmacion terminal del caso.
- En manual: envio inmediato por caso.
- En scheduled multihilo: correo consolidado al final.
- Adjunta la ultima evidencia disponible del Paso 2 para ese caso.

### Comportamiento en multihilo

Si una corrida tiene resultados mixtos, los correos se consolidan por tipo de resultado, no por worker.

Ejemplo:

- `3` confirmaciones exitosas
- `1` caso `SIN_CUPO`
- `1` caso `NRO_SOLICITUD`

Resultado esperado:

- `1` correo consolidado de confirmaciones
- `1` correo consolidado de sin cupo
- `1` correo consolidado de nro_solicitud

Si una evidencia no existe, el caso igual aparece en la tabla del correo con `Evidencia = No disponible`.

### Requisitos de Microsoft Graph

- `Mail.Send` como `Application permission`
- `Admin consent`
- `MS_GRAPH_SENDER` debe ser un buzon real del tenant
- si Exchange aplica restricciones por app o por buzon, el remitente debe estar autorizado

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

### Variables de correo Microsoft Graph

- `MS_GRAPH_MAIL_ENABLED`
- `MS_GRAPH_MAIL_STEP1_ENABLED`
- `MS_GRAPH_MAIL_CONFIRMATION_ENABLED`
- `MS_GRAPH_MAIL_NRO_SOLICITUD_ENABLED`
- `MS_GRAPH_TENANT_ID`
- `MS_GRAPH_CLIENT_ID`
- `MS_GRAPH_CLIENT_SECRET`
- `MS_GRAPH_SENDER`
- `MS_GRAPH_TO`
- `MS_GRAPH_CC`
- `MS_GRAPH_SUBJECT_PREFIX`

Ejemplo:

```env
MS_GRAPH_MAIL_ENABLED=1
MS_GRAPH_MAIL_STEP1_ENABLED=1
MS_GRAPH_MAIL_CONFIRMATION_ENABLED=1
MS_GRAPH_MAIL_NRO_SOLICITUD_ENABLED=1
MS_GRAPH_TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
MS_GRAPH_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
MS_GRAPH_CLIENT_SECRET=valor_real_del_secreto
MS_GRAPH_SENDER=notificaciones@tu-dominio.com
MS_GRAPH_TO=destino1@tu-dominio.com;destino2@tu-dominio.com
MS_GRAPH_CC=cc1@tu-dominio.com;cc2@tu-dominio.com
MS_GRAPH_SUBJECT_PREFIX=ARMAS-GADSO PRUEBA
```

Notas:

- En `MS_GRAPH_CLIENT_SECRET` debe ir el `Value` del secreto, no el `Secret ID`.
- `MS_GRAPH_TO` y `MS_GRAPH_CC` aceptan multiples destinatarios separados por `;`.

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
