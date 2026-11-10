"""Qué agente indica la medición para un proyecto, con una regla fijada antes de medir.

La unidad independiente es la corrida, no la oportunidad: las oportunidades de una misma
corrida comparten agente, tarea y contexto. Por eso la prueba permuta corridas, y sólo
dentro de cada tarea y estrategia (permutación estratificada): si el agente no importara,
cualquier reparto de las corridas de una tarea entre los dos agentes habría sido igual de
probable.

Para cada regla decisiva y cada par de agentes:

- estadístico: tasa de violación de A menos la de B, con los conteos sumados;
- p: fracción de repartos con un estadístico al menos tan extremo como el observado. Un
  reparto que deja a un agente sin oportunidades cuenta como extremo (conservador);
- se enumeran todos los repartos si son pocos; si no, se muestrean con semilla fija;
- corrección de Holm entre todas las pruebas del proyecto.

El veredicto se calcula una sola vez, cuando están todas las corridas pre-registradas:
mirar antes y detenerse al ver un resultado infla la falsa alarma. ``sin veredicto`` es
un resultado, no un fallo: con ese diseño, los datos no distinguen a los agentes.

``estudios.potencia`` comprueba esta regla contra corridas públicas: cuánto declara
cuando no hay nada que declarar y cuánto cuando sí.

Uso:
    python -m estudios.decision proyectos/NNN-nombre [--corridas corridas] [--json salida.json]
"""

from __future__ import annotations

import argparse
import io
import itertools
import json
import math
import random
import sys
import tomllib
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from verificador import fuente_diff, verificar, wilson

from .campos import como_entero, como_lista, como_real, como_tabla, como_texto

ALFA = 0.05
MUESTRAS = 20000
SEMILLA = 20261204
LIMITE_EXACTO = 100_000
_TOLERANCIA = 1e-12


@dataclass(frozen=True)
class Observacion:
    """Conteos de una regla en una corrida. ``estrato`` es la tarea (y estrategia) de la corrida."""

    estrato: str
    agente: str
    oportunidades: int
    violaciones: int


@dataclass(frozen=True)
class Prueba:
    """Contraste entre dos agentes para una regla. Los conteos son (violaciones, oportunidades)."""

    regla: str
    a: str
    b: str
    conteo_a: tuple[int, int]
    conteo_b: tuple[int, int]
    diferencia: float | None
    p: float | None
    p_holm: float | None
    repartos: int
    exacta: bool

    def como_dict(self) -> dict[str, object]:
        """Serializa la prueba para el informe JSON."""
        return {
            "regla": self.regla, "a": self.a, "b": self.b,
            "violaciones_oportunidades_a": list(self.conteo_a),
            "violaciones_oportunidades_b": list(self.conteo_b),
            "diferencia": self.diferencia, "p": self.p, "p_holm": self.p_holm,
            "repartos": self.repartos, "exacta": self.exacta,
        }


def _diferencia(a: tuple[int, int], b: tuple[int, int]) -> float | None:
    """Tasa de A menos tasa de B, con conteos (violaciones, oportunidades). None si falta denominador."""
    if a[1] == 0 or b[1] == 0:
        return None
    return a[0] / a[1] - b[0] / b[1]


def _extremo(candidata: float | None, observada: float) -> bool:
    """Un reparto sin oportunidades en un lado cuenta como extremo: nunca ayuda a dar veredicto."""
    return candidata is None or abs(candidata) >= abs(observada) - _TOLERANCIA


