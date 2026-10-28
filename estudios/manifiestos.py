"""Valida manifiestos de proyecto y pre-registros, y que el pre-registro preceda a las corridas.

§9 del Prompt Maestro depende de comparar resultados contra una asignación hecha antes de
medir. Eso sólo vale si (1) el pre-registro está bien escrito, (2) se commiteó antes que la
primera corrida de su proyecto, y (3) no se tocó después. Este módulo lo comprueba con el
historial de git en lugar de confiar en fechas escritas a mano.

Uso:
    python -m estudios.manifiestos proyectos --corridas corridas
"""

from __future__ import annotations

import argparse
import difflib
import subprocess
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Union

from verificador import Regla, cargar, comprobar_casos
from verificador.reglas import de_directorio

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


def validar_esquema(datos: Mapping[str, object], esquema: Esquema, donde: str) -> list[str]:
    """Rechaza claves desconocidas (con sugerencia), claves faltantes y tipos equivocados."""
    errores: list[str] = []
    for clave, valor in datos.items():
        if clave not in esquema:
            parecidas = difflib.get_close_matches(clave, list(esquema), n=1)
            pista = f" (¿quisiste decir '{parecidas[0]}'?)" if parecidas else ""
            errores.append(f"{donde}: clave desconocida '{clave}'{pista}")
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


def _reglas_del_proyecto(directorio_proyecto: Path, datos: Mapping[str, object]) -> list[Regla]:
    """Reglas propias: el directorio que declara el manifiesto o, si no existe aquí, ``reglas/``."""
    candidatos: list[Path] = []
    reglas = datos.get("reglas")
    if isinstance(reglas, dict) and isinstance(reglas.get("directorio"), str):
        candidatos.append(directorio_proyecto / str(reglas["directorio"]))
    candidatos.append(directorio_proyecto / "reglas")
    for candidato in candidatos:
        if candidato.is_dir():
            return de_directorio(candidato)
    return []


def validar_proyecto(directorio: Path) -> list[str]:
    """Valida proyecto.toml y preregistro.toml de un proyecto. Las plantillas (_*) sólo en forma."""
    errores: list[str] = []
    plantilla = directorio.name.startswith("_")
    manifiesto = directorio / "proyecto.toml"
    if not manifiesto.exists():
        return [f"{directorio}: falta proyecto.toml"]
    datos = tomllib.loads(manifiesto.read_text(encoding="utf-8"))
    errores.extend(validar_esquema(datos, PROYECTO, str(manifiesto)))
    propias = _reglas_del_proyecto(directorio, datos)
    conocidos = {r.id for r in cargar(None)} | {r.id for r in propias}
    for regla in propias:
        errores.extend(f"{directorio}: {e}" for e in comprobar_casos(regla))
    reglas = datos.get("reglas", {})
    aplica = reglas.get("aplica", []) if isinstance(reglas, dict) else []
    errores.extend(f"{manifiesto}: regla desconocida en aplica: {r}" for r in aplica if r not in conocidos)
    if not plantilla:
        for clave in ("nombre", "tipo", "repositorio"):
            if not str(datos.get(clave, "")).strip():
                errores.append(f"{manifiesto}: '{clave}' está vacío")
    prereg = directorio / "preregistro.toml"
    if prereg.exists():
        tareas = tomllib.loads(prereg.read_text(encoding="utf-8")).get("tarea", [])
        ids: list[str] = []
        for n, tarea in enumerate(tareas, 1):
            donde = f"{prereg}[tarea {n}]"
            errores.extend(validar_esquema(tarea, TAREA, donde))
            ids.append(str(tarea.get("id", "")))
            if plantilla:
                continue
            agentes = tarea.get("agentes", [])
            agentes = agentes if isinstance(agentes, list) else []
            if len(set(agentes)) < 2:
                errores.append(f"{donde}: hacen falta al menos dos agentes distintos")
            if not str(tarea.get("enunciado", "")).strip():
                errores.append(f"{donde}: 'enunciado' está vacío")
            asignacion = tarea.get("asignacion_sin_medir")
            if not str(asignacion or "").strip():
                errores.append(
                    f"{donde}: 'asignacion_sin_medir' vacío: escribe a qué agente darías hoy esta "
                    "tarea, sin medir, y commitéalo antes de cualquier corrida"
                )
            elif asignacion not in agentes:
                errores.append(f"{donde}: 'asignacion_sin_medir' debe ser uno de {agentes}")
            repeticiones = tarea.get("repeticiones", 0)
            if isinstance(repeticiones, bool) or not isinstance(repeticiones, int) or repeticiones < 1:
                errores.append(f"{donde}: 'repeticiones' debe ser un entero de al menos 1")
            decisivas = tarea.get("reglas_decisivas", [])
            errores.extend(
                f"{donde}: regla decisiva desconocida: {r}"
                for r in (decisivas if isinstance(decisivas, list) else []) if r not in conocidos
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
