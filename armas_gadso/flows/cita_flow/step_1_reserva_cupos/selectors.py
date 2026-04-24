"""Selectores del Paso 1: sede, fecha, tabla de cupos y acciones."""

SELECTORS = {
    "reserva_form": '#tabGestion\\:creaCitaPolJurForm',
    "sede_trigger": '#tabGestion\\:creaCitaPolJurForm\\:sedeId .ui-selectonemenu-trigger',
    "sede_panel": '#tabGestion\\:creaCitaPolJurForm\\:sedeId_panel',
    "sede_label": '#tabGestion\\:creaCitaPolJurForm\\:sedeId_label',
    "fecha_trigger": '#tabGestion\\:creaCitaPolJurForm\\:listaDiasId .ui-selectonemenu-trigger',
    "fecha_panel": '#tabGestion\\:creaCitaPolJurForm\\:listaDiasId_panel',
    "fecha_label": '#tabGestion\\:creaCitaPolJurForm\\:listaDiasId_label',
    "tabla_programacion": '#tabGestion\\:creaCitaPolJurForm\\:dtProgramacion',
    "tabla_programacion_rows": '#tabGestion\\:creaCitaPolJurForm\\:dtProgramacion_data tr',
    "boton_siguiente": '#tabGestion\\:creaCitaPolJurForm button:has-text("Siguiente")',
    "boton_limpiar": '#tabGestion\\:creaCitaPolJurForm\\:botonLimpiar',
}