def permutacion(
    observaciones: Sequence[Observacion], a: str, b: str, muestras: int = MUESTRAS, semilla: int = SEMILLA
) -> tuple[float | None, float | None, int, bool]:
    """Devuelve (diferencia observada, p bilateral, repartos posibles, si se enumeraron todos)."""
    por_estrato: dict[str, tuple[list[tuple[int, int]], list[tuple[int, int]]]] = defaultdict(lambda: ([], []))
    for observacion in observaciones:
        if observacion.agente == a:
            por_estrato[observacion.estrato][0].append((observacion.violaciones, observacion.oportunidades))
        elif observacion.agente == b:
            por_estrato[observacion.estrato][1].append((observacion.violaciones, observacion.oportunidades))
    estratos = [(de_a, de_b) for _, (de_a, de_b) in sorted(por_estrato.items()) if de_a and de_b]
    if not estratos:
        return None, None, 0, True
    total_v = sum(v for de_a, de_b in estratos for v, _ in de_a + de_b)
    total_o = sum(o for de_a, de_b in estratos for _, o in de_a + de_b)
    propio_v = sum(v for de_a, _ in estratos for v, _ in de_a)
    propio_o = sum(o for de_a, _ in estratos for _, o in de_a)
    observada = _diferencia((propio_v, propio_o), (total_v - propio_v, total_o - propio_o))
    repartos = math.prod(math.comb(len(de_a) + len(de_b), len(de_a)) for de_a, de_b in estratos)
    exacta = repartos <= LIMITE_EXACTO
    if observada is None:
        return None, None, repartos, exacta

    def diferencia_con(v_a: int, o_a: int) -> float | None:
        return _diferencia((v_a, o_a), (total_v - v_a, total_o - o_a))

    if exacta:
        # Sumas posibles del lado A en cada estrato; su producto cartesiano recorre todos los repartos.
        opciones = [
            [(sum(v for v, _ in c), sum(o for _, o in c)) for c in itertools.combinations(de_a + de_b, len(de_a))]
            for de_a, de_b in estratos
        ]
        extremos = sum(
            _extremo(diferencia_con(sum(v for v, _ in e), sum(o for _, o in e)), observada)
            for e in itertools.product(*opciones)
        )
        return observada, extremos / repartos, repartos, True
    azar = random.Random(semilla)
    extremos = 0
    for _ in range(muestras):
        v_a = o_a = 0
        for de_a, de_b in estratos:
            for v, o in azar.sample(de_a + de_b, len(de_a)):
                v_a += v
                o_a += o
        extremos += _extremo(diferencia_con(v_a, o_a), observada)
    return observada, (1 + extremos) / (1 + muestras), repartos, False


def holm(valores: Sequence[float | None]) -> list[float | None]:
    """p ajustadas por Holm. Las pruebas sin p (sin oportunidades) no entran en la familia."""
    orden = sorted((p, i) for i, p in enumerate(valores) if p is not None)
    ajustadas: list[float | None] = [None] * len(valores)
    acumulada = 0.0
    for puesto, (p, i) in enumerate(orden):
        acumulada = max(acumulada, min(1.0, (len(orden) - puesto) * p))
        ajustadas[i] = acumulada
    return ajustadas


def _conteo(observaciones: Sequence[Observacion], agente: str) -> tuple[int, int]:
    """(violaciones, oportunidades) de un agente."""
    propias = [o for o in observaciones if o.agente == agente]
    return sum(o.violaciones for o in propias), sum(o.oportunidades for o in propias)


def contrastar(
    por_regla: Mapping[str, Sequence[Observacion]], agentes: Sequence[str],
    muestras: int = MUESTRAS, semilla: int = SEMILLA,
) -> list[Prueba]:
    """Una prueba por regla y par de agentes, con Holm entre todas."""
    sin_ajuste: list[Prueba] = []
    for regla in sorted(por_regla):
        observaciones = por_regla[regla]
        for a, b in itertools.combinations(sorted(agentes), 2):
            diferencia, p, repartos, exacta = permutacion(observaciones, a, b, muestras, semilla)
            sin_ajuste.append(Prueba(
                regla, a, b, _conteo(observaciones, a), _conteo(observaciones, b), diferencia, p, None, repartos, exacta,
            ))
    ajustadas = holm([prueba.p for prueba in sin_ajuste])
    return [
        Prueba(s.regla, s.a, s.b, s.conteo_a, s.conteo_b, s.diferencia, s.p, ajustada, s.repartos, s.exacta)
        for s, ajustada in zip(sin_ajuste, ajustadas)
    ]


