"""R4 — Escrituras idempotentes con clave explícita. No decidible por máquina: lista sitios."""

from __future__ import annotations

import ast

from ..fuentes import es_ruta_test
from ..modelo import Caso, Fuente, Regla, Resultado

NOMBRE = "Escrituras idempotentes (revisión humana)"
_METODOS_ESCRITURA = frozenset(
    {"write", "write_text", "write_bytes", "executemany", "insert", "insert_one",
     "insert_many", "update_one", "update_many", "put_item", "upsert", "save"}
)
_SQL_ESCRITURA = ("insert", "update", "delete", "replace", "upsert", "merge")


def _es_escritura(nodo: ast.Call) -> bool:
    """Heurística de sitio de escritura: métodos típicos, open() en modo w/a/x, SQL DML."""
    funcion = nodo.func
    if isinstance(funcion, ast.Attribute) and funcion.attr in _METODOS_ESCRITURA:
        return True
    if isinstance(funcion, ast.Name) and funcion.id == "open":
        modos = [a for a in nodo.args[1:2]] + [k.value for k in nodo.keywords if k.arg == "mode"]
        return any(
            isinstance(m, ast.Constant) and isinstance(m.value, str) and set(m.value) & {"w", "a", "x"}
            for m in modos
        )
    if isinstance(funcion, ast.Attribute) and funcion.attr == "execute" and nodo.args:
        primero = nodo.args[0]
        return (
            isinstance(primero, ast.Constant)
            and isinstance(primero.value, str)
            and primero.value.lstrip().lower().startswith(_SQL_ESCRITURA)
        )
    return False


def evaluar(fuente: Fuente) -> Resultado:
    """Cuenta sitios de escritura para revisión humana; la tasa no se calcula."""
    if fuente.modo != "directorio":
        return Resultado("R4", NOMBRE, False, 0, 0, nota="Requiere el árbol completo.")
    sitios: list[str] = []
    for ruta, texto in sorted(fuente.textos.items()):
        if not ruta.endswith(".py") or es_ruta_test(ruta):
            continue
        try:
            arbol = ast.parse(texto)
        except SyntaxError:
            continue
        sitios.extend(
            f"{ruta}:{n.lineno}" for n in ast.walk(arbol) if isinstance(n, ast.Call) and _es_escritura(n)
        )
    return Resultado(
        regla="R4",
        nombre=NOMBRE,
        verificable=False,
        oportunidades=len(sitios),
        violaciones=0,
        detalle=tuple(sitios[:50]),
        nota="Regla no decidible mecánicamente; oportunidades = sitios a revisar.",
    )


REGLA = Regla(
    id="R4",
    nombre=NOMBRE,
    evaluar=evaluar,
    mecanica=False,
    casos=(
        Caso("sin escrituras", {"app/x.py": "def f(a: int) -> int:\n    return a\n"}, False),
        Caso("insert SQL", {"app/x.py": 'def f(c: object) -> None:\n    c.execute("INSERT INTO t VALUES (1)")\n'}, True),
    ),
)
