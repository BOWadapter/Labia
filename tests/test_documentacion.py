"""La documentación no puede citar comandos que no existen: la falla raíz de v1–v3 fue
documentos que se desfasaron del código. Cada ``python -m`` citado en un .md se comprueba.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from verificador.__main__ import SUBCOMANDOS

RAIZ = Path(__file__).resolve().parent.parent
DOCUMENTOS = sorted(
    p for p in RAIZ.rglob("*.md")
    if not any(parte.startswith(".") or parte in ("venv", "build", "dist") for parte in p.relative_to(RAIZ).parts)
)
_COMANDO = re.compile(r"python -m ([A-Za-z_][\w.]*)(?:[ \t]+([a-z]+))?")
_EXTERNOS = frozenset({"pytest", "mypy", "pip", "venv", "pre_commit"})


def test_hay_documentos_que_revisar() -> None:
    """El barrido encuentra los documentos principales."""
    nombres = {p.name for p in DOCUMENTOS}
    assert {"README.md", "CONTRIBUTING.md", "AGENTS.md", "PROMPT-MAESTRO.md"} <= nombres


@pytest.mark.parametrize("subcomando", SUBCOMANDOS)
def test_subcomandos_declarados_existen_en_la_cli(subcomando: str) -> None:
    """SUBCOMANDOS no puede divergir de la CLI real: cada uno responde a --help."""
    from verificador.__main__ import main

    with pytest.raises(SystemExit) as salida:
        main([subcomando, "--help"])
    assert salida.value.code == 0


@pytest.mark.parametrize("documento", DOCUMENTOS, ids=[p.relative_to(RAIZ).as_posix() for p in DOCUMENTOS])
def test_comandos_citados_existen(documento: Path) -> None:
    """Todo ``python -m modulo [subcomando]`` citado existe en este repositorio."""
    for modulo, subcomando in _COMANDO.findall(documento.read_text(encoding="utf-8")):
        if modulo in _EXTERNOS:
            continue
        assert importlib.util.find_spec(modulo) is not None, f"{documento.name}: no existe python -m {modulo}"
        if modulo == "verificador" and subcomando:
            assert subcomando in SUBCOMANDOS, f"{documento.name}: verificador no tiene '{subcomando}'"


def test_version_del_paquete_coincide_con_pyproject() -> None:
    """Una sola versión: la del pyproject y la que reporta el verificador en sus informes."""
    import tomllib

    import verificador

    proyecto = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    assert proyecto["project"]["version"] == verificador.__version__