def veredicto(pruebas: Sequence[Prueba], alfa: float = ALFA) -> tuple[str, str | None]:
    """('indica', agente) si toda diferencia significativa favorece al mismo agente; si no, por qué no."""
    favorecidos: set[str] = set()
    for prueba in pruebas:
        if prueba.p_holm is None or prueba.diferencia is None or prueba.p_holm > alfa or prueba.diferencia == 0:
            continue
        favorecidos.add(prueba.a if prueba.diferencia < 0 else prueba.b)
    if not favorecidos:
        return "sin veredicto", None
    if len(favorecidos) > 1:
        return "conflicto", None
    return "indica", next(iter(favorecidos))


def resolucion(repeticiones_por_estrato: Sequence[int], muestras: int = MUESTRAS) -> tuple[int, float]:
    """Repartos posibles y la p más chica que puede dar un diseño con n corridas por agente y estrato.

    Si esa p no baja de alfa, el diseño no puede dar veredicto salga lo que salga.
    """
    repartos = math.prod(math.comb(2 * n, n) for n in repeticiones_por_estrato)
    return repartos, (min(1.0, 2 / repartos) if repartos <= LIMITE_EXACTO else 1 / (1 + muestras))


def esperadas(tareas: Sequence[Mapping[str, object]]) -> list[tuple[str, str, str, int]]:
    """Todas las corridas que el pre-registro compromete: (tarea, agente, estrategia, n)."""
    return [
        (como_texto(t.get("id")), agente, estrategia, n)
        for t in tareas
        for agente in como_lista(t.get("agentes"))
        for estrategia in como_lista(t.get("estrategias"))
        for n in range(1, como_entero(t.get("repeticiones"), 0) + 1)
    ]


