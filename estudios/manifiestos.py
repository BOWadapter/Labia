"""Valida manifiestos de proyecto y pre-registros, y que el pre-registro preceda a las corridas.

§9 del Prompt Maestro depende de comparar resultados contra una asignación hecha antes de
medir. Eso sólo vale si (1) el pre-registro está bien escrito, (2) se commiteó antes que la
primera corrida de su proyecto, y (3) no se tocó después. Este módulo lo comprueba con el
historial de git en lugar de confiar en fechas escritas a mano.

El pre-registro fija también cómo se corre y cómo se decide: las tablas ``[agente.<id>]``
(comando, modelo y archivo de reglas de cada agente), ``[ejecucion]``, ``[decision]`` y
``[piloto]`` quedan congeladas junto con las tareas. Son opcionales para quien aporta
corridas hechas a mano; ``estudios.corrida`` exige las de los agentes que lanza.

Uso:
    python -m estudios.manifiestos proyectos --corridas corridas
"""

from __future__ import annotations

import argparse
import difflib
import re
import subprocess
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Union

from verificador import cargar

Esquema = Mapping[str, Union[type, "Esquema"]]

PROYECTO: Esquema = {
    "nombre": str,
    "tipo": str,
    "repositorio": str,
    "commit": str,
    "rebanada": {"descripcion": str, "comando_demo": str, "comando_eval": str},
    "reglas": {"directorio": str, "aplica": list},
}
TAREA: Esquema = {
    "id": str,
    "enunciado": str,
    "agentes": list,
    "estrategias": list,
    "repeticiones": int,
    "asignacion_sin_medir": str,
    "reglas_decisivas": list,
}
AGENTE: Esquema = {"comando": list, "modelo": str, "contexto": str}
# Regla decisiva que no sale del verificador sino de correr tests ocultos sobre cada diff.
OCULTOS = "OCULTOS"
# Tablas con claves opcionales: tipos admitidos por clave.
PROTOCOLO: Mapping[str, Mapping[str, tuple[type, ...]]] = {
    "ejecucion": {"limite_minutos": (int, float), "semilla": (int,)},
    "decision": {"alfa": (float,), "muestras": (int,), "semilla": (int,)},
    "piloto": {"enunciado": (str,)},
    "ocultos": {"dependencias": (list,), "limite_minutos": (int, float)},
}
TABLAS_PREREGISTRO = ("tarea", "agente", *PROTOCOLO)
# Tareas, agentes y estrategias forman rutas: corridas/<proyecto>/<tarea>/<agente>__<estrategia>__<n>.diff
_NOMBRE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _pista(clave: str, validas: Mapping[str, object] | tuple[str, ...]) -> str:
    """Sugerencia para una clave mal escrita."""
    parecidas = difflib.get_close_matches(clave, list(validas), n=1)
    return f" (¿quisiste decir '{parecidas[0]}'?)" if parecidas else ""


def _nombre_valido(nombre: object) -> bool:
    """True si el nombre sirve como parte de la ruta de una corrida."""
    return isinstance(nombre, str) and _NOMBRE.fullmatch(nombre) is not None and "__" not in nombre


def validar_esquema(datos: Mapping[str, object], esquema: Esquema, donde: str) -> list[str]:
    """Rechaza claves desconocidas (con sugerencia), claves faltantes y tipos equivocados."""
    errores: list[str] = []
    for clave, valor in datos.items():
        if clave not in esquema:
            errores.append(f"{donde}: clave desconocida '{clave}'{_pista(clave, esquema)}")
            continue
        esperado = esquema[clave]
        if isinstance(esperado, Mapping):
            if not isinstance(valor, dict):
                errores.append(f"{donde}.{clave}: debe ser una tabla")
            else:
                errores.extend(validar_esquema(valor, esperado, f"{donde}.{clave}"))
        elif isinstance(valor, bool) or not isinstance(valor, esperado):
            errores.append(f"{donde}.{clave}: debe ser {esperado.__name__}, es {type(valor).__name__}")
        elif isinstance(valor, list) and not all(isinstance(v, str) for v in valor):
            errores.append(f"{donde}.{clave}: la lista sólo admite texto")
    errores.extend(f"{donde}: falta la clave '{c}'" for c in esquema if c not in datos)
    return errores


