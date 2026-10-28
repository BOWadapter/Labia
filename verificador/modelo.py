"""Tipos del verificador: fuente normalizada, resultado por regla y regla registrable."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Funcion:
    """Una definición de función encontrada en el código que se verifica.

    ``anotada`` vale None cuando la firma no pudo evaluarse (por ejemplo, un diff
    que cambia sólo parte de una firma multilínea). ``docstring_evaluable`` es
    False cuando el cuerpo de la función no está a la vista.
    """

    archivo: str
    linea: int
    nombre: str
    es_test: bool
    anotada: bool | None
    docstring: str | None
    docstring_evaluable: bool


@dataclass(frozen=True)
class Fuente:
    """Vista normalizada de lo que se verifica: un árbol de archivos o un diff.

    ``textos`` sólo se llena en modo directorio; las reglas que necesitan el
    archivo completo se declaran no verificables en modo diff.
    """

    modo: str
    textos: Mapping[str, str]
    rutas: tuple[str, ...]
    funciones: tuple[Funcion, ...]
    stdout: str | None = None
    commits: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Resultado:
    """Resultado de una regla. La tasa es violaciones sobre oportunidades, nunca un conteo."""

    regla: str
    nombre: str
    verificable: bool
    oportunidades: int
    violaciones: int
    detalle: tuple[str, ...] = ()
    nota: str = ""

    @property
    def tasa(self) -> float | None:
        """Devuelve la tasa de violación, o None si no hay oportunidades o no es verificable."""
        if not self.verificable or self.oportunidades == 0:
            return None
        return self.violaciones / self.oportunidades

    def como_dict(self) -> dict[str, object]:
        """Serializa el resultado para el informe JSON."""
        return {
            "regla": self.regla,
            "nombre": self.nombre,
            "verificable": self.verificable,
            "oportunidades": self.oportunidades,
            "violaciones": self.violaciones,
            "tasa": self.tasa,
            "detalle": list(self.detalle),
            "nota": self.nota,
        }


@dataclass(frozen=True)
class Caso:
    """Caso de referencia que una regla debe discriminar; el meta-test lo exige.

    Para reglas mecánicas, ``viola`` indica si el caso debe producir violaciones.
    Para reglas de revisión humana, indica si debe producir sitios a revisar.
    """

    descripcion: str
    archivos: Mapping[str, str]
    viola: bool
    stdout: str | None = None
    commits: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Regla:
    """Una regla registrable. Añadir una regla es añadir un módulo con ``REGLA``."""

    id: str
    nombre: str
    evaluar: Callable[[Fuente], Resultado]
    casos: tuple[Caso, ...]
    mecanica: bool = True
    tipo: str = "python"
