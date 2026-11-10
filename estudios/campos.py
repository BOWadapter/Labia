"""Lectura de campos de TOML con el tipo esperado o un valor por omisión.

Los errores de forma los reporta ``estudios.manifiestos``; quien lee con estas funciones
no tiene que repetir esas comprobaciones ni puede romperse con un tipo inesperado.
"""

from __future__ import annotations


def como_texto(valor: object) -> str:
    """El valor si es texto; si no, cadena vacía."""
    return valor if isinstance(valor, str) else ""


def como_lista(valor: object) -> list[str]:
    """Los elementos de texto de una lista; lista vacía si el valor no es una lista."""
    return [v for v in valor if isinstance(v, str)] if isinstance(valor, list) else []


def como_tabla(valor: object) -> dict[str, object]:
    """El valor si es una tabla; si no, tabla vacía."""
    return {str(clave): contenido for clave, contenido in valor.items()} if isinstance(valor, dict) else {}


def como_entero(valor: object, omision: int) -> int:
    """El valor si es un entero (no booleano); si no, el valor por omisión."""
    return valor if isinstance(valor, int) and not isinstance(valor, bool) else omision


def como_real(valor: object, omision: float) -> float:
    """El valor como real si es un número (no booleano); si no, el valor por omisión."""
    return float(valor) if isinstance(valor, (int, float)) and not isinstance(valor, bool) else omision
