"""Tests del corredor con un agente de mentira: qué se registra, qué no, y qué recibe el agente."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from estudios.corrida import main
from estudios.tabla import leer_directorio

AGENTE_FALSO = '''\
"""Agente de mentira: lee el enunciado por stdin y edita según el archivo de reglas que encuentre."""
import json
import os
import pathlib
import sys
import time

enunciado = sys.stdin.read().strip()
modo = os.environ.get("AGENTE_FALSO", "editar")
if modo == "fallar":
    print("sin credenciales", file=sys.stderr)
    sys.exit(3)
if modo == "error":
    print(json.dumps({"type": "error", "error": {"message": "Model unavailable"}}))
    sys.exit(0)
if modo == "dormir":
    time.sleep(120)
if modo != "nada":
    reglas = "".join(
        pathlib.Path(n).read_text(encoding="utf-8") for n in ("AGENTS.md", "CLAUDE.md") if pathlib.Path(n).exists()
    )
    marca = "# labia-contexto-ok\\n" if "labia-contexto-ok" in reglas else ""
    firma = "def suma(a: int, b: int) -> int:" if reglas else "def suma(a, b):"
    pathlib.Path("hola.py").write_text(f"{marca}# {enunciado}\\n{firma}\\n    return a + b\\n", encoding="utf-8")
print(json.dumps({"type": "result", "is_error": False, "num_turns": 2, "total_cost_usd": 0.01,
                  "modelUsage": {sys.argv[1]: {}}, "permission_denials": [],
                  "session_id": "secreto", "cwd": os.getcwd()}))
'''
PROYECTO = """\
nombre = "001-demo"
tipo = "python"
repositorio = {repositorio}
commit = ""
[rebanada]
descripcion = "una función"
comando_demo = ""
comando_eval = ""
[reglas]
directorio = "reglas"
aplica = ["R1", "R7"]
"""
PREREGISTRO = """\
[[tarea]]
id = "t1"
enunciado = "Crea hola.py con la funcion suma"
agentes = ["falso_a", "falso_b"]
estrategias = ["none", "always_on"]
repeticiones = 1
asignacion_sin_medir = "falso_a"
reglas_decisivas = ["R1"]

[agente.falso_a]
comando = [{python}, {guion}, "{{modelo}}"]
modelo = "modelo-a"
contexto = "AGENTS.md"

[agente.falso_b]
comando = [{python}, {guion}, "{{modelo}}"]
modelo = "modelo-b"
contexto = "CLAUDE.md"

[ejecucion]
limite_minutos = 1
semilla = 7

