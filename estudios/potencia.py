"""Control negativo y potencia de la regla de decisión, con las corridas públicas de arXiv 2607.27250.

Antes de fiarse de una regla que dice «este agente cumple más» hay que saber cuántas veces
lo dice cuando no hay diferencia (falsa alarma) y cuántas cuando sí la hay (potencia). Aquí
se responde remuestreando corridas reales de Claude Code y Codex:

- nulo: corridas de un mismo agente repartidas al azar en dos grupos. Todo lo que una
  regla declare ahí es falsa alarma;
- efecto: un agente contra el otro con ``always_on``, el contraste real de esos datos.

Se comparan dos reglas sobre los mismos datos: el intervalo por remuestreo de tareas de
``estudios.tabla`` y la permutación por tarea de ``estudios.decision``. Un diseño es el
número de tareas y de corridas por agente y tarea; el del pre-registro de un proyecto se
puede leer aquí antes de gastar una corrida.

Uso (desde la raíz del repo, con los datos del estudio clonados):
    python -m estudios.potencia ../cfa/data/experiment_full.db [--json potencia.json] [--sims N]
"""

from __future__ import annotations

import argparse
import io
import json
import random
import sys
from collections import defaultdict
from collections.abc import Callable, Sequence
from pathlib import Path

from .contexto_2607_27250 import leer
from .decision import ALFA, Observacion, permutacion
from .tabla import Corrida, diferencia_bootstrap

REGLA = "R1"
AGENTES = ("claude_code", "codex")
ESTRATEGIA = "always_on"
DISENOS = ((3, 3), (6, 3), (12, 3))
SIMULACIONES = 200
MUESTRAS = 2000
SEMILLA = 20261204

Celdas = dict[tuple[str, str, str], list[tuple[int, int]]]
Constructor = Callable[[Sequence[str], random.Random], list[Observacion]]


def celdas(corridas: Sequence[Corrida], regla: str = REGLA) -> Celdas:
    """(oportunidades, violaciones) de cada corrida, por (tarea, agente, estrategia)."""
    salida: Celdas = defaultdict(list)
    for corrida in corridas:
        salida[(corrida.tarea, corrida.agente, corrida.estrategia)].append(corrida.conteos[regla])
    return dict(salida)


def declara_permutacion(observaciones: Sequence[Observacion], alfa: float = ALFA) -> bool:
    """True si la permutación por tarea distingue a los grupos 'a' y 'b'."""
    _, p, _, _ = permutacion(observaciones, "a", "b", MUESTRAS, SEMILLA)
    return p is not None and p <= alfa


def declara_intervalo(observaciones: Sequence[Observacion]) -> bool:
    """True si el intervalo por remuestreo de tareas de ``estudios.tabla`` excluye el cero."""
    corridas = [
        Corrida(o.estrato, "x", o.agente, False, {REGLA: (o.oportunidades, o.violaciones)}) for o in observaciones
    ]
    puntual, bajo, alto = diferencia_bootstrap(corridas, REGLA, "b", base="a")
    return puntual is not None and bajo is not None and alto is not None and (bajo > 0 or alto < 0)


def nulo(datos: Celdas, agente: str, n: int) -> tuple[list[str], Constructor]:
    """Tareas utilizables y constructor de un experimento sin efecto: un agente contra sí mismo."""
    propias: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for (tarea, de, _), conteos in sorted(datos.items()):
        if de == agente:
            propias[tarea].extend(conteos)
    utilizables = sorted(t for t, conteos in propias.items() if len(conteos) >= 2 * n)

    def construir(tareas: Sequence[str], azar: random.Random) -> list[Observacion]:
        return [
            Observacion(tarea, "ab"[i % 2], oportunidades, violaciones)
            for tarea in tareas
            for i, (oportunidades, violaciones) in enumerate(azar.sample(propias[tarea], 2 * n))
        ]

    return utilizables, construir


