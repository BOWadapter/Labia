"""R3 — Logs JSON con request_id, timestamp ISO y duration_ms; nunca secretos."""

from __future__ import annotations

import json
import re
from datetime import datetime

from ..modelo import Caso, Fuente, Regla, Resultado

NOMBRE = "Logs JSON estructurados"
_CLAVE_SECRETA = re.compile(r"(password|passwd|secret|token|api[_-]?key|authorization)", re.I)
_VALOR_SECRETO = re.compile(r"(sk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,})")


def _problema(linea: str) -> str | None:
    """Describe por qué una línea de log viola la regla, o None si cumple."""
    try:
        registro = json.loads(linea)
    except json.JSONDecodeError:
        return "no es JSON"
    if not isinstance(registro, dict):
        return "no es un objeto JSON"
    if not isinstance(registro.get("request_id"), str) or not registro["request_id"]:
        return "falta request_id"
    marca = registro.get("timestamp")
    try:
        datetime.fromisoformat(str(marca).replace("Z", "+00:00"))
    except ValueError:
        return "timestamp no ISO 8601"
    duracion = registro.get("duration_ms")
    if isinstance(duracion, bool) or not isinstance(duracion, (int, float)):
        return "falta duration_ms numérico"
    for clave, valor in registro.items():
        if _CLAVE_SECRETA.search(str(clave)) and valor not in (None, "", "***"):
            return f"posible secreto en '{clave}'"
    if _VALOR_SECRETO.search(linea):
        return "valor con forma de credencial"
    return None


def evaluar(fuente: Fuente) -> Resultado:
    """Tasa de líneas de stdout del comando de demostración que no cumplen el formato."""
    if fuente.stdout is None:
        return Resultado("R3", NOMBRE, False, 0, 0,
                         nota="Requiere --stdout con la salida del comando de demostración.")
    lineas = [linea.strip() for linea in fuente.stdout.splitlines() if linea.strip()]
    malas = [(n, p) for n, linea in enumerate(lineas, 1) if (p := _problema(linea)) is not None]
    return Resultado(
        regla="R3",
        nombre=NOMBRE,
        verificable=True,
        oportunidades=len(lineas),
        violaciones=len(malas),
        detalle=tuple(f"línea {n}: {p}" for n, p in malas[:25]),
        nota="Cada línea no vacía de stdout es una oportunidad.",
    )


_BUENA = '{"request_id": "a1", "timestamp": "2026-10-28T10:00:00Z", "duration_ms": 3.2}'
REGLA = Regla(
    tipo="cualquiera",
    id="R3",
    nombre=NOMBRE,
    evaluar=evaluar,
    casos=(
        Caso("log completo", {}, False, stdout=_BUENA + "\n"),
        Caso("texto plano", {}, True, stdout="procesado ok\n"),
        Caso("secreto en log", {}, True, stdout=_BUENA[:-1] + ', "api_key": "abc123"}\n'),
    ),
)
