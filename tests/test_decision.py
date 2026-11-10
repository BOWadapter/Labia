"""Tests de la regla de decisión: permutación por tarea, Holm, veredicto y espera a la batería completa."""

from __future__ import annotations

from pathlib import Path

import pytest

from estudios import decision
from estudios.decision import Observacion, Prueba, holm, informe, permutacion, resolucion, veredicto

CON_TIPOS = (
    "diff --git a/app/m.py b/app/m.py\n--- /dev/null\n+++ b/app/m.py\n@@ -0,0 +1,3 @@\n"
    '+def f(a: int) -> int:\n+    """Doble."""\n+    return a * 2\n'
)
SIN_TIPOS = (
    "diff --git a/app/m.py b/app/m.py\n--- /dev/null\n+++ b/app/m.py\n@@ -0,0 +1,2 @@\n"
    "+def f(a):\n+    return a * 2\n"
)
PROYECTO = """\
nombre = "001-demo"
tipo = "python"
repositorio = "."
commit = ""
[rebanada]
descripcion = "una función"
comando_demo = ""
comando_eval = ""
[reglas]
directorio = "reglas"
aplica = ["R1", "R7"]
"""
TAREA = """\
[[tarea]]
id = "{id}"
enunciado = "Añade una función"
agentes = ["a", "b"]
estrategias = ["always_on"]
repeticiones = 3
asignacion_sin_medir = "b"
reglas_decisivas = ["R1"]
"""


def _corridas(estrato: str, agente: str, violaciones: list[int]) -> list[Observacion]:
    """Corridas de un agente en un estrato, con una oportunidad cada una."""
    return [Observacion(estrato, agente, 1, v) for v in violaciones]


def _proyecto(tmp_path: Path) -> Path:
    """Proyecto con tres tareas, dos agentes y tres repeticiones; pre-registrado para 'b'."""
    proyecto = tmp_path / "proyectos" / "001-demo"
    proyecto.mkdir(parents=True)
    (proyecto / "proyecto.toml").write_text(PROYECTO, encoding="utf-8")
    (proyecto / "preregistro.toml").write_text(
        "\n".join(TAREA.format(id=f"t{n}") for n in (1, 2, 3)), encoding="utf-8"
    )
    return proyecto


def _escribir(corridas: Path, tarea: str, agente: str, n: int, diff: str) -> None:
    """Escribe el diff de una corrida con la convención del directorio."""
    destino = corridas / "001-demo" / tarea
    destino.mkdir(parents=True, exist_ok=True)
    (destino / f"{agente}__always_on__{n}.diff").write_text(diff, encoding="utf-8")


def test_permutacion_exacta_cuenta_los_repartos_al_menos_tan_extremos() -> None:
    """Con cuatro corridas hay seis repartos; dos son tan extremos como el observado."""
    observaciones = _corridas("t1", "a", [1, 1]) + _corridas("t1", "b", [0, 0])
    diferencia, p, repartos, exacta = permutacion(observaciones, "a", "b")
    assert (diferencia, repartos, exacta) == (1.0, 6, True)
    assert p == pytest.approx(2 / 6)


def test_la_permutacion_no_confunde_la_tarea_con_el_agente() -> None:
    """'a' corrió más veces la tarea difícil: su tasa cruda es peor, pero dentro de cada tarea no difiere."""
    observaciones = (
        _corridas("dificil", "a", [1, 1, 1]) + _corridas("dificil", "b", [1])
        + _corridas("facil", "a", [0]) + _corridas("facil", "b", [0, 0, 0])
    )
    diferencia, p, _, _ = permutacion(observaciones, "a", "b")
    assert diferencia == pytest.approx(0.5)
    assert p == 1.0


def test_un_reparto_sin_oportunidades_nunca_ayuda_al_veredicto() -> None:
    """Si un lado puede quedarse sin oportunidades, ese reparto cuenta como extremo; sin ellas no hay p."""
    con_vacias = [Observacion("t1", "a", 1, 1), Observacion("t1", "a", 0, 0),
                  Observacion("t1", "b", 1, 0), Observacion("t1", "b", 0, 0)]
    assert permutacion(con_vacias, "a", "b")[1] == 1.0
    sin_denominador = [Observacion("t1", "a", 1, 1), Observacion("t1", "b", 0, 0)]
    assert permutacion(sin_denominador, "a", "b")[:2] == (None, None)


