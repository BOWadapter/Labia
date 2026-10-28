"""Tests de la tabla de corridas: convención de nombres y contraste con intervalo."""

from __future__ import annotations

from pathlib import Path

import pytest

from estudios.tabla import leer_directorio, tabla

CON_TIPOS = (
    "diff --git a/app/m.py b/app/m.py\n--- /dev/null\n+++ b/app/m.py\n@@ -0,0 +1,3 @@\n"
    '+def f(a: int) -> int:\n+    """Doble."""\n+    return a * 2\n'
)
SIN_TIPOS = (
    "diff --git a/app/m.py b/app/m.py\n--- /dev/null\n+++ b/app/m.py\n@@ -0,0 +1,2 @@\n"
    "+def f(a):\n+    return a * 2\n"
)


def _escribir(raiz: Path, tarea: str, nombre: str, diff: str) -> None:
    """Escribe un diff de corrida con la convención del directorio."""
    destino = raiz / "001-demo" / tarea
    destino.mkdir(parents=True, exist_ok=True)
    (destino / nombre).write_text(diff, encoding="utf-8")


def test_tabla_desde_directorio_con_contraste(tmp_path: Path) -> None:
    """La tabla lee la convención y calcula el contraste frente a none."""
    for tarea in ("t1", "t2"):
        _escribir(tmp_path, tarea, "agente-a__none__1.diff", SIN_TIPOS)
        _escribir(tmp_path, tarea, "agente-a__always_on__1.diff", CON_TIPOS)
    corridas = leer_directorio(tmp_path)
    assert len(corridas) == 4
    texto, filas = tabla(corridas, "demo")
    r1_none = next(f for f in filas if f.get("estrategia") == "none" and f["regla"] == "R1")
    assert (r1_none["violaciones"], r1_none["oportunidades"]) == (2, 2)
    contraste = next(f for f in filas if f.get("contraste") == "always_on-none" and f["regla"] == "R1")
    assert contraste["delta"] == pytest.approx(-1.0)
    assert "always_on − none" in texto


def test_nombre_fuera_de_convencion_falla(tmp_path: Path) -> None:
    """Un diff sin agente__estrategia__n se rechaza en vez de contarse mal."""
    _escribir(tmp_path, "t1", "corrida.diff", CON_TIPOS)
    with pytest.raises(ValueError):
        leer_directorio(tmp_path)
