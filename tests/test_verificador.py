"""Tests del verificador: sin red, sin claves, deterministas.

El meta-test ``test_cada_regla_discrimina_sus_casos`` es la compuerta de contribución:
una regla nueva sin un caso que la cumpla y otro que la viole no entra.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from verificador import (
    Caso, Regla, Resultado, cargar, comprobar_casos, fuente_diff, fuente_directorio, verificar, wilson,
)

REGLAS = cargar()


def test_registro_tiene_las_siete_reglas_con_ids_unicos() -> None:
    """Las siete reglas de §6.2 están registradas una sola vez."""
    ids = [r.id for r in REGLAS]
    assert ids[:7] == ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("regla", REGLAS, ids=[r.id for r in REGLAS])
def test_cada_regla_discrimina_sus_casos(regla: Regla) -> None:
    """Compuerta de contribución: cada regla trae casos que cumplen y que violan, y los separa."""
    assert comprobar_casos(regla) == []


def test_plantilla_de_regla_de_proyecto_carga_y_discrimina() -> None:
    """La plantilla de proyectos/ se carga como regla externa y pasa la misma compuerta."""
    directorio = Path(__file__).resolve().parent.parent / "proyectos" / "_plantilla" / "reglas"
    reglas = cargar("typescript", extra=directorio)
    assert [r.id for r in reglas] == ["P1", "R3", "R6"]
    assert all(comprobar_casos(r) == [] for r in reglas)


def test_regla_que_no_discrimina_es_rechazada() -> None:
    """Una regla que nunca reporta violaciones no pasa la compuerta."""
    nula = Regla(
        id="X1",
        nombre="nula",
        evaluar=lambda f: Resultado("X1", "nula", True, 1, 0),
        casos=(Caso("cumple", {}, False), Caso("viola", {}, True)),
    )
    assert comprobar_casos(nula) == ["X1: no detecta 'viola'"]


DIFF = """\
diff --git a/pkg/mod.py b/pkg/mod.py
--- a/pkg/mod.py
+++ b/pkg/mod.py
@@ -1,3 +1,13 @@
 import os
+
+def anotada(a: int,
+            b: str = "x") -> int:
+    \"\"\"Devuelve la suma de longitudes.\"\"\"
+    return a + len(b)
+
+def sin_tipos(a, b):
+    return a
+
+def una_linea(x: int) -> int: return x
 VALOR = 1
-OTRO = 2
+-- no es cabecera aunque empiece con guiones
"""


def test_diff_extrae_firmas_multilinea_y_docstrings() -> None:
    """El parser de diff reconstruye firmas multilínea y detecta docstrings."""
    fuente = fuente_diff(DIFF)
    por_nombre = {f.nombre: f for f in fuente.funciones}
    assert set(por_nombre) == {"anotada", "sin_tipos", "una_linea"}
    assert por_nombre["anotada"].anotada is True
    assert por_nombre["anotada"].docstring == "Devuelve la suma de longitudes."
    assert por_nombre["sin_tipos"].anotada is False
    assert por_nombre["sin_tipos"].docstring is None
    assert por_nombre["una_linea"].docstring_evaluable is True
    assert fuente.rutas == ("pkg/mod.py",)


def test_diff_r7_exige_tocar_tests() -> None:
    """Un diff que toca código sin tocar tests viola R7; con test, cumple."""
    sin_test = {r.regla: r for r in verificar(fuente_diff(DIFF))}["R7"]
    assert (sin_test.oportunidades, sin_test.violaciones) == (1, 1)
    con_test = DIFF + (
        "diff --git a/tests/test_mod.py b/tests/test_mod.py\n"
        "--- /dev/null\n+++ b/tests/test_mod.py\n@@ -0,0 +1 @@\n+def test_x() -> None: ...\n"
    )
    resultado = {r.regla: r for r in verificar(fuente_diff(con_test))}["R7"]
    assert resultado.violaciones == 0


def test_reglas_de_arbol_completo_no_son_verificables_en_diff() -> None:
    """R4 y R5 necesitan el archivo completo: en modo diff se declaran no verificables."""
    resultados = {r.regla: r for r in verificar(fuente_diff(DIFF))}
    assert not resultados["R4"].verificable
    assert not resultados["R5"].verificable
    assert resultados["R5"].tasa is None


def test_directorio_ignora_entornos(tmp_path: Path) -> None:
    """fuente_directorio no lee .venv ni __pycache__."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "x.py").write_text("def f(a): return a\n", encoding="utf-8")
    (tmp_path / ".venv" / "lib").mkdir(parents=True)
    (tmp_path / ".venv" / "lib" / "y.py").write_text("def g(a): return a\n", encoding="utf-8")
    fuente = fuente_directorio(tmp_path)
    assert [f.nombre for f in fuente.funciones] == ["f"]


def test_wilson_acota_y_se_ensancha_con_n_chico() -> None:
    """El intervalo contiene la tasa y es más ancho con menos oportunidades."""
    bajo, alto = wilson(3, 12)
    assert bajo < 3 / 12 < alto
    assert (alto - bajo) > (lambda i: i[1] - i[0])(wilson(30, 120))
    assert wilson(0, 0) == (0.0, 1.0)


def test_cli_lista_reglas_en_json() -> None:
    """``python -m verificador reglas`` emite JSON válido con las reglas registradas."""
    salida = subprocess.run(
        [sys.executable, "-m", "verificador", "reglas"], check=True, capture_output=True, text=True
    ).stdout
    assert [r["id"] for r in json.loads(salida)][:7] == ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]
