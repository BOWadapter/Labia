"""Tests del control negativo y la potencia: sin efecto no se declara nada; con efecto total, siempre."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from estudios.contexto_2607_27250 import leer
from estudios.potencia import celdas, efecto, main, nulo, simular

CON_TIPOS = (
    "diff --git a/app/m.py b/app/m.py\n--- /dev/null\n+++ b/app/m.py\n@@ -0,0 +1,3 @@\n"
    '+def f(a: int) -> int:\n+    """Doble."""\n+    return a * 2\n'
)
SIN_TIPOS = (
    "diff --git a/app/m.py b/app/m.py\n--- /dev/null\n+++ b/app/m.py\n@@ -0,0 +1,2 @@\n"
    "+def f(a):\n+    return a * 2\n"
)


def _db(tmp_path: Path) -> Path:
    """Base con el esquema del estudio público: un agente siempre anota tipos y el otro nunca."""
    ruta = tmp_path / "corridas.db"
    con = sqlite3.connect(ruta)
    con.execute("create table runs (task_id text, repo text, agent text, strategy text, final_diff text)")
    for tarea in ("t1", "t2", "t3"):
        for agente, diff in (("claude_code", CON_TIPOS), ("codex", SIN_TIPOS)):
            for estrategia in ("none", "always_on"):
                for _ in range(3):
                    con.execute("insert into runs values (?, ?, ?, ?, ?)", (tarea, "repo", agente, estrategia, diff))
    con.commit()
    con.close()
    return ruta


def test_sin_efecto_no_se_declara_y_con_efecto_total_siempre(tmp_path: Path) -> None:
    """Las dos reglas callan cuando los grupos son idénticos y hablan cuando no comparten nada."""
    datos = celdas([corrida for _, corrida in leer(_db(tmp_path))])
    assert simular(*nulo(datos, "codex", 3), tareas=3, simulaciones=5, semilla=1) == (0.0, 0.0)
    assert simular(*efecto(datos, 3), tareas=3, simulaciones=5, semilla=1) == (1.0, 1.0)


def test_un_diseno_mas_grande_que_los_datos_no_se_inventa(tmp_path: Path) -> None:
    """Pedir más tareas de las que hay no devuelve una cifra."""
    datos = celdas([corrida for _, corrida in leer(_db(tmp_path))])
    assert simular(*efecto(datos, 3), tareas=12, simulaciones=5, semilla=1) is None


def test_informe_por_cli(tmp_path: Path) -> None:
    """La CLI escribe una fila por escenario y diseño, y deja vacías las que no puede simular."""
    salida = tmp_path / "potencia.json"
    assert main([str(_db(tmp_path)), "--sims", "2", "--json", str(salida)]) == 0
    filas = json.loads(salida.read_text(encoding="utf-8"))["filas"]
    assert len(filas) == 9
    assert [fila["permutacion"] for fila in filas if fila["tareas"] == 12] == [None, None, None]
