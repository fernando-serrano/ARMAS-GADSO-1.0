from __future__ import annotations


class SinCupoError(Exception):
    """Se lanza cuando la hora objetivo existe pero no tiene cupos libres."""


class FechaNoDisponibleError(Exception):
    """Se lanza cuando la fecha objetivo no aparece en el combo de fechas."""


class TurnoDuplicadoError(Exception):
    """Se lanza cuando SEL informa turno ya registrado para la persona/tipo de licencia."""


class CuposOcupadosPostValidacionError(Exception):
    """Se lanza cuando SEL indica que el horario ya se ocupo al generar la cita final."""