def efecto(datos: Celdas, n: int, estrategia: str = ESTRATEGIA) -> tuple[list[str], Constructor]:
    """Tareas utilizables y constructor del contraste real entre los dos agentes."""
    utilizables = sorted(
        {t for t, _, _ in datos if all(len(datos.get((t, agente, estrategia), [])) >= n for agente in AGENTES)}
    )

    def construir(tareas: Sequence[str], azar: random.Random) -> list[Observacion]:
        return [
            Observacion(tarea, etiqueta, oportunidades, violaciones)
            for tarea in tareas
            for etiqueta, agente in zip("ab", AGENTES)
            for oportunidades, violaciones in azar.sample(datos[(tarea, agente, estrategia)], n)
        ]

    return utilizables, construir


def simular(
    utilizables: Sequence[str], construir: Constructor, tareas: int, simulaciones: int, semilla: int
) -> tuple[float, float] | None:
    """Fracción de experimentos simulados en que cada regla declara diferencia: (intervalo, permutación)."""
    if len(utilizables) < tareas:
        return None
    azar = random.Random(semilla)
    intervalo = permutada = 0
    for _ in range(simulaciones):
        observaciones = construir(azar.sample(list(utilizables), tareas), azar)
        intervalo += declara_intervalo(observaciones)
        permutada += declara_permutacion(observaciones)
    return intervalo / simulaciones, permutada / simulaciones


def informe(datos: Celdas, simulaciones: int = SIMULACIONES) -> tuple[str, list[dict[str, object]]]:
    """Tabla markdown y filas JSON: falsa alarma y potencia de cada regla por diseño."""
    md = [
        f"### Regla de decisión: falsa alarma y potencia ({REGLA}, corridas públicas de arXiv 2607.27250)", "",
        f"Fracción de {simulaciones} experimentos simulados en que cada regla declara diferencia entre dos grupos.",
        "En las filas «nulo» los grupos son corridas del mismo agente repartidas al azar: lo que se declare es",
        f"falsa alarma y no debería pasar de {ALFA:.0%}. En las filas «efecto» la diferencia es real: es la potencia.",
        "",
        "| escenario | tareas | corridas por grupo y tarea | intervalo por remuestreo de tareas | permutación por tarea |",
        "|---|---|---|---|---|",
    ]
    filas: list[dict[str, object]] = []
    escenarios: list[tuple[str, str | None]] = [(f"nulo: {agente} contra sí mismo", agente) for agente in AGENTES]
    escenarios.append((f"efecto: {AGENTES[0]} contra {AGENTES[1]} con {ESTRATEGIA}", None))
    for orden, (nombre, agente) in enumerate(escenarios):
        for tareas, n in DISENOS:
            utilizables, construir = efecto(datos, n) if agente is None else nulo(datos, agente, n)
            resultado = simular(utilizables, construir, tareas, simulaciones, SEMILLA + 100 * orden + tareas)
            celdas_md = "— | —" if resultado is None else f"{resultado[0]:.1%} | {resultado[1]:.1%}"
            md.append(f"| {nombre} | {tareas} | {n} | {celdas_md} |")
            filas.append({
                "escenario": nombre, "tareas": tareas, "corridas_por_grupo_y_tarea": n,
                "tareas_utilizables": len(utilizables),
                "intervalo": None if resultado is None else resultado[0],
                "permutacion": None if resultado is None else resultado[1],
            })
    return "\n".join(md) + "\n", filas


def main(argv: list[str] | None = None) -> int:
    """Imprime la tabla de falsa alarma y potencia y, opcionalmente, su JSON."""
    parser = argparse.ArgumentParser(prog="python -m estudios.potencia")
    parser.add_argument("db", type=Path)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--sims", type=int, default=SIMULACIONES)
    args = parser.parse_args(argv)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(errors="replace")
    texto, filas = informe(celdas([corrida for _, corrida in leer(args.db)]), args.sims)
    print(texto)
    if args.json:
        args.json.write_text(
            json.dumps({"fuente": "arXiv 2607.27250 @ c929724", "regla": REGLA, "simulaciones": args.sims,
                        "filas": filas}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
