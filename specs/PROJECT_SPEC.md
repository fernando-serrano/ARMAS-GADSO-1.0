# ARMAS-GADSO - Sintesis funcional y reglas de negocio

## Proposito

ARMAS-GADSO automatiza la programacion de citas en SEL-SUCAMEC para tramites de armas desde un Excel operativo. El bot lee registros pendientes, reserva cupos, completa datos del tramite, valida armas, resuelve captcha, genera la cita, toma evidencias, actualiza el Excel y envia correos por Microsoft Graph segun el resultado.

El flujo productivo entra por `run_pipeline.py`, pasa por `armas_gadso/main.py` y se orquesta principalmente desde `armas_gadso/flows/orchestration_flow/legacy_pipeline.py` y `group_runner.py`.

## Componentes principales

- `armas_gadso/config.py`: carga rutas, modo de ejecucion y configuracion general.
- `armas_gadso/excel.py`: lectura del Excel, ordenamiento de trabajos, agrupacion por RUC, deduplicacion y actualizacion de estado/observaciones.
- `armas_gadso/utils.py`: normalizacion de textos, fechas, horas, RUC, tokens de solicitud y valores de Excel.
- `armas_gadso/exceptions.py`: excepciones de dominio para causales controladas.
- `flows/login_flow/`: apertura de navegador, login SEL y credenciales por grupo.
- `flows/orchestration_flow/`: coordinacion del flujo, multihilo scheduled, reintentos, clasificacion terminal y recuperacion.
- `flows/cita_flow/step_1_reserva_cupos/`: sede, fecha, hora, cupos y seleccion adaptativa de horario.
- `flows/cita_flow/step_2_datos_tramite/`: tipo de operacion, tipo de licencia, documento vigilante, Nro. Solicitud y tabla de armas.
- `flows/cita_flow/step_3_validacion_final/`: resumen, captcha final, terminos y generacion de cita.
- `flows/cita_flow/step_4_confirmacion/`: evidencia final de cita generada.
- `flows/evidence_flow/`: screenshots por paso.
- `flows/notifications/`: correos Microsoft Graph, manifiestos multihilo y builders HTML.

## Entrada de datos

Ruta por defecto del Excel: `data/programaciones-armas.xlsx`.

Columnas clave:

- `estado`
- `sede`
- `fecha`
- `fecha_programacion` opcional; si existe se usa para filtrar ejecucion del dia
- `hora_rango`
- `tipo_operacion`
- `nro_solicitud`
- `doc_vigilante` o `dni`
- `tipo_arma`
- `arma`
- `ruc`
- `prioridad`
- `observaciones` u `observacion`

Solo se procesan registros cuyo `estado` contiene `PENDIENTE`. Si `VALIDAR_FECHA_PROGRAMACION_HOY=1`, solo se procesan registros cuya fecha de programacion coincide con el dia de ejecucion.

## Orden de procesamiento

El orden se construye en `excel.py`:

1. Filtrar pendientes.
2. Filtrar por fecha de programacion del dia si aplica.
3. Agrupar por RUC operativo:
   - `SELVA`: si el RUC/texto contiene `SELVA` o `20493762789`.
   - `JV`: si contiene `J&V`, `J V`, `RESGUARDO` o `20100901481`.
   - `OTRO`: cualquier otro valor.
4. Ordenar por grupo:
   - `SELVA`
   - `JV`
   - `OTRO`
5. Ordenar por prioridad:
   - `ALTA` primero.
   - Todo otro valor se trata como normal para orden.
6. Desempatar por indice original del Excel, de arriba hacia abajo.

Si la columna `prioridad` no existe, se crea como `Normal`.

## Deduplicacion y agrupacion de armas

El bot evita duplicar trabajo usando una clave compuesta por:

- documento vigilante
- Nro. Solicitud
- fecha programada
- grupo RUC

Cuando detecta filas relacionadas del mismo caso, arma objetivos multiples de arma. Por ejemplo, un mismo vigilante/solicitud puede llevar `CORTA/REVOLVER` y `LARGA/ESCOPETA`; el flujo las carga en la misma cita cuando corresponde.

## Flujo funcional por registro

1. Asegura sesion y contexto operativo de SEL.
2. Navega a `CITAS -> RESERVAS DE CITAS`.
3. Selecciona `EXAMEN PARA POLIGONO DE TIRO`.
4. Paso 1:
   - Selecciona sede.
   - Selecciona fecha.
   - Busca `hora_rango`.
   - Toma evidencia de tabla inicial.
   - Selecciona hora con cupo.
