"""P2 — Un hiperparámetro nuevo es campo en config/post_training_config.py y clave en configs/*.json.

Convención declarada en el CONTRIBUTING de train-llm-from-scratch. Sólo es decidible sobre
un diff: "nuevo" existe respecto de un commit base.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from verificador import Caso, Fuente, Regla, Resultado

NOMBRE = "Hiperparámetro nuevo = campo + clave JSON"
ARCHIVO_CONFIG = "config/post_training_config.py"
_CAMPO = re.compile(r"^ {4}(?P<nombre>[a-z_][a-z0-9_]*)\s*:\s*[^=\n]+=")
_CLAVE = re.compile(r'"(?P<nombre>[A-Za-z_][A-Za-z0-9_]*)"\s*:')


def evaluar(fuente: Fuente) -> Resultado:
    """Cada campo añadido a las dataclasses de configuración necesita su clave en un JSON."""
    if fuente.modo != "diff":
        return Resultado("P2", NOMBRE, False, 0, 0, nota="Requiere un diff contra el commit base.")
    campos = [
        m.group("nombre")
        for linea in fuente.textos.get(ARCHIVO_CONFIG, "").splitlines()
        if (m := _CAMPO.match(linea)) is not None
    ]
    claves = {
        m.group("nombre")
        for ruta, texto in fuente.textos.items()
        if PurePosixPath(ruta).parts[:1] == ("configs",) and ruta.endswith(".json")
        for m in _CLAVE.finditer(texto)
    }
    sin_clave = [c for c in campos if c not in claves]
    return Resultado(
        regla="P2",
        nombre=NOMBRE,
        verificable=True,
        oportunidades=len(campos),
        violaciones=len(sin_clave),
        detalle=tuple(sin_clave),
        nota="Oportunidad = campo añadido en una dataclass de configuración.",
    )


_CONFIG = """\
diff --git a/config/post_training_config.py b/config/post_training_config.py
--- a/config/post_training_config.py
+++ b/config/post_training_config.py
@@ -10,2 +10,3 @@ class SFTConfig(BaseModelConfig):
     lr: float = 1e-5
+    label_smoothing: float = 0.0
     min_lr: float = 1e-6
"""
_JSON = """\
diff --git a/configs/sft.json b/configs/sft.json
--- a/configs/sft.json
+++ b/configs/sft.json
@@ -2,2 +2,3 @@
   "lr": 1e-05,
+  "label_smoothing": 0.0,
   "min_lr": 1e-06,
"""

REGLA = Regla(
    id="P2",
    nombre=NOMBRE,
    evaluar=evaluar,
    casos=(
        Caso("campo y clave", {}, False, diff=_CONFIG + _JSON),
        Caso("campo sin clave", {}, True, diff=_CONFIG),
    ),
)