def test_muestreo_con_semilla_cuando_no_se_pueden_enumerar(monkeypatch: pytest.MonkeyPatch) -> None:
    """Por encima del límite se muestrean repartos; la misma semilla da la misma p."""
    monkeypatch.setattr(decision, "LIMITE_EXACTO", 10)
    observaciones = [
        o for tarea in ("t1", "t2", "t3")
        for o in _corridas(tarea, "a", [0, 0, 0]) + _corridas(tarea, "b", [1, 1, 1])
    ]
    diferencia, p, repartos, exacta = permutacion(observaciones, "a", "b", muestras=2000, semilla=1)
    assert (diferencia, repartos, exacta) == (-1.0, 8000, False)
    assert p is not None and p < 0.01
    assert permutacion(observaciones, "a", "b", muestras=2000, semilla=1)[1] == p


def test_holm_ajusta_en_orden_y_deja_fuera_las_pruebas_sin_p() -> None:
    """La p más chica se multiplica por el número de pruebas; las ajustadas no decrecen."""
    assert holm([0.01, 0.04, None, 0.03]) == [pytest.approx(0.03), pytest.approx(0.06), None, pytest.approx(0.06)]


def test_veredicto_indica_no_distingue_o_se_contradice() -> None:
    """Indica al de menor tasa sólo si es significativo y ninguna otra regla dice lo contrario."""

    def prueba(regla: str, diferencia: float, p: float) -> Prueba:
        return Prueba(regla, "a", "b", (0, 1), (0, 1), diferencia, p, p, 20, True)

    assert veredicto([prueba("R1", -0.4, 0.01)]) == ("indica", "a")
    assert veredicto([prueba("R1", 0.4, 0.01)]) == ("indica", "b")
    assert veredicto([prueba("R1", -0.4, 0.2)]) == ("sin veredicto", None)
    assert veredicto([prueba("R1", -0.4, 0.01), prueba("R2", 0.3, 0.01)]) == ("conflicto", None)


def test_resolucion_dice_si_el_diseno_puede_dar_veredicto() -> None:
    """Una sola tarea con tres repeticiones no puede bajar de 0.05; tres tareas sí."""
    repartos, minima = resolucion([3])
    assert repartos == 20 and minima == pytest.approx(0.1)
    repartos, minima = resolucion([3, 3, 3])
    assert repartos == 8000 and minima < 0.05


def test_informe_espera_la_bateria_completa_y_compara_con_lo_preregistrado(tmp_path: Path) -> None:
    """Sin todas las corridas no hay veredicto; con todas, se contrasta con la asignación sin medir."""
    proyecto, corridas = _proyecto(tmp_path), tmp_path / "corridas"
    for tarea in ("t1", "t2", "t3"):
        for n in (1, 2, 3):
            _escribir(corridas, tarea, "a", n, CON_TIPOS)
            if (tarea, n) != ("t3", 3):
                _escribir(corridas, tarea, "b", n, SIN_TIPOS)
    texto, datos = informe(proyecto, corridas)
    assert datos["veredicto"] == "incompleto" and datos["corridas"] == 17
    assert "17 de 18" in texto and "Veredicto" not in texto
    _escribir(corridas, "t3", "b", 3, SIN_TIPOS)
    texto, datos = informe(proyecto, corridas)
    assert (datos["veredicto"], datos["indica"]) == ("indica", "a")
    assert "Veredicto: indica `a`" in texto
    tareas = datos["tareas"]
    assert isinstance(tareas, list) and all(fila["difiere"] for fila in tareas)


def test_informe_sin_diferencia_no_cambia_la_asignacion(tmp_path: Path) -> None:
    """Si los agentes hacen lo mismo el resultado es 'sin veredicto' y nada difiere de lo pre-registrado."""
    proyecto, corridas = _proyecto(tmp_path), tmp_path / "corridas"
    for tarea in ("t1", "t2", "t3"):
        for n in (1, 2, 3):
            for agente in ("a", "b"):
                _escribir(corridas, tarea, agente, n, SIN_TIPOS)
    _, datos = informe(proyecto, corridas)
    assert datos["veredicto"] == "sin veredicto"
    tareas = datos["tareas"]
    assert isinstance(tareas, list) and not any(fila["difiere"] for fila in tareas)