5. Paso 2:
   - Selecciona tipo de operacion.
   - En flujo inicial, selecciona `SEGURIDAD PRIVADA` antes del documento.
   - Selecciona documento vigilante.
   - Selecciona `Presentara tramite por Ventanilla Virtual = SI`.
   - Busca y selecciona `Nro. Solicitud` por token numerico.
   - Completa tabla de tipos de arma.
6. Paso 3:
   - Espera panel de resumen.
   - Resuelve captcha final por OCR o manual segun modo.
   - Marca terminos y condiciones.
   - Genera cita con reintento rapido ante captcha invalido.
7. Paso 4:
   - Captura confirmacion.
   - Registra correo de confirmacion.
   - Actualiza Excel con `estado = Cita Programada`.
8. Limpia formulario para continuar con el siguiente registro.

## Seleccion adaptativa de horario

La regla base es respetar primero `hora_rango` del Excel.

Si la hora exacta no tiene cupo, y `ADAPTIVE_HOUR_SELECTION=1`, el bot puede replanificar:

- Prueba vecinos inmediatos inferior/superior.
- Si `ADAPTIVE_HOUR_NOON_FULL_BLOCK=1`, puede evaluar el bloque de mediodia segun la estrategia del paso 1.
- Guarda horas descartadas en `_horas_descartadas`.
- Si al generar la cita SEL indica que el cupo fue ocupado, reintenta con otro horario hasta `MAX_HOUR_FALLBACK_RETRIES`.

Si no encuentra cupo tras la estrategia configurada, registra `SIN_CUPO`.

## Modos de ejecucion

### Manual

Comando tipico:

```powershell
python run_pipeline.py --mode manual --hold-browser-open
```

En manual, los correos se pueden enviar inmediatamente por caso.

### Scheduled

Comando tipico:

```powershell
python run_pipeline.py --mode scheduled
```

En scheduled, si `SCHEDULED_MULTIWORKER=1`, el orquestador padre divide trabajos entre workers. Cada worker usa un Excel temporal filtrado y escribe eventos de correo en manifiestos JSONL. Al finalizar, el proceso padre consolida y envia correos por tipo de resultado.

Variables importantes:

- `SCHEDULED_MULTIWORKER`
- `SCHEDULED_WORKERS`, maximo 4
- `SCHEDULED_WORKER_MODE`, `sticky` o `dynamic`
- `SCHEDULED_MAX_UNITS`

## Estados y resultados de negocio

### OK / Cita Programada

Se considera OK cuando:

- El flujo llega al paso final y captura confirmacion.
- O una validacion intermedia detecta que SEL ya muestra `REGISTRO DE CITA` / `RESUMEN DE CITA` con DNI y token esperados.

Acciones:

- Actualiza Excel: `estado = Cita Programada`.
- Registra screenshot de confirmacion.
- Envia correo `CONFIRMACION`.

### SIN_CUPO

Se considera `SIN_CUPO` cuando:

- La hora objetivo existe pero no tiene cupos.
- La estrategia adaptativa no encuentra alternativa valida.
- SEL indica cupos ocupados en post-validacion y se agotan los reintentos.

Acciones:

- Actualiza observaciones.
- Registra evidencia de tabla/candidatos.
- Envia correo `SIN_CUPO`.

### NRO_SOLICITUD

Se considera terminal cuando:

- No hay opciones en el combo de `Nro Solicitud`.
- No se encuentra el token numerico de `nro_solicitud` dentro de las opciones.
- El combo no confirma la seleccion esperada.

Regla de confirmacion:

- No se dispara por el primer intento; espera `NRO_SOLICITUD_CONFIRM_ATTEMPTS`, por defecto 2 en scheduled.

Acciones:

- Actualiza observaciones.
- Adjunta la ultima evidencia del paso 2.
- Envia correo consolidado de validaciones.

### RESTRICCION_48H_EXAMEN

Se considera terminal cuando SEL muestra la alerta:

```text
No esta permitido reservar una cita con fecha anterior a las 48 horas de rendido el examen
```

Esta causal se detecta en growls visibles, buffer de growl y texto del DOM. Se maneja como validacion terminal propia, no como `NRO_SOLICITUD`.

Acciones:

- Actualiza observaciones con restriccion de 48 horas.
- Captura pantalla del paso 2.
- Envia correo consolidado de validaciones con motivo `Restriccion 48h por examen`.
- Requiere una sola confirmacion terminal.

### Cita ya registrada / validacion intermedia

Se considera cita programada si, en medio de un intento o despues de una replanificacion de horario, aparece un modal o resumen con:

- `REGISTRO DE CITA`
- `RESUMEN DE CITA`
- DNI esperado
- token numerico de solicitud esperado

Esta regla evita falsos errores cuando SEL ya dejo una cita registrada pero el bot cae por una validacion intermedia del combo o del paso 2.

Acciones:

