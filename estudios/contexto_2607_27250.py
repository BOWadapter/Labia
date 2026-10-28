"""Re-puntúa los diffs públicos de arXiv 2607.27250 con el verificador, por agente y estrategia.

Datos: https://github.com/codeprakhar25/context-files-coding-agents (MIT), commit c929724,
``data/experiment_full.db``. 291 corridas de Claude Code (``claude --print``) y Codex CLI
(``codex exec``) sobre tareas reales de opshin, pdm y firebase-admin-python, con tres
estrategias de entrega del AGENTS.md: none, always_on (inyección completa) y selective
(wiki consultable por herramienta).

El paper mide corrección (tests ocultos). Aquí se mide conformidad mecánica del código
añadido: R1 (anotaciones), R2 (docstrings) y R7 (tocar tests), sólo en funciones nuevas.
Esas reglas no estaban declaradas en los AGENTS.md de los repos, salvo en parte en
opshin (pide escribir tests primero; la documentación sale de los comentarios de
función); por eso opshin se reporta aparte. Mide conformidad espontánea y si el
mecanismo de entrega la mueve, no cumplimiento de reglas declaradas.

Uso (desde la raíz del repo):
    git clone https://github.com/codeprakhar25/context-files-coding-agents ../cfa
    python -m estudios.contexto_2607_27250 ../cfa/data/experiment_full.db --json estudio.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from .tabla import Corrida, tabla, verificar_corrida


def leer(db: Path) -> list[tuple[str, Corrida]]:
    """Lee las corridas en modo sólo lectura y devuelve (repo, corrida verificada)."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    filas = con.execute(
        "select task_id, repo, agent, strategy, coalesce(final_diff, '') from runs"
    ).fetchall()
    con.close()
    return [
        (str(repo), verificar_corrida(str(tarea), str(agente), str(estrategia), str(diff)))
        for tarea, repo, agente, estrategia, diff in filas
    ]


def main(argv: list[str] | None = None) -> int:
    """Imprime las tablas (todas las tareas y sólo opshin) y, opcionalmente, el JSON."""
    parser = argparse.ArgumentParser(prog="python -m estudios.contexto_2607_27250")
    parser.add_argument("db", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    pares = leer(args.db)
    corridas = [c for _, c in pares]
    opshin = [c for repo, c in pares if "opshin" in repo.lower()]
    texto_total, filas_total = tabla(corridas, "Todas las tareas")
    texto_opshin, filas_opshin = tabla(opshin, "Sólo opshin")
    vacias = sum(c.diff_vacio for c in corridas)
    print(f"Corridas: {len(corridas)} · con diff vacío: {vacias}\n\n{texto_total}\n{texto_opshin}")
    if args.json:
        args.json.write_text(
            json.dumps({"fuente": "arXiv 2607.27250 @ c929724", "corridas": len(corridas),
                        "diff_vacio": vacias, "filas": filas_total + filas_opshin},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
