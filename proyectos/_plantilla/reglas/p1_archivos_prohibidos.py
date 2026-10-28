"""P1 — Archivos que el proyecto prohíbe (plantilla de regla propia de proyecto).

Ejemplo real: en Whole Platport (Next 16) un asistente generó ``middleware.ts`` cuando
el proyecto usa ``proxy.ts``. Copia este archivo a ``.labia/reglas/`` del proyecto,
ajusta ``PROHIBIDOS`` y los casos, y comprueba con:

    python -m verificador casos --reglas-proyecto .labia/reglas --tipo typescript
"""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import PurePosixPath

from verificador import Caso, Fuente, Regla, Resultado

NOMBRE = "Archivos prohibidos por el proyecto"
PROHIBIDOS: tuple[str, ...] = ("middleware.ts", "middleware.js")


def evaluar(fuente: Fuente) -> Resultado:
    """Una oportunidad por patrón prohibido; violación si algún archivo lo cumple."""
    encontrados = [
        ruta for ruta in fuente.rutas
        if any(fnmatch(PurePosixPath(ruta).name, patron) for patron in PROHIBIDOS)
    ]
    patrones_violados = {p for p in PROHIBIDOS if any(fnmatch(PurePosixPath(r).name, p) for r in encontrados)}
    return Resultado(
        regla="P1",
        nombre=NOMBRE,
        verificable=True,
        oportunidades=len(PROHIBIDOS),
        violaciones=len(patrones_violados),
        detalle=tuple(encontrados[:25]),
        nota="Patrones: " + ", ".join(PROHIBIDOS),
    )


REGLA = Regla(
    id="P1",
    nombre=NOMBRE,
    evaluar=evaluar,
    tipo="typescript",
    casos=(
        Caso("usa proxy.ts", {"proxy.ts": "export {}\n"}, False),
        Caso("generó middleware.ts", {"middleware.ts": "export {}\n"}, True),
    ),
)