[piloto]
enunciado = "Crea hola.py para el piloto"
"""


@dataclass(frozen=True)
class Banco:
    """Lo que un test necesita: el repositorio con el proyecto, el proyecto, las corridas y el hogar."""

    raiz: Path
    proyecto: Path
    corridas: Path
    casa: Path

    def correr(self, *extra: str) -> int:
        """Lanza la batería del proyecto."""
        return main(["correr", str(self.proyecto), "--corridas", str(self.corridas), *extra])

    def reescribir(self, viejo: str, nuevo: str) -> None:
        """Cambia el pre-registro y lo deja commiteado, como exige el corredor."""
        prereg = self.proyecto / "preregistro.toml"
        texto = prereg.read_text(encoding="utf-8")
        assert viejo in texto
        prereg.write_text(texto.replace(viejo, nuevo), encoding="utf-8")
        _git(self.raiz, "commit", "-qam", "docs: ajuste del pre-registro")


def _git(raiz: Path, *args: str) -> None:
    """git con identidad local, para no depender de la configuración de la máquina."""
    subprocess.run(
        ["git", "-C", str(raiz), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True, capture_output=True,
    )


@pytest.fixture
def banco(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Banco:
    """Un repositorio de partida, un proyecto que lo usa con dos agentes de mentira, y un hogar vacío."""
    casa = tmp_path / "casa"
    casa.mkdir()
    for variable in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(variable, str(casa))
    monkeypatch.delenv("LABIA_HOME", raising=False)
    monkeypatch.delenv("AGENTE_FALSO", raising=False)
    origen = tmp_path / "origen"
    (origen / "app").mkdir(parents=True)
    (origen / "app" / "m.py").write_text("def uno() -> int:\n    return 1\n", encoding="utf-8")
    _git(origen, "init", "-q")
    _git(origen, "add", "-A")
    _git(origen, "commit", "-qm", "feat: partida")
    guion = tmp_path / "agente_falso.py"
    guion.write_text(AGENTE_FALSO, encoding="utf-8")
    raiz = tmp_path / "labia"
    proyecto = raiz / "proyectos" / "001-demo"
    proyecto.mkdir(parents=True)
    (proyecto / "proyecto.toml").write_text(PROYECTO.format(repositorio=json.dumps(str(origen))), encoding="utf-8")
    (proyecto / "preregistro.toml").write_text(
        PREREGISTRO.format(python=json.dumps(sys.executable), guion=json.dumps(str(guion))), encoding="utf-8"
    )
    (proyecto / "AGENTS.md").write_text("# Reglas\n\nType hints en todo.\n", encoding="utf-8")
    _git(raiz, "init", "-q")
    _git(raiz, "add", "-A")
    _git(raiz, "commit", "-qm", "docs: pre-registro")
    return Banco(raiz, proyecto, raiz / "corridas", casa)


def test_probar_distingue_agente_sin_cambios_y_fallo(
    banco: Banco, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """La prueba de arranque dice quién falló: el agente que edita, el que no hace nada, el que no arranca."""
    assert main(["probar", str(banco.proyecto), "falso_a"]) == 0
    salida = capsys.readouterr().out
    assert "AGENTE" in salida and "LEÍDO — AGENTS.md" in salida
    esperado = {"nada": "SIN CAMBIOS", "fallar": "sin credenciales", "error": "Model unavailable"}
    for modo, texto in esperado.items():
        monkeypatch.setenv("AGENTE_FALSO", modo)
        assert main(["probar", str(banco.proyecto), "falso_a"]) == 1
        assert texto in capsys.readouterr().out


def test_probar_avisa_si_el_archivo_de_reglas_no_llega(banco: Banco, capsys: pytest.CaptureFixture[str]) -> None:
    """Si el agente no lee el archivo con el nombre declarado, always_on no entregaría nada: se dice."""
    banco.reescribir('contexto = "AGENTS.md"', 'contexto = "OTRO.md"')
    assert main(["probar", str(banco.proyecto), "falso_a"]) == 1
    assert "NO LEÍDO" in capsys.readouterr().out


def test_correr_guarda_diff_y_metadatos_y_continua_donde_quedo(
    banco: Banco, capsys: pytest.CaptureFixture[str]
) -> None:
    """Cada corrida deja su diff y sus metadatos con la convención; relanzar sólo hace lo que falta."""
    assert banco.correr("--max", "1") == 0
    assert len(list(banco.corridas.rglob("*.diff"))) == 1
    assert banco.correr() == 0
    carpeta = banco.corridas / "001-demo" / "t1"
    assert sorted(p.name for p in carpeta.glob("*.diff")) == [
        "falso_a__always_on__1.diff", "falso_a__none__1.diff",
        "falso_b__always_on__1.diff", "falso_b__none__1.diff",
    ]
    con_reglas = (carpeta / "falso_b__always_on__1.diff").read_text(encoding="utf-8")
    sin_reglas = (carpeta / "falso_b__none__1.diff").read_text(encoding="utf-8")
    assert "+def suma(a: int, b: int) -> int:" in con_reglas  # recibió las reglas con el nombre que lee
    assert "CLAUDE.md" not in con_reglas  # y el archivo entregado no es parte de lo que hizo
    assert "+def suma(a, b):" in sin_reglas
    assert "Crea hola.py con la funcion suma" in con_reglas  # el enunciado llegó por stdin
    crudo = (carpeta / "falso_b__always_on__1.json").read_text(encoding="utf-8")
    metadatos = json.loads(crudo)
    assert (metadatos["modelo"], metadatos["termino"], metadatos["estrategia"]) == ("modelo-b", "ok", "always_on")
    assert metadatos["reportado"]["num_turns"] == 2 and metadatos["reportado"]["modelos"] == ["modelo-b"]
    assert "secreto" not in crudo and banco.casa.name not in crudo and "trabajo" not in crudo
    assert len(leer_directorio(banco.corridas)) == 4  # la tabla los lee sin cambios
    capsys.readouterr()
    assert banco.correr() == 0
    assert "batería completa" in capsys.readouterr().out
    assert not list((banco.casa / ".labia" / "trabajo").iterdir())  # no deja clones


def test_simular_lista_sin_lanzar_agentes(banco: Banco, capsys: pytest.CaptureFixture[str]) -> None:
    """--simular enseña el plan y no escribe nada."""
    assert banco.correr("--simular") == 0
    assert capsys.readouterr().out.count("modelo-") == 4
    assert not banco.corridas.exists()


def test_fallo_de_infraestructura_no_se_registra(
    banco: Banco, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Un agente que no llega a trabajar no deja corrida: registrar su diff vacío sesgaría la tabla."""
    for modo in ("fallar", "error"):
        monkeypatch.setenv("AGENTE_FALSO", modo)
        assert banco.correr() == 2
        assert not list(banco.corridas.rglob("*.*"))
    assert "continúa donde quedó" in capsys.readouterr().err


