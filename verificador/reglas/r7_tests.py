"""R7 — Tests junto al código."""

from __future__ import annotations

from pathlib import PurePosixPath

from ..fuentes import es_ruta_test
from ..modelo import Caso, Fuente, Regla, Resultado

NOMBRE = "Tests junto al código"
_EXENTOS = frozenset({"__init__.py", "__main__.py", "conftest.py", "setup.py"})


def _evaluar_directorio(fuente: Fuente) -> Resultado:
    """Cada módulo fuera de tests necesita test_<módulo>.py en su carpeta o en un tests/ cercano."""
    rutas = set(fuente.rutas)
    modulos = [
        PurePosixPath(r) for r in fuente.rutas
        if r.endswith(".py") and not es_ruta_test(r) and PurePosixPath(r).name not in _EXENTOS
    ]
    sin_test: list[str] = []
    for modulo in modulos:
        nombre = f"test_{modulo.stem}.py"
        candidatos = {
            (modulo.parent / nombre).as_posix(),
            (modulo.parent / "tests" / nombre).as_posix(),
            (PurePosixPath("tests") / nombre).as_posix(),
        }
        candidatos |= {(p / "tests" / nombre).as_posix() for p in modulo.parents}
        if not candidatos & rutas:
            sin_test.append(modulo.as_posix())
    return Resultado(
        regla="R7",
        nombre=NOMBRE,
        verificable=True,
        oportunidades=len(modulos),
        violaciones=len(sin_test),
        detalle=tuple(sin_test[:25]),
        nota="Oportunidad = módulo fuera de tests. Cobertura es señal, no objetivo.",
    )


def _evaluar_diff(fuente: Fuente) -> Resultado:
    """En un diff: si toca código .py fuera de tests, debe tocar también algún test."""
    fuente_py = [r for r in fuente.rutas if r.endswith(".py") and not es_ruta_test(r)]
    toca_tests = any(es_ruta_test(r) for r in fuente.rutas)
    viola = bool(fuente_py) and not toca_tests
    return Resultado(
        regla="R7",
        nombre=NOMBRE,
        verificable=True,
        oportunidades=1 if fuente_py else 0,
        violaciones=1 if viola else 0,
        detalle=tuple(fuente_py[:10]) if viola else (),
        nota="Oportunidad = diff que toca .py fuera de tests.",
    )


def evaluar(fuente: Fuente) -> Resultado:
    """Despacha según el modo de la fuente."""
    return _evaluar_diff(fuente) if fuente.modo == "diff" else _evaluar_directorio(fuente)


REGLA = Regla(
    id="R7",
    nombre=NOMBRE,
    evaluar=evaluar,
    casos=(
        Caso("test adyacente", {"app/calc.py": "x = 1\n", "app/test_calc.py": "y = 2\n"}, False),
        Caso("test en tests/", {"app/calc.py": "x = 1\n", "tests/test_calc.py": "y = 2\n"}, False),
        Caso("sin test", {"app/calc.py": "x = 1\n"}, True),
    ),
)
