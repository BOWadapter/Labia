"""Verificador de conformidad por regla: tasa de violación sobre oportunidades, nunca agregada.

Uso:
    python -m verificador reglas [--reglas-proyecto DIR]
    python -m verificador casos  [--reglas-proyecto DIR]
    python -m verificador directorio RUTA [--stdout ARCHIVO] [--git REPO] [--tipo T] [--reglas-proyecto DIR]
    python -m verificador diff ARCHIVO
"""

from __future__ import annotations

import math
from pathlib import Path

from .fuentes import fuente_diff, fuente_directorio, fuente_memoria
from .modelo import Caso, Fuente, Funcion, Regla, Resultado
from .reglas import cargar

__all__ = [
    "Caso", "Fuente", "Funcion", "Regla", "Resultado", "cargar", "comprobar_casos",
    "fuente_diff", "fuente_directorio", "fuente_memoria", "verificar", "wilson",
]
__version__ = "0.1.0"


def verificar(
    fuente: Fuente,
    ids: set[str] | None = None,
    tipo: str = "python",
    extra: Path | None = None,
) -> list[Resultado]:
    """Evalúa las reglas del tipo dado (más las del proyecto) sobre la fuente."""
    return [r.evaluar(fuente) for r in cargar(tipo, extra) if ids is None or r.id in ids]


def comprobar_casos(regla: Regla) -> list[str]:
    """Compuerta de contribución: errores si la regla no discrimina sus propios casos."""
    errores: list[str] = []
    if not any(c.viola for c in regla.casos):
        errores.append(f"{regla.id}: falta un caso que viole")
    if not any(not c.viola for c in regla.casos):
        errores.append(f"{regla.id}: falta un caso que cumpla")
    for caso in regla.casos:
        fuente = (
            fuente_diff(caso.diff) if caso.diff is not None
            else fuente_memoria(caso.archivos, caso.stdout, caso.commits)
        )
        resultado = regla.evaluar(fuente)
        medida = resultado.violaciones if regla.mecanica else resultado.oportunidades
        if regla.mecanica and not resultado.verificable:
            errores.append(f"{regla.id}: '{caso.descripcion}' no fue verificable")
        elif caso.viola and medida == 0:
            errores.append(f"{regla.id}: no detecta '{caso.descripcion}'")
        elif not caso.viola and medida > 0:
            errores.append(f"{regla.id}: falso positivo en '{caso.descripcion}'")
    return errores


def wilson(violaciones: int, oportunidades: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalo de Wilson al 95% para una tasa. Con n chico, el intervalo es la noticia."""
    if oportunidades == 0:
        return (0.0, 1.0)
    p = violaciones / oportunidades
    n = oportunidades
    centro = (p + z * z / (2 * n)) / (1 + z * z / n)
    margen = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centro - margen), min(1.0, centro + margen))
