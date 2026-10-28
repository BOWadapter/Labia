"""Construcción de fuentes: árbol de archivos en memoria o en disco, y diff unificado."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath

from .modelo import Fuente, Funcion

_DIRECTORIOS_IGNORADOS = frozenset(
    {".git", ".venv", "venv", "env", "__pycache__", "node_modules", "build", "dist",
     ".mypy_cache", ".pytest_cache", ".tox", ".eggs"}
)
_DEF = re.compile(r"^\s*(?:async\s+)?def\s+(?P<nombre>[A-Za-z_]\w*)\s*\(")
_INICIO_DOCSTRING = re.compile(r"""^[rRuU]?(?P<delim>"{3}|'{3}|"|')(?P<resto>.*)$""")
_HUNK = re.compile(
    r"^@@ -\d+(?:,(?P<n_viejo>\d+))? \+(?P<inicio_nuevo>\d+)(?:,(?P<n_nuevo>\d+))? @@"
)
_MAX_LINEAS_FIRMA = 40
_MAX_LINEAS_DOCSTRING = 20

FuncionAst = ast.FunctionDef | ast.AsyncFunctionDef


def es_ruta_test(ruta: str) -> bool:
    """Indica si una ruta corresponde a código de pruebas."""
    partes = PurePosixPath(ruta.replace("\\", "/")).parts
    if not partes:
        return False
    nombre = partes[-1]
    return (
        any(p in ("tests", "test") for p in partes[:-1])
        or nombre.startswith("test_")
        or nombre.endswith("_test.py")
        or nombre == "conftest.py"
    )


def anotada(nodo: FuncionAst) -> bool:
    """True si todos los parámetros (salvo self/cls inicial) y el retorno están anotados.

    Sigue a ``mypy --strict``: ``__init__`` puede omitir el retorno si tiene al menos
    un parámetro anotado.
    """
    args = nodo.args
    posicionales = [*args.posonlyargs, *args.args]
    if posicionales and posicionales[0].arg in ("self", "cls"):
        posicionales = posicionales[1:]
    parametros = [*posicionales, *args.kwonlyargs]
    faltan = [a for a in parametros if a.annotation is None]
    if args.vararg is not None and args.vararg.annotation is None:
        faltan.append(args.vararg)
    if args.kwarg is not None and args.kwarg.annotation is None:
        faltan.append(args.kwarg)
    if faltan:
        return False
    if nodo.returns is not None:
        return True
    return nodo.name == "__init__" and len(parametros) > 0


def _funciones_de_texto(ruta: str, texto: str) -> list[Funcion]:
    """Extrae funciones de un archivo completo mediante AST."""
    try:
        arbol = ast.parse(texto)
    except SyntaxError:
        return []
    test = es_ruta_test(ruta)
    return [
        Funcion(
            archivo=ruta,
            linea=nodo.lineno,
            nombre=nodo.name,
            es_test=test,
            anotada=anotada(nodo),
            docstring=ast.get_docstring(nodo),
            docstring_evaluable=True,
        )
        for nodo in ast.walk(arbol)
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def fuente_memoria(
    archivos: Mapping[str, str],
    stdout: str | None = None,
    commits: Iterable[str] | None = None,
    otras_rutas: Iterable[str] = (),
) -> Fuente:
    """Construye una fuente en modo directorio a partir de rutas y contenidos.

    ``otras_rutas`` registra archivos presentes cuyo contenido no se leyó (binarios,
    grandes); cuentan para reglas de existencia, no para reglas de contenido.
    """
    textos = {ruta.replace("\\", "/"): texto for ruta, texto in archivos.items()}
    funciones: list[Funcion] = []
    for ruta in sorted(textos):
        if ruta.endswith(".py"):
            funciones.extend(_funciones_de_texto(ruta, textos[ruta]))
    rutas = set(textos) | {r.replace("\\", "/") for r in otras_rutas}
    return Fuente(
        modo="directorio",
        textos=textos,
        rutas=tuple(sorted(rutas)),
        funciones=tuple(funciones),
        stdout=stdout,
        commits=tuple(commits) if commits is not None else None,
    )


_EXTENSIONES_TEXTO = frozenset(
    {".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".json", ".toml", ".yaml", ".yml",
     ".md", ".c", ".h", ".cpp", ".hpp", ".ino", ".sql", ".sh", ".ps1"}
)
_MAX_BYTES_TEXTO = 1_000_000


def fuente_directorio(
    raiz: Path,
    stdout: str | None = None,
    commits: Iterable[str] | None = None,
) -> Fuente:
    """Recorre ``raiz`` (sin entornos ni cachés): lee archivos de texto, registra el resto."""
    archivos: dict[str, str] = {}
    otras: list[str] = []
    for ruta in sorted(p for p in raiz.rglob("*") if p.is_file()):
        relativa = ruta.relative_to(raiz)
        if any(parte in _DIRECTORIOS_IGNORADOS for parte in relativa.parts[:-1]):
            continue
        if ruta.suffix.lower() in _EXTENSIONES_TEXTO and ruta.stat().st_size <= _MAX_BYTES_TEXTO:
            archivos[relativa.as_posix()] = ruta.read_text(encoding="utf-8", errors="replace")
        else:
            otras.append(relativa.as_posix())
    return fuente_memoria(archivos, stdout=stdout, commits=commits, otras_rutas=otras)


def _firma(lineas: list[str]) -> tuple[FuncionAst, bool] | None:
    """Interpreta líneas como una firma de función.

    Devuelve el nodo y si el cuerpo venía en las mismas líneas (función de una línea),
    o None si la firma sigue incompleta.
    """
    texto = "\n".join(linea.strip() for linea in lineas)
    for candidato, cuerpo_propio in ((texto, True), (texto + "\n    pass", False)):
        try:
            arbol = ast.parse(candidato)
        except SyntaxError:
            continue
        if arbol.body and isinstance(arbol.body[0], (ast.FunctionDef, ast.AsyncFunctionDef)):
            return arbol.body[0], cuerpo_propio
    return None


def _docstring_desde(bloque: list[tuple[int, str]], k: int) -> str | None:
    """Si la línea k abre un literal de cadena, devuelve su texto (aproximado)."""
    inicio = _INICIO_DOCSTRING.match(bloque[k][1].strip())
    if inicio is None:
        return None
    delim, resto = inicio.group("delim"), inicio.group("resto")
    partes = [resto]
    if len(delim) == 3 and delim not in resto:
        for _, linea in bloque[k + 1 : k + 1 + _MAX_LINEAS_DOCSTRING]:
            partes.append(linea.strip())
            if delim in linea:
                break
    texto = " ".join(partes).replace(delim, " ").strip()
    return texto or " "


def _funciones_de_bloque(ruta: str, bloque: list[tuple[int, str]]) -> list[Funcion]:
    """Extrae funciones de un bloque contiguo de líneas añadidas en un diff."""
    salida: list[Funcion] = []
    test = es_ruta_test(ruta)
    i = 0
    while i < len(bloque):
        numero, texto = bloque[i]
        coincidencia = _DEF.match(texto)
        if coincidencia is None:
            i += 1
            continue
        interpretada: tuple[FuncionAst, bool] | None = None
        fin = i
        for j in range(i, min(len(bloque), i + _MAX_LINEAS_FIRMA)):
            interpretada = _firma([t for _, t in bloque[i : j + 1]])
            if interpretada is not None:
                fin = j
                break
        docstring: str | None = None
        evaluable = False
        if interpretada is not None and interpretada[1]:
            docstring = ast.get_docstring(interpretada[0])
            evaluable = True
        else:
            k = fin + 1
            while k < len(bloque) and not bloque[k][1].strip():
                k += 1
            if k < len(bloque):
                evaluable = True
                docstring = _docstring_desde(bloque, k)
        salida.append(
            Funcion(
                archivo=ruta,
                linea=numero,
                nombre=coincidencia.group("nombre"),
                es_test=test,
                anotada=anotada(interpretada[0]) if interpretada is not None else None,
                docstring=docstring,
                docstring_evaluable=evaluable,
            )
        )
        i = fin + 1
    return salida


def _ruta_de_cabecera(linea: str) -> str | None:
    """Obtiene la ruta de una cabecera '+++ b/x'; None para /dev/null (archivo borrado)."""
    ruta = linea[4:].split("\t", 1)[0].strip()
    if ruta == "/dev/null":
        return None
    if ruta.startswith(("a/", "b/")):
        ruta = ruta[2:]
    return ruta


def fuente_diff(diff: str) -> Fuente:
    """Construye una fuente a partir de un diff unificado (sólo líneas añadidas).

    Las rutas incluyen todo archivo tocado salvo los borrados. Las funciones se
    extraen de bloques contiguos de líneas añadidas en archivos .py, y sólo cuentan
    las nuevas: si el diff elimina una ``def`` con el mismo nombre en el mismo
    archivo, la función se considera modificada y se excluye.
    """
    rutas: list[str] = []
    funciones: list[Funcion] = []
    eliminadas: set[tuple[str, str]] = set()
    ruta_actual: str | None = None
    bloque: list[tuple[int, str]] = []
    numero_nuevo = 0
    quedan_viejas = 0
    quedan_nuevas = 0

    def cerrar_bloque() -> None:
        if ruta_actual is not None and ruta_actual.endswith(".py") and bloque:
            funciones.extend(_funciones_de_bloque(ruta_actual, list(bloque)))
        bloque.clear()

    for linea in diff.splitlines():
        if (quedan_viejas > 0 or quedan_nuevas > 0) and linea.startswith("diff --git "):
            quedan_viejas = quedan_nuevas = 0  # conteo del hunk mal declarado: manda la cabecera
        if quedan_viejas > 0 or quedan_nuevas > 0:
            # Dentro de un hunk el prefijo decide, aunque el contenido empiece con '---'.
            if linea.startswith("\\"):
                continue
            if linea.startswith("+"):
                bloque.append((numero_nuevo, linea[1:]))
                numero_nuevo += 1
                quedan_nuevas -= 1
            elif linea.startswith("-"):
                cerrar_bloque()
                quedan_viejas -= 1
                previa = _DEF.match(linea[1:])
                if previa is not None and ruta_actual is not None:
                    eliminadas.add((ruta_actual, previa.group("nombre")))
            else:
                cerrar_bloque()
                numero_nuevo += 1
                quedan_viejas -= 1
                quedan_nuevas -= 1
            continue
        cerrar_bloque()
        if linea.startswith("diff --git "):
            ruta_actual = None
        elif linea.startswith("+++ "):
            ruta_actual = _ruta_de_cabecera(linea)
            if ruta_actual is not None and ruta_actual not in rutas:
                rutas.append(ruta_actual)
        else:
            cabecera = _HUNK.match(linea)
            if cabecera is not None:
                numero_nuevo = int(cabecera.group("inicio_nuevo"))
                quedan_viejas = int(cabecera.group("n_viejo") or 1)
                quedan_nuevas = int(cabecera.group("n_nuevo") or 1)
    cerrar_bloque()
    # Sólo funciones nuevas: una def reescrita (misma función, mismo archivo) no es autoría
    # completa del agente y su docstring/tipos pueden venir del original.
    nuevas = tuple(f for f in funciones if (f.archivo, f.nombre) not in eliminadas)
    return Fuente(modo="diff", textos={}, rutas=tuple(rutas), funciones=nuevas)