def validar_protocolo(prereg: Mapping[str, object], donde: str, plantilla: bool = False) -> list[str]:
    """Valida las tablas del pre-registro que fijan cómo se corre y cómo se decide."""
    errores = [
        f"{donde}: tabla desconocida '{clave}'{_pista(clave, TABLAS_PREREGISTRO)}"
        for clave in prereg if clave not in TABLAS_PREREGISTRO
    ]
    agentes = prereg.get("agente", {})
    if not isinstance(agentes, dict):
        errores.append(f"{donde}: 'agente' debe ser una tabla por agente: [agente.<id>]")
        agentes = {}
    for identificador, declarado in agentes.items():
        sitio = f"{donde}[agente.{identificador}]"
        if not _nombre_valido(identificador):
            errores.append(f"{sitio}: el id sólo admite letras, números, '.', '-' y '_' (sin '__')")
        if not isinstance(declarado, dict):
            errores.append(f"{sitio}: debe ser una tabla")
            continue
        errores.extend(validar_esquema({c: v for c, v in declarado.items() if c != "entorno"}, AGENTE, sitio))
        entorno = declarado.get("entorno", {})
        if not isinstance(entorno, dict) or not all(isinstance(v, str) for v in entorno.values()):
            errores.append(f"{sitio}.entorno: debe ser una tabla de textos")
        if plantilla:
            continue
        comando = declarado.get("comando", [])
        comando = comando if isinstance(comando, list) else []
        if not comando:
            errores.append(f"{sitio}: 'comando' está vacío")
        if any("{modelo}" in str(parte) for parte in comando) and not str(declarado.get("modelo", "")).strip():
            errores.append(f"{sitio}: 'modelo' está vacío y el comando lo usa")
    for tabla, claves in PROTOCOLO.items():
        valores = prereg.get(tabla, {})
        sitio = f"{donde}[{tabla}]"
        if not isinstance(valores, dict):
            errores.append(f"{sitio}: debe ser una tabla")
            continue
        for clave, valor in valores.items():
            if clave not in claves:
                errores.append(f"{sitio}: clave desconocida '{clave}'{_pista(clave, claves)}")
            elif isinstance(valor, bool) or not isinstance(valor, claves[clave]):
                esperado = " o ".join(t.__name__ for t in claves[clave])
                errores.append(f"{sitio}.{clave}: debe ser {esperado}, es {type(valor).__name__}")
            elif isinstance(valor, list) and not all(isinstance(v, str) for v in valor):
                errores.append(f"{sitio}.{clave}: la lista sólo admite texto")
    ejecucion, decision = prereg.get("ejecucion", {}), prereg.get("decision", {})
    limite = ejecucion.get("limite_minutos", 1) if isinstance(ejecucion, dict) else 1
    if isinstance(limite, (int, float)) and not isinstance(limite, bool) and limite <= 0:
        errores.append(f"{donde}[ejecucion].limite_minutos: debe ser mayor que 0")
    alfa = decision.get("alfa", 0.05) if isinstance(decision, dict) else 0.05
    if isinstance(alfa, float) and not 0 < alfa < 1:
        errores.append(f"{donde}[decision].alfa: debe estar entre 0 y 1")
    muestras = decision.get("muestras", 1000) if isinstance(decision, dict) else 1000
    if isinstance(muestras, int) and not isinstance(muestras, bool) and muestras < 1000:
        errores.append(f"{donde}[decision].muestras: debe ser al menos 1000")
    return errores


