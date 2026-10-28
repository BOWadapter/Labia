"""R2 — Docstrings en español: presencia mecánica; el idioma sólo se señala para revisión."""

from __future__ import annotations

import re

from ..modelo import Caso, Fuente, Regla, Resultado

NOMBRE = "Docstrings (presencia)"
_PALABRA = re.compile(r"[a-záéíóúñü]+")
_ES = frozenset("el la los las de del que y en un una para por con se es al lo su como más devuelve".split())
_EN = frozenset("the of and to in is for that this with on returns return if it be as an by".split())


def ingles_probable(texto: str) -> bool:
    """Heurística: más palabras vacías inglesas que españolas. No decide; señala."""
    palabras = _PALABRA.findall(texto.lower())
    return sum(p in _EN for p in palabras) > sum(p in _ES for p in palabras)


def evaluar(fuente: Fuente) -> Resultado:
    """Tasa de funciones públicas fuera de tests sin docstring."""
    candidatas = [
        f for f in fuente.funciones
        if not f.es_test and not f.nombre.startswith("_") and f.docstring_evaluable
    ]
    sin_doc = [f for f in candidatas if f.docstring is None]
    en_ingles = [f for f in candidatas if f.docstring is not None and ingles_probable(f.docstring)]
    return Resultado(
        regla="R2",
        nombre=NOMBRE,
        verificable=True,
        oportunidades=len(candidatas),
        violaciones=len(sin_doc),
        detalle=tuple(f"{f.archivo}:{f.linea} {f.nombre}" for f in sin_doc[:25]),
        nota=f"Funciones públicas fuera de tests. Idioma a revisión humana: "
        f"{len(en_ingles)} docstring(s) con inglés probable (no cuentan como violación).",
    )


REGLA = Regla(
    id="R2",
    nombre=NOMBRE,
    evaluar=evaluar,
    casos=(
        Caso("con docstring", {"app/x.py": 'def f() -> None:\n    """Hace algo."""\n'}, False),
        Caso("sin docstring", {"app/x.py": "def f() -> None:\n    return None\n"}, True),
        Caso("privada exenta", {"app/x.py": "def _f() -> None:\n    return None\n"}, False),
    ),
)
