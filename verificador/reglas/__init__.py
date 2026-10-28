"""Registro de reglas. Cada módulo de este paquete que exponga ``REGLA`` queda registrado.

Contribuir una regla = añadir un módulo con ``REGLA = Regla(...)`` y al menos un caso
que la cumple y otro que la viola. ``tests/test_verificador.py`` rechaza la regla si
sus casos no la discriminan.

Un proyecto puede traer reglas propias en un directorio (por ejemplo
``.labia/reglas/``) y cargarlas con ``cargar(extra=ruta)``. Son código del proyecto:
se ejecutan con los permisos de quien corre el verificador.
"""

from __future__ import annotations

import importlib
import importlib.util
import pkgutil
import re
from pathlib import Path

from ..modelo import Regla


def _orden(regla: Regla) -> tuple[str, int, str]:
    """Orden natural: R2 antes que R10, agrupado por prefijo."""
    prefijo = re.sub(r"\d+$", "", regla.id)
    numero = re.search(r"(\d+)$", regla.id)
    return (prefijo, int(numero.group(1)) if numero else 0, regla.id)


def _de_directorio(directorio: Path) -> list[Regla]:
    """Carga reglas desde archivos .py de un directorio de proyecto."""
    reglas: list[Regla] = []
    for archivo in sorted(directorio.glob("*.py")):
        if archivo.name.startswith("_"):
            continue
        especificacion = importlib.util.spec_from_file_location(f"reglas_proyecto.{archivo.stem}", archivo)
        if especificacion is None or especificacion.loader is None:
            continue
        modulo = importlib.util.module_from_spec(especificacion)
        especificacion.loader.exec_module(modulo)
        regla = getattr(modulo, "REGLA", None)
        if isinstance(regla, Regla):
            reglas.append(regla)
    return reglas


def cargar(tipo: str | None = None, extra: Path | None = None) -> tuple[Regla, ...]:
    """Devuelve las reglas registradas del tipo dado, más las del directorio ``extra``."""
    reglas: list[Regla] = []
    for info in pkgutil.iter_modules(__path__):
        modulo = importlib.import_module(f"{__name__}.{info.name}")
        regla = getattr(modulo, "REGLA", None)
        if isinstance(regla, Regla):
            reglas.append(regla)
    if extra is not None:
        reglas.extend(_de_directorio(extra))
    reglas = [r for r in reglas if tipo is None or r.tipo in (tipo, "cualquiera")]
    ids = [r.id for r in reglas]
    repetidos = sorted({i for i in ids if ids.count(i) > 1})
    if repetidos:
        raise ValueError(f"ids de regla repetidos: {repetidos}")
    return tuple(sorted(reglas, key=_orden))