- Captura la pantalla visible como evidencia de confirmacion.
- Registra correo `CONFIRMACION`.
- Actualiza Excel como `Cita Programada`.
- Limpia el formulario y continua.

### TURNO_DUPLICADO

Se considera terminal cuando SEL indica que ya existe un turno registrado para la misma persona y tipo de licencia. Se detecta por growl/DOM.

Acciones:

- Actualiza observaciones.
- Cuenta como error terminal.

### DOC_VIGILANTE

Se considera terminal cuando el documento vigilante no se puede confirmar para el RUC/razon social.

Acciones:

- Actualiza observaciones.
- Cuenta como error terminal.

### FECHA_NO_DISPONIBLE

Se considera terminal cuando la fecha objetivo no aparece en el combo de fechas.

Acciones:

- Actualiza observaciones.
- Cuenta como error terminal.

### HORA_NO_DISPONIBLE

Se considera terminal cuando la hora objetivo no figura en la tabla de cupos y la estrategia no consigue alternativa.

Acciones:

- Actualiza observaciones.
- Cuenta como error terminal.

## Correos Microsoft Graph

El envio se controla con:

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

Tipos de correo:

- `CONFIRMACION`: citas generadas o detectadas como ya registradas.
- `SIN_CUPO`: casos terminales sin cupo.
- Validaciones de cita: antes era principalmente `NRO_SOLICITUD`; ahora el correo soporta multiples motivos, incluyendo `No se encontro Nro. Solicitud` y `Restriccion 48h por examen`.

En scheduled multihilo:

- Los workers no envian directamente.
- Escriben manifiestos:
  - `graph_confirmation_worker_N.jsonl`
  - `graph_step1_worker_N.jsonl`
  - `graph_nro_solicitud_worker_N.jsonl`
- El proceso padre consolida y envia al final.

## Evidencias

Cada corrida crea carpeta en `screenshots/aaaammdd_hhmmss/`.

Evidencias principales:

- `step_1_reserva_cupos`: tabla inicial y sin cupo.
- `step_2_datos_tramite`: errores de documento, Nro. Solicitud y restriccion 48h.
- `step_3_validacion_final`: errores de validacion/captcha.
- `step_4_confirmacion`: confirmacion final o cita ya registrada detectada.

Las capturas se nombran con fecha/hora, motivo, indice Excel y hora seleccionada.

## Logging

Cada corrida crea carpeta en `logs/aaaammdd_hhmmss/`.

Archivos principales:

- `run_aaaammdd_hhmmss.log`
- `task_scheduler_stdout.log`
- `logs_wN/run_aaaammdd_hhmmss.log` en multihilo
- Excels temporales por worker
- Manifiestos JSONL de correos

Los logs y screenshots conservan un maximo configurado por limpieza interna del proyecto.

## Reglas recientes agregadas

### Validacion intermedia de cita registrada

Motivo: evitar que un caso se envie como error cuando, tras reintentos o cambio adaptativo de horario, SEL ya muestra una cita registrada.

Implementacion:

- `CitaYaRegistradaError` en `exceptions.py`.
- `detectar_y_capturar_cita_ya_registrada_visible` en paso 2.
- Hook en `group_runner.py` antes de clasificar errores terminales.

Resultado:

- Si el modal tiene DNI y token esperado, se trata como OK.
- Se adjunta como confirmacion.

### Restriccion 48h por examen

Motivo: la alerta de SUCAMEC es una causal terminal clara y debe notificarse.

Implementacion:

- `detectar_y_capturar_restriccion_48h_examen_visible` en paso 2.
- Categoria terminal `RESTRICCION_48H_EXAMEN` en `runtime.py`.
- Hook en `group_runner.py` antes de clasificar errores.
- Builder de correo de validaciones ahora incluye columna `Motivo`.

Resultado:

- Se captura evidencia.
- Se actualiza observacion.
- Se envia correo consolidado de validaciones con motivo explicito.

## Consideraciones operativas

- Los errores generales no siempre generan correo. Solo generan correo si caen en categorias con notificacion implementada.
- `FECHA_NO_DISPONIBLE`, `HORA_NO_DISPONIBLE`, `DOC_VIGILANTE` y `TURNO_DUPLICADO` actualizan observaciones, pero no tienen correo propio salvo que se extienda el builder de validaciones.
- La validacion de cita ya registrada debe ejecutarse antes de declarar `NRO_SOLICITUD`, porque SEL puede mostrar un resumen exitoso aunque el combo no refleje el token esperado.
- La restriccion de 48h debe detectarse mientras el growl aun esta visible o desde el buffer instalado por el monitor.
- En multihilo, revisar siempre el log principal y los logs `logs_wN`, porque el evento puede generarse en un worker y el envio consolidado aparece al final en el proceso padre.

