"""R1 — Type hints en todo (aproximación por AST de ``mypy --strict``)."""

from __future__ import annotations

from ..modelo import Caso, Fuente, Regla, Resultado

NOMBRE = "Type hints en todo"


def evaluar(fuente: Fuente) -> Resultado:
    """Tasa de funciones fuera de tests con algún parámetro o retorno sin anotar."""
    candidatas = [f for f in fuente.funciones if not f.es_test and f.anotada is not None]
    malas = [f for f in candidatas if not f.anotada]
    return Resultado(
        regla="R1",
        nombre=NOMBRE,
        verificable=True,
        oportunidades=len(candidatas),
        violaciones=len(malas),
        detalle=tuple(f"{f.archivo}:{f.linea} {f.nombre}" for f in malas[:25]),
        nota="Funciones fuera de tests; self/cls exentos; __init__ con parámetros anotados "
        "puede omitir el retorno. mypy --strict sigue siendo la verificación completa.",
    )


REGLA = Regla(
    id="R1",
    nombre=NOMBRE,
    evaluar=evaluar,
    casos=(
        Caso("firma completa", {"app/calc.py": "def doble(a: int) -> int:\n    return a * 2\n"}, False),
        Caso("retorno sin anotar", {"app/calc.py": "def doble(a: int):\n    return a * 2\n"}, True),
        Caso("parámetro sin anotar", {"app/calc.py": "def doble(a) -> int:\n    return a * 2\n"}, True),
    ),
)