def _ids_conocidos(directorio_proyecto: Path, datos: Mapping[str, object]) -> set[str]:
    """Ids de reglas generales más las del directorio de reglas propio, si existe aquí."""
    extra: Path | None = None
    reglas = datos.get("reglas")
    if isinstance(reglas, dict) and isinstance(reglas.get("directorio"), str):
        candidato = directorio_proyecto / str(reglas["directorio"])
        extra = candidato if candidato.is_dir() else None
    if (directorio_proyecto / "reglas").is_dir():
        extra = directorio_proyecto / "reglas"
    return {r.id for r in cargar(None, extra)}


def validar_proyecto(directorio: Path) -> list[str]:
    """Valida proyecto.toml y preregistro.toml de un proyecto. Las plantillas (_*) sólo en forma."""
    errores: list[str] = []
    plantilla = directorio.name.startswith("_")
    manifiesto = directorio / "proyecto.toml"
    if not manifiesto.exists():
        return [f"{directorio}: falta proyecto.toml"]
    datos = tomllib.loads(manifiesto.read_text(encoding="utf-8"))
    errores.extend(validar_esquema(datos, PROYECTO, str(manifiesto)))
    conocidos = _ids_conocidos(directorio, datos)
    reglas = datos.get("reglas", {})
    aplica = reglas.get("aplica", []) if isinstance(reglas, dict) else []
    errores.extend(f"{manifiesto}: regla desconocida en aplica: {r}" for r in aplica if r not in conocidos)
    if not plantilla:
        for clave in ("nombre", "tipo", "repositorio"):
            if not str(datos.get(clave, "")).strip():
                errores.append(f"{manifiesto}: '{clave}' está vacío")
    prereg = directorio / "preregistro.toml"
    if prereg.exists():
        contenido = tomllib.loads(prereg.read_text(encoding="utf-8"))
        errores.extend(validar_protocolo(contenido, str(prereg), plantilla))
        tareas = contenido.get("tarea", [])
        ids: list[str] = []
        for n, tarea in enumerate(tareas, 1):
            donde = f"{prereg}[tarea {n}]"
            errores.extend(validar_esquema({c: v for c, v in tarea.items() if c != "tests_ocultos"}, TAREA, donde))
            ids.append(str(tarea.get("id", "")))
            ocultos = tarea.get("tests_ocultos")
            if ocultos is not None and (not isinstance(ocultos, str) or not (directorio / ocultos).is_file()):
                errores.append(f"{donde}: 'tests_ocultos' debe ser la ruta, relativa al proyecto, de un archivo que existe")
            decisivas_tarea = tarea.get("reglas_decisivas", [])
            if isinstance(decisivas_tarea, list) and OCULTOS in decisivas_tarea and ocultos is None:
                errores.append(f"{donde}: la regla decisiva {OCULTOS} necesita 'tests_ocultos'")
            agentes = tarea.get("agentes", [])
            agentes = agentes if isinstance(agentes, list) else []
            estrategias = tarea.get("estrategias", [])
            nombres = [tarea.get("id"), *agentes, *(estrategias if isinstance(estrategias, list) else [])]
            errores.extend(
                f"{donde}: '{nombre}' no sirve como nombre: sólo letras, números, '.', '-' y '_' (sin '__')"
                for nombre in nombres if not _nombre_valido(nombre)
            )
            if plantilla:
                continue
            if len(set(agentes)) < 2:
                errores.append(f"{donde}: hacen falta al menos dos agentes distintos")
            if not str(tarea.get("enunciado", "")).strip():
                errores.append(f"{donde}: 'enunciado' está vacío")
            if tarea.get("asignacion_sin_medir") not in agentes:
                errores.append(f"{donde}: 'asignacion_sin_medir' debe ser uno de {agentes}")
            repeticiones = tarea.get("repeticiones", 0)
            if isinstance(repeticiones, bool) or not isinstance(repeticiones, int) or repeticiones < 1:
                errores.append(f"{donde}: 'repeticiones' debe ser un entero de al menos 1")
            decisivas = tarea.get("reglas_decisivas", [])
            errores.extend(
                f"{donde}: regla decisiva desconocida: {r}"
                for r in (decisivas if isinstance(decisivas, list) else []) if r not in conocidos | {OCULTOS}
            )
        if len(ids) != len(set(ids)):
            errores.append(f"{prereg}: ids de tarea repetidos")
    return errores