def informe(directorio: Path, corridas: Path) -> tuple[str, dict[str, object]]:
    """Informe en markdown y JSON: avance, pruebas, veredicto y contraste con lo pre-registrado."""
    manifiesto = tomllib.loads((directorio / "proyecto.toml").read_text(encoding="utf-8"))
    prereg = tomllib.loads((directorio / "preregistro.toml").read_text(encoding="utf-8"))
    tareas = [como_tabla(t) for t in prereg.get("tarea", []) if isinstance(t, dict)]
    decision = como_tabla(prereg.get("decision"))
    alfa = como_real(decision.get("alfa"), ALFA)
    muestras = como_entero(decision.get("muestras"), MUESTRAS)
    semilla = como_entero(decision.get("semilla"), SEMILLA)
    reglas = como_tabla(manifiesto.get("reglas"))
    propias = directorio / como_texto(reglas.get("directorio"))
    extra = propias if como_texto(reglas.get("directorio")) and propias.is_dir() else None
    aplica = set(como_lista(reglas.get("aplica")))
    tipo = como_texto(manifiesto.get("tipo")) or "python"
    nombre = directorio.name
    comprometidas = esperadas(tareas)
    decisivas = {como_texto(t.get("id")): set(como_lista(t.get("reglas_decisivas"))) for t in tareas}
    por_regla: dict[str, list[Observacion]] = defaultdict(list)
    descriptivo: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    presentes = 0
    for tarea, agente, estrategia, n in comprometidas:
        archivo = corridas / nombre / tarea / f"{agente}__{estrategia}__{n}.diff"
        if not archivo.is_file():
            continue
        presentes += 1
        fuente = fuente_diff(archivo.read_text(encoding="utf-8", errors="replace"))
        for r in verificar(fuente, aplica | decisivas[tarea], tipo, extra):
            if not r.verificable:
                continue
            descriptivo[(r.regla, agente)][0] += r.violaciones
            descriptivo[(r.regla, agente)][1] += r.oportunidades
            if r.regla in decisivas[tarea]:
                por_regla[r.regla].append(Observacion(f"{tarea}/{estrategia}", agente, r.oportunidades, r.violaciones))
    agentes = sorted({a for t in tareas for a in como_lista(t.get("agentes"))})
    completo = bool(comprometidas) and presentes == len(comprometidas)
    md = [f"### Decisión de {nombre}", "", f"Corridas: {presentes} de {len(comprometidas)} pre-registradas.", ""]
    datos: dict[str, object] = {
        "proyecto": nombre, "corridas": presentes, "comprometidas": len(comprometidas),
        "alfa": alfa, "completo": completo,
    }
    por_estrato = [como_entero(t.get("repeticiones"), 0) for t in tareas for _ in como_lista(t.get("estrategias"))]
    repartos, minima = resolucion(por_estrato, muestras) if por_estrato and all(por_estrato) else (0, 1.0)
    md += [
        f"Diseño: {len(por_estrato)} estratos (tarea y estrategia), {repartos} repartos posibles por regla y par de "
        f"agentes; p mínima alcanzable {minima:.2g} (alfa {alfa:g}).",
    ]
    if minima > alfa:
        md.append("Con este diseño no puede haber veredicto: hacen falta más tareas o repeticiones.")
    datos.update({"repartos": repartos, "p_minima": minima})
    if not completo:
        md += ["", "El veredicto se calcula cuando estén todas: mirar antes infla la falsa alarma."]
        datos["veredicto"] = "incompleto"
        return "\n".join(md) + "\n", datos
    pruebas = contrastar(por_regla, agentes, muestras, semilla)
    estado, indicado = veredicto(pruebas, alfa)
    md += [
        "",
        f"Permutación por tarea y estrategia; Holm entre {sum(p.p is not None for p in pruebas)} prueba(s).",
        "",
        "| regla decisiva | A | B | viol./oport. A | viol./oport. B | tasa A - tasa B | repartos | p | p Holm |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for p in pruebas:
        md.append(
            f"| {p.regla} | {p.a} | {p.b} | {p.conteo_a[0]}/{p.conteo_a[1]} | {p.conteo_b[0]}/{p.conteo_b[1]} | "
            f"{'—' if p.diferencia is None else f'{p.diferencia:+.1%}'} | "
            f"{p.repartos}{'' if p.exacta else ' (muestreados)'} | "
            f"{'—' if p.p is None else f'{p.p:.4f}'} | {'—' if p.p_holm is None else f'{p.p_holm:.4f}'} |"
        )
    md += ["", f"**Veredicto: {estado}{f' `{indicado}`' if indicado else ''}.**", "",
           "| tarea | asignación sin medir | la medición indica | ¿difiere? |", "|---|---|---|---|"]
    filas: list[dict[str, object]] = []
    for t in tareas:
        previa = como_texto(t.get("asignacion_sin_medir"))
        difiere = indicado is not None and indicado != previa
        md.append(f"| {como_texto(t.get('id'))} | {previa or '—'} | {indicado or estado} | {'sí' if difiere else 'no'} |")
        filas.append({"tarea": como_texto(t.get("id")), "asignacion_sin_medir": previa,
                      "indica": indicado, "difiere": difiere})
    md += ["", "Tasas por regla aplicable (descriptivo; no entra en el veredicto):", "",
           "| regla | agente | violaciones/oportunidades | tasa | IC95 (Wilson) |", "|---|---|---|---|---|"]
    tasas: list[dict[str, object]] = []
    for (regla, agente), (v, o) in sorted(descriptivo.items()):
        bajo, alto = wilson(v, o)
        md.append(f"| {regla} | {agente} | {v}/{o} | {(f'{v / o:.1%}' if o else '—')} | {bajo:.0%}–{alto:.0%} |")
        tasas.append({"regla": regla, "agente": agente, "violaciones": v, "oportunidades": o})
    datos.update({"veredicto": estado, "indica": indicado, "pruebas": [p.como_dict() for p in pruebas],
                  "tareas": filas, "tasas": tasas})
    return "\n".join(md) + "\n", datos


def main(argv: list[str] | None = None) -> int:
    """Imprime el informe de decisión de un proyecto y, opcionalmente, su JSON."""
    parser = argparse.ArgumentParser(prog="python -m estudios.decision")
    parser.add_argument("proyecto", type=Path)
    parser.add_argument("--corridas", type=Path, default=Path("corridas"))
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(errors="replace")
    texto, datos = informe(args.proyecto, args.corridas)
    print(texto)
    if args.json:
        args.json.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
