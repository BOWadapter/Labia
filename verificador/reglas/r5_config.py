"""R5 — Nada hardcodeado: la configuración entra por entorno."""

from __future__ import annotations

import ast
import re

from ..fuentes import es_ruta_test
from ..modelo import Caso, Fuente, Regla, Resultado

NOMBRE = "Configuración por entorno"
_URL = re.compile(r"^[a-z][a-z0-9+.-]*://", re.I)
_HOST = re.compile(r"^(localhost|\d{1,3}(\.\d{1,3}){3})(:\d+)?$")
_NOMBRE_SECRETO = re.compile(r"(password|passwd|secret|token|api_?key)", re.I)
_NOMBRE_PUERTO = re.compile(r"port", re.I)


def _es_lectura_entorno(nodo: ast.AST) -> bool:
    """os.getenv(...), os.environ.get(...), os.environ[...] y variantes importadas."""
    if isinstance(nodo, ast.Call):
        funcion = nodo.func
        if isinstance(funcion, ast.Name) and funcion.id == "getenv":
            return True
        if isinstance(funcion, ast.Attribute):
            if funcion.attr == "getenv":
                return True
            if funcion.attr == "get" and _es_environ(funcion.value):
                return True
    if isinstance(nodo, ast.Subscript) and _es_environ(nodo.value):
        return True
    return False


def _es_environ(nodo: ast.expr) -> bool:
    """True para ``environ`` u ``os.environ``."""
    return (isinstance(nodo, ast.Name) and nodo.id == "environ") or (
        isinstance(nodo, ast.Attribute) and nodo.attr == "environ"
    )


def _nombres_destino(nodo: ast.Assign | ast.AnnAssign) -> list[str]:
    """Nombres a los que se asigna (variables o atributos)."""
    destinos = nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target]
    nombres: list[str] = []
    for d in destinos:
        if isinstance(d, ast.Name):
            nombres.append(d.id)
        elif isinstance(d, ast.Attribute):
            nombres.append(d.attr)
    return nombres


def _analizar(texto: str) -> tuple[list[int], int]:
    """Devuelve (líneas con literales de configuración, número de lecturas de entorno)."""
    arbol = ast.parse(texto)
    excluidos: set[int] = set()
    for nodo in ast.walk(arbol):
        cuerpo = getattr(nodo, "body", None)
        if isinstance(cuerpo, list) and cuerpo and isinstance(cuerpo[0], ast.Expr):
            excluidos.add(id(cuerpo[0].value))
        if _es_lectura_entorno(nodo) and isinstance(nodo, ast.Call):
            excluidos.update(id(a) for a in ast.walk(nodo))
    lecturas = sum(1 for n in ast.walk(arbol) if _es_lectura_entorno(n))
    lineas: list[int] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) and id(nodo) not in excluidos:
            if _URL.match(nodo.value) or _HOST.match(nodo.value):
                lineas.append(nodo.lineno)
        if isinstance(nodo, (ast.Assign, ast.AnnAssign)) and isinstance(nodo.value, ast.Constant):
            valor = nodo.value.value
            for nombre in _nombres_destino(nodo):
                if _NOMBRE_SECRETO.search(nombre) and isinstance(valor, str) and valor:
                    lineas.append(nodo.lineno)
                elif _NOMBRE_PUERTO.search(nombre) and isinstance(valor, int) and 0 < valor < 65536:
                    lineas.append(nodo.lineno)
    return sorted(set(lineas)), lecturas


def evaluar(fuente: Fuente) -> Resultado:
    """Tasa = literales de configuración / (literales + lecturas de entorno)."""
    if fuente.modo != "directorio":
        return Resultado("R5", NOMBRE, False, 0, 0, nota="Requiere el árbol completo.")
    malas: list[str] = []
    lecturas = 0
    for ruta, texto in sorted(fuente.textos.items()):
        if not ruta.endswith(".py") or es_ruta_test(ruta):
            continue
        try:
            lineas, n = _analizar(texto)
        except SyntaxError:
            continue
        lecturas += n
        malas.extend(f"{ruta}:{linea}" for linea in lineas)
    return Resultado(
        regla="R5",
        nombre=NOMBRE,
        verificable=True,
        oportunidades=len(malas) + lecturas,
        violaciones=len(malas),
        detalle=tuple(malas[:25]),
        nota="URLs, hosts, puertos y credenciales literales fuera de tests y docstrings; "
        "los valores por defecto dentro de getenv/environ.get no cuentan.",
    )


REGLA = Regla(
    id="R5",
    nombre=NOMBRE,
    evaluar=evaluar,
    casos=(
        Caso("por entorno con default", {"app/cfg.py": 'import os\nURL = os.getenv("URL", "http://localhost:8000")\n'}, False),
        Caso("URL literal", {"app/cfg.py": 'import os\nX = os.getenv("X")\nURL = "http://10.0.0.5:8000"\n'}, True),
        Caso("credencial literal", {"app/cfg.py": 'API_KEY = "abc123"\n'}, True),
    ),
)
