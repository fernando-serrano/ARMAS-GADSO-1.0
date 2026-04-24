"""Selectores de la pantalla de login SEL."""

LOGIN_SELECTORS = {
    "tab_tradicional": '#tabViewLogin a[href^="#tabViewLogin:j_idt"]:has-text("Autenticación Tradicional"), #tabViewLogin a:has-text("Autenticación Tradicional"), #tabViewLogin a:has-text("Autenticacion Tradicional")',
    "tipo_doc_select": "#tabViewLogin\\:tradicionalForm\\:tipoDoc_input",
    "numero_documento": "#tabViewLogin\\:tradicionalForm\\:documento",
    "usuario": "#tabViewLogin\\:tradicionalForm\\:usuario",
    "clave": "#tabViewLogin\\:tradicionalForm\\:clave",
    "captcha_img": "#tabViewLogin\\:tradicionalForm\\:imgCaptcha",
    "captcha_input": "#tabViewLogin\\:tradicionalForm\\:textoCaptcha",
    "boton_refresh": "#tabViewLogin\\:tradicionalForm\\:botonCaptcha",
    "ingresar": "#tabViewLogin\\:tradicionalForm\\:ingresar",
}
