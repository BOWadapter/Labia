"""Tests del validador de manifiestos y del orden pre-registro → corridas (§9)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from estudios.manifiestos import validar_orden, validar_proyecto

RAIZ = Path(__file__).resolve().parent.parent

PROYECTO = """\
nombre = "002-demo"
tipo = "python"
repositorio = "."
commit = ""
[rebanada]
descripcion = "una función con su test"
comando_demo = ""
comando_eval = ""
[reglas]
directorio = ".labia/reglas"
aplica = ["R1", "R7"]
"""
PREREGISTRO = """\
[[tarea]]
id = "t1"
enunciado = "Añade una función doble(x) con su test"
agentes = ["claude_code", "codex"]
estrategias = ["none", "always_on"]
repeticiones = 3
asignacion_sin_medir = "codex"
reglas_decisivas = ["R1", "R2"]
"""


def _git(raiz: Path, *args: str) -> None:
    """git con identidad local, para no depender de la configuración de la máquina."""
    subprocess.run(
        ["git", "-C", str(raiz), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True, capture_output=True,
    )


def _repo(tmp_path: Path) -> Path:
    """Repositorio con el proyecto 002-demo y su pre-registro sin commitear aún."""
    _git(tmp_path, "init", "-q")
    proyecto = tmp_path / "proyectos" / "002-demo"
    proyecto.mkdir(parents=True)
    (proyecto / "proyecto.toml").write_text(PROYECTO, encoding="utf-8")
    (proyecto / "preregistro.toml").write_text(PREREGISTRO, encoding="utf-8")
    return proyecto


def _corrida(tmp_path: Path) -> None:
    """Añade una corrida al proyecto."""
    destino = tmp_path / "corridas" / "002-demo" / "t1"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "codex__none__1.diff").write_text("", encoding="utf-8")


def test_plantilla_del_repo_es_valida() -> None:
    """La plantilla que se copia para proyectos nuevos pasa el validador."""
    assert validar_proyecto(RAIZ / "proyectos" / "_plantilla") == []


def test_clave_mal_escrita_se_rechaza_con_sugerencia(tmp_path: Path) -> None:
    """Una errata en el pre-registro no pasa en silencio: se nombra la clave correcta."""
    proyecto = _repo(tmp_path)
    texto = PREREGISTRO.replace("asignacion_sin_medir", "asignacion_sin_medi")
    (proyecto / "preregistro.toml").write_text(texto, encoding="utf-8")
    errores = validar_proyecto(proyecto)
    assert any("¿quisiste decir 'asignacion_sin_medir'?" in e for e in errores)


def test_asignacion_debe_ser_uno_de_los_agentes(tmp_path: Path) -> None:
    """La asignación pre-registrada tiene que ser un agente de la tarea."""
    proyecto = _repo(tmp_path)
    texto = PREREGISTRO.replace('asignacion_sin_medir = "codex"', 'asignacion_sin_medir = "gemini"')
    (proyecto / "preregistro.toml").write_text(texto, encoding="utf-8")
    assert any("asignacion_sin_medir" in e for e in validar_proyecto(proyecto))


def test_preregistro_antes_de_la_corrida_es_valido(tmp_path: Path) -> None:
    """Pre-registro en un commit y corrida en uno posterior: válido."""
    proyecto = _repo(tmp_path)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "docs: pre-registro")
    _corrida(tmp_path)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "test: corrida")
    assert validar_orden(tmp_path, proyecto, tmp_path / "corridas") == []


def test_preregistro_en_el_mismo_commit_que_la_corrida_no_vale(tmp_path: Path) -> None:
    """Pre-registrar junto con la corrida no es pre-registrar."""
    proyecto = _repo(tmp_path)
    _corrida(tmp_path)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "feat: todo junto")
    assert validar_orden(tmp_path, proyecto, tmp_path / "corridas") != []


def test_preregistro_cambiado_despues_de_la_corrida_no_vale(tmp_path: Path) -> None:
    """Corregir la asignación después de ver la corrida se detecta en el historial."""
    proyecto = _repo(tmp_path)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "docs: pre-registro")
    _corrida(tmp_path)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "test: corrida")
    texto = PREREGISTRO.replace('asignacion_sin_medir = "codex"', 'asignacion_sin_medir = "claude_code"')
    (proyecto / "preregistro.toml").write_text(texto, encoding="utf-8")
    _git(tmp_path, "commit", "-qam", "docs: ajuste")
    errores = validar_orden(tmp_path, proyecto, tmp_path / "corridas")
    assert len(errores) == 1 and "no es anterior" in errores[0]


def test_corridas_sin_preregistro_commiteado(tmp_path: Path) -> None:
    """Corridas commiteadas sin pre-registro en el historial: error."""
    proyecto = _repo(tmp_path)
    (proyecto / "preregistro.toml").unlink()
    _corrida(tmp_path)
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "test: corrida")
    assert any("sin pre-registro" in e for e in validar_orden(tmp_path, proyecto, tmp_path / "corridas"))
