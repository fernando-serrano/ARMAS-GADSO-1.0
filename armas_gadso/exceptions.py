from __future__ import annotations


class SinCupoError(Exception):
    """Se lanza cuando la hora objetivo existe pero no tiene cupos libres."""


class FechaNoDisponibleError(Exception):
    """Se lanza cuando la fecha objetivo no aparece en el combo de fechas."""


class TurnoDuplicadoError(Exception):
    """Se lanza cuando SEL informa turno ya registrado para la persona/tipo de licencia."""


class CitaYaRegistradaError(Exception):
    """Se lanza cuando SEL muestra una cita ya registrada para el registro actual."""


class CuposOcupadosPostValidacionError(Exception):
    """Se lanza cuando SEL indica que el horario ya se ocupo al generar la cita final."""


class GrowlErrorSucamec(Exception):
    """Se lanza cuando SUCAMEC muestra un growl de error no catalogado.
    Decision operativa: abortar el registro usando el texto del growl como observacion."""
