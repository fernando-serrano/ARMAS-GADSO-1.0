"""Selectores del Paso 3: resumen, captcha, terminos y generar cita."""

SELECTORS = {
    "fase3_panel": '#tabGestion\\:creaCitaPolJurForm\\:panelPaso4',
    "fase3_captcha_img": '#tabGestion\\:creaCitaPolJurForm\\:imgCaptcha',
    "fase3_captcha_input": '#tabGestion\\:creaCitaPolJurForm\\:textoCaptcha',
    "fase3_boton_refresh": '#tabGestion\\:creaCitaPolJurForm\\:botonCaptcha',
    "fase3_terminos_box": '#tabGestion\\:creaCitaPolJurForm\\:terminos .ui-chkbox-box',
    "fase3_terminos_input": '#tabGestion\\:creaCitaPolJurForm\\:terminos_input',
    "fase3_boton_generar_cita": '#tabGestion\\:creaCitaPolJurForm button.ui-button:has-text("Generar Cita")',
    "panel_candidates": [
        '#tabGestion\\:creaCitaPolJurForm\\:panelPaso3_content',
        '#tabGestion\\:creaCitaPolJurForm\\:panelPaso4',
        '#tabGestion\\:tab3',
        '#tabGestion\\:creaCitaPolJurForm',
    ],
}
