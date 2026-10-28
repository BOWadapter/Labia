"""CLI del verificador. Imprime JSON en stdout; ``casos`` sale con 1 si alguna regla no discrimina."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__, cargar, comprobar_casos, fuente_diff, fuente_directorio, verificar

SUBCOMANDOS = ("reglas", "casos", "directorio", "diff")


def _git(repo: Path, *args: str) -> str:
    """Ejecuta git en el repositorio y devuelve stdout."""
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada: ``reglas``, ``casos``, ``directorio`` o ``diff``."""
    parser = argparse.ArgumentParser(prog="python -m verificador")
    sub = parser.add_subparsers(dest="orden", required=True)
    for nombre, ayuda in (("reglas", "lista las reglas"), ("casos", "comprueba que cada regla discrimina")):
        p = sub.add_parser(nombre, help=ayuda)
        p.add_argument("--reglas-proyecto", type=Path)
        p.add_argument("--tipo")
    p_dir = sub.add_parser("directorio", help="verifica un árbol de código")
    p_dir.add_argument("ruta", type=Path)
    p_dir.add_argument("--stdout", type=Path, help="salida del comando de demostración (R3)")
    p_dir.add_argument("--git", type=Path, help="repositorio para leer commits (R6)")
    p_diff = sub.add_parser("diff", help="verifica un diff unificado ('-' = stdin)")
    p_diff.add_argument("archivo")
    for p in (p_dir, p_diff):
        p.add_argument("--reglas", help="ids separados por coma; por defecto todas")
        p.add_argument("--tipo", default="python", help="python, typescript, ... ('cualquiera' siempre aplica)")
        p.add_argument("--reglas-proyecto", type=Path, help="directorio con reglas propias del proyecto")
    args = parser.parse_args(argv)

    if args.orden in ("reglas", "casos"):
        reglas = cargar(args.tipo, args.reglas_proyecto)
        if args.orden == "reglas":
            listado = [
                {"id": r.id, "nombre": r.nombre, "tipo": r.tipo, "mecanica": r.mecanica, "casos": len(r.casos)}
                for r in reglas
            ]
            print(json.dumps(listado, ensure_ascii=False, indent=2))
            return 0
        errores = [e for r in reglas for e in comprobar_casos(r)]
        print(json.dumps({"reglas": len(reglas), "errores": errores}, ensure_ascii=False, indent=2))
        return 1 if errores else 0

    ids = set(args.reglas.split(",")) if args.reglas else None
    informe: dict[str, object] = {
        "verificador": __version__,
        "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "modo": args.orden,
        "tipo": args.tipo,
    }
    if args.orden == "directorio":
        stdout = args.stdout.read_text(encoding="utf-8") if args.stdout else None
        commits = None
        if args.git:
            commits = [c for c in _git(args.git, "log", "--format=%s").splitlines() if c]
            informe["commit"] = _git(args.git, "rev-parse", "--short", "HEAD").strip()
        fuente = fuente_directorio(args.ruta, stdout=stdout, commits=commits)
        informe["objetivo"] = str(args.ruta)
    else:
        texto = sys.stdin.read() if args.archivo == "-" else Path(args.archivo).read_text(encoding="utf-8")
        fuente = fuente_diff(texto)
        informe["objetivo"] = args.archivo
    informe["reglas"] = [r.como_dict() for r in verificar(fuente, ids, args.tipo, args.reglas_proyecto)]
    print(json.dumps(informe, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
