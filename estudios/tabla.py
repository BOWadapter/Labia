"""Tabla regla × agente × estrategia a partir de corridas, con intervalos.

Formato de entrada para corridas propias o de la comunidad:

    corridas/<NNN-proyecto>/<tarea>/<agente>__<estrategia>__<n>.diff

La corrida de un agente no es reproducible; su verificación sí. El CI recalcula la
tabla desde los diffs, así que la cifra la produce el CI, no quien envía la corrida.

Uso:
    python -m estudios.tabla corridas/ [--json tabla.json]
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from verificador import fuente_diff, verificar, wilson

REGLAS_DIFF = ("R1", "R2", "R7")
SEMILLA = 20261028
REMUESTREOS = 2000


@dataclass(frozen=True)
class Corrida:
    """Una corrida verificada: quién, con qué estrategia, sobre qué tarea, y sus conteos."""

    tarea: str
    agente: str
    estrategia: str
    diff_vacio: bool
    conteos: dict[str, tuple[int, int]]


def verificar_corrida(tarea: str, agente: str, estrategia: str, diff: str) -> Corrida:
    """Verifica el diff de una corrida con las reglas aplicables a diffs."""
    resultados = verificar(fuente_diff(diff), set(REGLAS_DIFF))
    return Corrida(
        tarea=tarea,
        agente=agente,
        estrategia=estrategia,
        diff_vacio=not diff.strip(),
        conteos={r.regla: (r.oportunidades, r.violaciones) for r in resultados},
    )


def leer_directorio(raiz: Path) -> list[Corrida]:
    """Lee corridas con la convención ``<tarea>/<agente>__<estrategia>__<n>.diff``."""
    corridas: list[Corrida] = []
    for archivo in sorted(raiz.rglob("*.diff")):
        partes = archivo.stem.split("__")
        if len(partes) != 3:
            raise ValueError(f"nombre fuera de convención: {archivo}")
        agente, estrategia, _ = partes
        tarea = f"{archivo.parent.parent.name}/{archivo.parent.name}"
        corridas.append(verificar_corrida(tarea, agente, estrategia, archivo.read_text(encoding="utf-8")))
    return corridas


def suma(corridas: Iterable[Corrida], regla: str) -> tuple[int, int]:
    """Suma oportunidades y violaciones de una regla."""
    oportunidades = violaciones = 0
    for c in corridas:
        o, v = c.conteos[regla]
        oportunidades += o
        violaciones += v
    return oportunidades, violaciones


def diferencia_bootstrap(
    corridas: Sequence[Corrida], regla: str, estrategia: str, base: str = "none"
) -> tuple[float | None, float | None, float | None]:
    """Δ tasa (estrategia − base) con IC 95% remuestreando tareas (la tarea es el conglomerado)."""
    por_tarea: dict[str, dict[str, list[Corrida]]] = defaultdict(lambda: defaultdict(list))
    for c in corridas:
        por_tarea[c.tarea][c.estrategia].append(c)
    tareas = sorted(t for t, d in por_tarea.items() if d[base] and d[estrategia])

    def delta(muestra: list[str]) -> float | None:
        a = suma((c for t in muestra for c in por_tarea[t][estrategia]), regla)
        b = suma((c for t in muestra for c in por_tarea[t][base]), regla)
        if a[0] == 0 or b[0] == 0:
            return None
        return a[1] / a[0] - b[1] / b[0]

    puntual = delta(tareas) if tareas else None
    if puntual is None:
        return None, None, None
    azar = random.Random(SEMILLA)
    deltas = sorted(
        d for _ in range(REMUESTREOS) if (d := delta([azar.choice(tareas) for _ in tareas])) is not None
    )
    return puntual, deltas[int(0.025 * len(deltas))], deltas[int(0.975 * len(deltas)) - 1]


def tabla(corridas: Sequence[Corrida], titulo: str, base: str = "none") -> tuple[str, list[dict[str, object]]]:
    """Tabla markdown y filas JSON: tasa por regla con Wilson, y Δ frente a la estrategia base."""
    estrategias = sorted({c.estrategia for c in corridas}, key=lambda e: (e != base, e))
    md = [
        f"### {titulo}", "",
        "| agente | estrategia | corridas | regla | violaciones/oportunidades | tasa | IC95 (Wilson) |",
        "|---|---|---|---|---|---|---|",
    ]
    filas: list[dict[str, object]] = []
    agentes = sorted({c.agente for c in corridas})
    for agente in agentes:
        for estrategia in estrategias:
            grupo = [c for c in corridas if c.agente == agente and c.estrategia == estrategia]
            if not grupo:
                continue
            for regla in REGLAS_DIFF:
                o, v = suma(grupo, regla)
                bajo, alto = wilson(v, o)
                md.append(
                    f"| {agente} | {estrategia} | {len(grupo)} | {regla} | {v}/{o} | "
                    f"{(f'{v / o:.1%}' if o else '—')} | {bajo:.0%}–{alto:.0%} |"
                )
                filas.append({"subconjunto": titulo, "agente": agente, "estrategia": estrategia,
                              "corridas": len(grupo), "regla": regla, "oportunidades": o,
                              "violaciones": v, "tasa": v / o if o else None, "wilson95": [bajo, alto]})
    otras = [e for e in estrategias if e != base]
    if otras and base in estrategias:
        md += ["", f"Δ tasa frente a `{base}` (IC 95% por remuestreo de tareas):", ""]
        md += ["| agente | regla | " + " | ".join(f"{e} − {base}" for e in otras) + " |",
               "|---|---|" + "---|" * len(otras)]
        for agente in agentes:
            propias = [c for c in corridas if c.agente == agente]
            for regla in REGLAS_DIFF:
                celdas = []
                for estrategia in otras:
                    p, b, a = diferencia_bootstrap(propias, regla, estrategia, base)
                    celdas.append("—" if p is None else f"{p:+.1%} [{b:+.1%}, {a:+.1%}]")
                    filas.append({"subconjunto": titulo, "agente": agente, "regla": regla,
                                  "contraste": f"{estrategia}-{base}", "delta": p, "ic95": [b, a]})
                md.append(f"| {agente} | {regla} | " + " | ".join(celdas) + " |")
    return "\n".join(md) + "\n", filas


def main(argv: list[str] | None = None) -> int:
    """Imprime la tabla de un directorio de corridas y, opcionalmente, el JSON."""
    parser = argparse.ArgumentParser(prog="python -m estudios.tabla")
    parser.add_argument("raiz", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--base", default="none")
    args = parser.parse_args(argv)
    corridas = leer_directorio(args.raiz)
    texto, filas = tabla(corridas, str(args.raiz), args.base)
    print(f"Corridas: {len(corridas)}\n\n{texto}")
    if args.json:
        args.json.write_text(json.dumps({"corridas": len(corridas), "filas": filas},
                                        ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