def test_limite_de_tiempo_se_registra_marcado(banco: Banco, monkeypatch: pytest.MonkeyPatch) -> None:
    """Agotar el límite corta al agente y a sus procesos, y la corrida queda registrada como tal."""
    banco.reescribir("limite_minutos = 1", "limite_minutos = 0.02")
    monkeypatch.setenv("AGENTE_FALSO", "dormir")
    inicio = time.monotonic()
    assert banco.correr("--max", "1") == 0
    assert time.monotonic() - inicio < 60
    (metadatos,) = banco.corridas.rglob("*.json")
    assert json.loads(metadatos.read_text(encoding="utf-8"))["termino"] == "limite_de_tiempo"
    assert metadatos.with_suffix(".diff").read_text(encoding="utf-8") == ""


def test_correr_exige_preregistro_fijo_y_valido(banco: Banco, capsys: pytest.CaptureFixture[str]) -> None:
    """La batería no empieza con el pre-registro sin commit ni con errores del validador."""
    prereg = banco.proyecto / "preregistro.toml"
    prereg.write_text(prereg.read_text(encoding="utf-8") + "\n# nota\n", encoding="utf-8")
    assert banco.correr() == 1
    assert "sin commit" in capsys.readouterr().err
    banco.reescribir('asignacion_sin_medir = "falso_a"', 'asignacion_sin_medir = ""')
    assert banco.correr() == 1
    assert "asignacion_sin_medir" in capsys.readouterr().err
    assert not banco.corridas.exists()


def test_contexto_ajeno_detiene_la_bateria_salvo_que_se_anote(
    banco: Banco, capsys: pytest.CaptureFixture[str]
) -> None:
    """Un archivo de instrucciones global llega también a las corridas none: se exige apartarlo o anotarlo."""
    (banco.casa / ".claude").mkdir()
    (banco.casa / ".claude" / "CLAUDE.md").write_text("Responde siempre en verso.\n", encoding="utf-8")
    assert banco.correr("--max", "1") == 1
    assert "--con-contexto-ajeno" in capsys.readouterr().err
    assert banco.correr("--max", "1", "--con-contexto-ajeno") == 0
    (metadatos,) = banco.corridas.rglob("*.json")
    assert json.loads(metadatos.read_text(encoding="utf-8"))["contexto_ajeno"] == ["~/.claude/CLAUDE.md"]


def test_piloto_mide_sin_registrar(banco: Banco, capsys: pytest.CaptureFixture[str]) -> None:
    """El piloto corre sobre el repositorio real, enseña las reglas aplicables y no toca corridas/."""
    assert main(["piloto", str(banco.proyecto), "falso_a"]) == 0
    salida = capsys.readouterr().out
    assert "R1" in salida and "0/1 violaciones/oportunidades" in salida
    assert not banco.corridas.exists()
    assert len(list((banco.casa / ".labia" / "pilotos" / "001-demo").glob("falso_a-*.diff"))) == 1


def test_agente_no_declarado_o_ausente_se_explica(banco: Banco, capsys: pytest.CaptureFixture[str]) -> None:
    """Pedir un agente que el pre-registro no declara, o cuyo programa no existe, da un mensaje y no una traza."""
    assert main(["probar", str(banco.proyecto), "otro"]) == 1
    assert "[agente.otro]" in capsys.readouterr().err
    banco.reescribir(json.dumps(sys.executable), '"programa-que-no-existe"')
    assert main(["probar", str(banco.proyecto), "falso_a"]) == 1
    assert "PATH" in capsys.readouterr().err
    assert banco.correr() == 1
    assert "programa-que-no-existe" in capsys.readouterr().err