def _git(raiz: Path, *args: str) -> str:
    """Ejecuta git y devuelve stdout ('' si falla)."""
    salida = subprocess.run(["git", "-C", str(raiz), *args], capture_output=True, text=True)
    return salida.stdout.strip() if salida.returncode == 0 else ""


def _es_ancestro(raiz: Path, a: str, b: str) -> bool:
    """True si el commit ``a`` es ancestro de ``b``."""
    return subprocess.run(
        ["git", "-C", str(raiz), "merge-base", "--is-ancestor", a, b], capture_output=True
    ).returncode == 0


def validar_orden(raiz: Path, directorio: Path, corridas: Path) -> list[str]:
    """Todo commit que toque el pre-registro debe ser anterior a la primera corrida del proyecto.

    Eso cubre dos trampas: pre-registrar en el mismo commit que la corrida, y corregir el
    pre-registro después de ver resultados (también en una rama paralela que se fusione luego).
    """
    carpeta = corridas / directorio.name
    if not carpeta.is_dir() or not any(carpeta.rglob("*.diff")):
        return []
    if not _git(raiz, "rev-parse", "--git-dir"):
        return [f"{carpeta}: hay corridas pero esto no es un repositorio git; el orden no se puede comprobar"]
    base = raiz.resolve()
    ruta_prereg = (directorio / "preregistro.toml").resolve().relative_to(base).as_posix()
    commits_prereg = _git(raiz, "log", "--format=%H", "--reverse", "--", ruta_prereg).splitlines()
    if not commits_prereg:
        return [f"{carpeta}: hay corridas sin pre-registro commiteado ({ruta_prereg})"]
    ruta_corridas = carpeta.resolve().relative_to(base).as_posix()
    commits_corrida = _git(
        raiz, "log", "--format=%H", "--reverse", "--diff-filter=A", "--", ruta_corridas
    ).splitlines()
    if not commits_corrida:
        # Corridas aún sin commit (p. ej. dentro de pre-commit): el pre-registro ya debe estar fijo.
        if _git(raiz, "status", "--porcelain", "--", ruta_prereg):
            return [f"{ruta_prereg}: tiene cambios sin commit y hay corridas nuevas; commitéalo antes"]
        return []
    primera = commits_corrida[0]
    return [
        f"{ruta_prereg}: cambiado en {c[:7]}, que no es anterior a la primera corrida ({primera[:7]})"
        for c in commits_prereg
        if c == primera or not _es_ancestro(raiz, c, primera)
    ]


def main(argv: list[str] | None = None) -> int:
    """Valida todos los proyectos; sale con 1 si hay algún error."""
    parser = argparse.ArgumentParser(prog="python -m estudios.manifiestos")
    parser.add_argument("proyectos", type=Path)
    parser.add_argument("--corridas", type=Path, default=Path("corridas"))
    parser.add_argument("--repo", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    errores: list[str] = []
    directorios = sorted(p for p in args.proyectos.iterdir() if p.is_dir())
    for directorio in directorios:
        errores.extend(validar_proyecto(directorio))
        if not directorio.name.startswith("_"):
            errores.extend(validar_orden(args.repo, directorio, args.corridas))
    for error in errores:
        print(error, file=sys.stderr)
    print(f"proyectos: {len(directorios)} · errores: {len(errores)}")
    return 1 if errores else 0


if __name__ == "__main__":
    raise SystemExit(main())
