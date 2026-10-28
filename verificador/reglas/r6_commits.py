"""R6 — Conventional Commits. El force push no se ve en el log: se impone en el remoto."""

from __future__ import annotations

import re

from ..modelo import Caso, Fuente, Regla, Resultado

NOMBRE = "Conventional Commits"
_TIPOS = "feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert"
_CC = re.compile(rf"^(?:{_TIPOS})(?:\([^()\r\n]+\))?!?: \S")


def evaluar(fuente: Fuente) -> Resultado:
    """Tasa de asuntos de commit (sin merges) que no siguen Conventional Commits 1.0."""
    if fuente.commits is None:
        return Resultado("R6", NOMBRE, False, 0, 0, nota="Requiere --git con la ruta del repositorio.")
    asuntos = [c for c in fuente.commits if not c.startswith("Merge ")]
    malos = [c for c in asuntos if not _CC.match(c)]
    return Resultado(
        regla="R6",
        nombre=NOMBRE,
        verificable=True,
        oportunidades=len(asuntos),
        violaciones=len(malos),
        detalle=tuple(malos[:25]),
        nota="Merges excluidos. 'Nunca force push a main/develop' se impone con protección "
        "de rama en el remoto, no se mide aquí.",
    )


REGLA = Regla(
    tipo="cualquiera",
    id="R6",
    nombre=NOMBRE,
    evaluar=evaluar,
    casos=(
        Caso("convencional", {}, False, commits=("feat(api): añade alta de dispositivos", "Merge pull request #3")),
        Caso("libre", {}, True, commits=("arreglos varios",)),
    ),
)
