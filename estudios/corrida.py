"""Corre agentes de código sobre las tareas pre-registradas de un proyecto y guarda sus diffs.

Cada corrida parte de un clon limpio del repositorio del manifiesto en su commit fijo,
fuera de cualquier árbol que traiga archivos de contexto. La estrategia decide si el
agente recibe las reglas del proyecto: con ``always_on`` el ``AGENTS.md`` del proyecto
se copia a la raíz con el nombre que ese agente lee; con ``none`` no se copia nada. El
enunciado es idéntico para todos y entra por la entrada estándar. Se guarda el
``git diff`` final contra el estado que recibió el agente, y junto a él un ``.json`` con
metadatos que no identifican la máquina.

Los agentes se declaran en el pre-registro, no aquí:

    [agente.mi_agente]
    comando = ["programa", "--model", "{modelo}"]   # recibe el enunciado por stdin
    modelo = "..."
    contexto = "AGENTS.md"                           # nombre con el que lee sus reglas

    [agente.mi_agente.entorno]                       # variables de entorno; opcional
    CLAVE = "valor"

Ese comando es código del pre-registro: se ejecuta con los permisos de quien lanza el
corredor. Antes de correr un pre-registro ajeno, ``correr --simular`` enseña qué lanzaría.

Una corrida no se registra si el agente no llegó a trabajar por causas ajenas a él:
código de salida distinto de cero, o un evento ``{"type": "error"}`` o
``{"type": "result", "is_error": true}`` en su salida JSON. Se reintenta una vez; si
vuelve a fallar la batería se detiene, y al relanzarla continúa donde quedó. Agotar el
límite de tiempo sí se registra, marcado en los metadatos.

``correr`` no enseña resultados de reglas mientras la batería está en marcha: el
veredicto lo da ``estudios.decision`` cuando están todas las corridas.

Uso:
    python -m estudios.corrida probar PROYECTO AGENTE [--modelo M]
    python -m estudios.corrida piloto PROYECTO AGENTE [--modelo M]
    python -m estudios.corrida correr PROYECTO [--corridas corridas] [--max N] [--simular]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import random
import shutil
import signal
import stat
import subprocess
import sys
import time
import tomllib
import uuid
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from verificador import fuente_diff, verificar

from .campos import como_entero, como_lista, como_real, como_tabla, como_texto
from .manifiestos import validar_proyecto

ESTRATEGIAS = ("none", "always_on")
LIMITE_MINUTOS = 30.0
LIMITE_PRUEBA_S = 300.0
SEMILLA = 20261204
MARCA = "labia-contexto-ok"
ENUNCIADO_PRUEBA = (
    "Create a file named hola.py in the repository root. It must define a function "
    "suma(a: int, b: int) -> int that returns the sum of its two arguments. "
    "Do not create or modify any other file."
)
CONTEXTO_PRUEBA = (
    "# Repository rules\n\nEvery Python file you create in this repository must begin with the "
    f"following comment as its very first line:\n\n```\n# {MARCA}\n```\n"
)
# Archivos que un agente puede leer como instrucciones sin que nadie se los entregue.
CONTEXTOS = ("AGENTS.md", "CLAUDE.md", "CLAUDE.local.md")
GLOBALES = (".claude/CLAUDE.md", ".config/opencode/AGENTS.md")
_ESTADO_DE_AGENTE = (":(exclude).claude", ":(exclude).opencode")
_IDENTIDAD = ("-c", "user.name=labia", "-c", "user.email=labia@localhost", "-c", "commit.gpgsign=false")


class Falla(Exception):
    """El corredor no pudo hacer su parte (configuración, git, programa ausente). No es un resultado del agente."""


@dataclass(frozen=True)
class Agente:
    """Cómo se invoca un agente y con qué nombre lee su archivo de reglas."""

    id: str
    comando: tuple[str, ...]
    modelo: str
    contexto: str
    entorno: Mapping[str, str]

    def orden(self, modelo: str) -> list[str]:
        """El comando con el modelo sustituido."""
        if not modelo and any("{modelo}" in parte for parte in self.comando):
            raise Falla(f"el agente '{self.id}' no tiene modelo: escríbelo en el pre-registro o pasa --modelo")
        return [parte.replace("{modelo}", modelo) for parte in self.comando]


@dataclass(frozen=True)
class Tarea:
    """Una tarea pre-registrada."""

    id: str
    enunciado: str
    agentes: tuple[str, ...]
    estrategias: tuple[str, ...]
    repeticiones: int


@dataclass(frozen=True)
class Proyecto:
    """Lo que el corredor necesita del manifiesto y del pre-registro."""

    directorio: Path
    nombre: str
    tipo: str
    repositorio: str
    commit: str
    aplica: frozenset[str]
    reglas: Path | None
    reglas_de_agente: str | None
    tareas: tuple[Tarea, ...]
    agentes: Mapping[str, Agente]
    limite_s: float
    semilla: int
    piloto: str

    def agente(self, identificador: str) -> Agente:
        """El agente declarado con ese id, o una Falla que dice cuáles hay."""
        if identificador not in self.agentes:
            raise Falla(
                f"el pre-registro no declara [agente.{identificador}]; declarados: {sorted(self.agentes) or 'ninguno'}"
            )
        return self.agentes[identificador]


@dataclass(frozen=True)
class Ejecucion:
    """Lo que pasó al lanzar un agente una vez. Con ``falla`` no es registrable."""

    termino: str
    duracion_s: float
    diff: bytes
    falla: str | None
    reportado: Mapping[str, object]


def cargar(directorio: Path) -> Proyecto:
    """Lee manifiesto y pre-registro. La forma la valida ``estudios.manifiestos``; aquí sólo se lee."""
    for nombre in ("proyecto.toml", "preregistro.toml"):
        if not (directorio / nombre).is_file():
            raise Falla(f"{directorio}: falta {nombre}")
    try:
        manifiesto = tomllib.loads((directorio / "proyecto.toml").read_text(encoding="utf-8"))
        prereg = tomllib.loads((directorio / "preregistro.toml").read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise Falla(f"{directorio}: TOML inválido: {error}") from error
    reglas = como_tabla(manifiesto.get("reglas"))
    propias = directorio / como_texto(reglas.get("directorio"))
    agentes: dict[str, Agente] = {}
    for identificador, valor in como_tabla(prereg.get("agente")).items():
        declarado = como_tabla(valor)
        entorno = {clave: como_texto(v) for clave, v in como_tabla(declarado.get("entorno")).items()}
        agentes[identificador] = Agente(
            identificador, tuple(como_lista(declarado.get("comando"))), como_texto(declarado.get("modelo")),
            como_texto(declarado.get("contexto")), entorno,
        )
    tareas = tuple(
        Tarea(
            como_texto(t.get("id")), como_texto(t.get("enunciado")), tuple(como_lista(t.get("agentes"))),
            tuple(como_lista(t.get("estrategias"))), como_entero(t.get("repeticiones"), 0),
        )
        for t in (como_tabla(bruta) for bruta in prereg.get("tarea", []) if isinstance(bruta, dict))
    )
    ejecucion = como_tabla(prereg.get("ejecucion"))
    reglas_de_agente = directorio / "AGENTS.md"
    return Proyecto(
        directorio=directorio,
        nombre=directorio.resolve().name,
        tipo=como_texto(manifiesto.get("tipo")) or "python",
        repositorio=como_texto(manifiesto.get("repositorio")),
        commit=como_texto(manifiesto.get("commit")),
        aplica=frozenset(como_lista(reglas.get("aplica"))),
        reglas=propias if como_texto(reglas.get("directorio")) and propias.is_dir() else None,
        reglas_de_agente=reglas_de_agente.read_text(encoding="utf-8") if reglas_de_agente.is_file() else None,
        tareas=tareas,
        agentes=agentes,
        limite_s=60 * como_real(ejecucion.get("limite_minutos"), LIMITE_MINUTOS),
        semilla=como_entero(ejecucion.get("semilla"), SEMILLA),
        piloto=como_texto(como_tabla(prereg.get("piloto")).get("enunciado")),
    )


def _hogar() -> Path:
    """Directorio del corredor (clones, registros, pilotos), fuera del repositorio de LabIA."""
    return Path(os.environ.get("LABIA_HOME") or Path.home() / ".labia")


def _git(*args: str, cwd: Path | None = None) -> str:
    """Ejecuta git y devuelve su salida. Un fallo de git es una Falla del corredor."""
    salida = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if salida.returncode != 0:
        raise Falla(f"git {' '.join(args[:2])} falló: {salida.stderr.strip()[-400:]}")
    return salida.stdout.strip()


def _borrar(ruta: Path) -> None:
    """Borra un directorio de trabajo. En Windows los objetos de git son de sólo lectura."""

    def reintentar(funcion: Callable[..., object], objetivo: str, _error: BaseException) -> None:
        try:
            os.chmod(objetivo, stat.S_IWRITE)
            funcion(objetivo)
        except OSError:
            pass

    try:
        shutil.rmtree(ruta, onexc=reintentar)
    except OSError:
        pass


@contextmanager
def _trabajo() -> Iterator[Path]:
    """Directorio nuevo para una corrida; se borra al terminar."""
    ruta = _hogar() / "trabajo" / uuid.uuid4().hex[:12]
    ruta.parent.mkdir(parents=True, exist_ok=True)
    try:
        yield ruta
    finally:
        _borrar(ruta)


def contexto_ajeno() -> list[tuple[str, Path]]:
    """Archivos de instrucciones que el agente leería sin que el corredor se los entregue.

    Devuelve (nombre publicable, ruta local). Son un factor de confusión: llegan también
    a las corridas ``none`` y no son los mismos para cada agente.
    """
    candidatos = {Path.home().resolve() / relativa: f"~/{relativa}" for relativa in GLOBALES}
    base = (_hogar() / "trabajo").resolve()
    for directorio in (base, *base.parents):
        for nombre in (*CONTEXTOS, ".claude/CLAUDE.md"):
            candidatos.setdefault(directorio / nombre, f"superior/{nombre}")
    return [(publico, ruta) for ruta, publico in candidatos.items() if ruta.is_file()]


def _espejo(proyecto: Proyecto) -> Path:
    """Copia local del repositorio del proyecto: se descarga una vez y se reutiliza."""
    if not proyecto.repositorio:
        raise Falla(f"{proyecto.nombre}: el manifiesto no dice 'repositorio'")
    local = proyecto.directorio / proyecto.repositorio
    origen = str(local.resolve()) if "://" not in proyecto.repositorio and local.exists() else proyecto.repositorio
    espejo = _hogar() / "cache" / f"{proyecto.nombre}-{hashlib.sha256(origen.encode()).hexdigest()[:12]}.git"
    if not espejo.exists():
        espejo.parent.mkdir(parents=True, exist_ok=True)
        print(f"descargando {origen} (sólo la primera vez)", flush=True)
        _git("clone", "--quiet", "--bare", origen, str(espejo))
    if proyecto.commit:
        existe = subprocess.run(
            ["git", "-C", str(espejo), "cat-file", "-e", f"{proyecto.commit}^{{commit}}"], capture_output=True
        ).returncode == 0
        if not existe:
            _git("-C", str(espejo), "fetch", "--quiet", "origin", proyecto.commit)
    return espejo


def _entregar(trabajo: Path, contexto: tuple[str, str] | None) -> str:
    """Deja el archivo de reglas (si toca) y fija el estado que recibe el agente. Devuelve su commit."""
    if contexto is not None:
        nombre, texto = contexto
        (trabajo / nombre).write_text(texto, encoding="utf-8", newline="\n")
    _git("add", "-A", cwd=trabajo)
    if _git("status", "--porcelain", cwd=trabajo):
        _git(*_IDENTIDAD, "commit", "--quiet", "--no-verify", "-m", "estado que recibe el agente", cwd=trabajo)
    return _git("rev-parse", "HEAD", cwd=trabajo)


def _clon(proyecto: Proyecto, trabajo: Path, contexto: tuple[str, str] | None) -> str:
    """Clon limpio del repositorio del proyecto en su commit fijo, listo para el agente."""
    _git(
        "clone", "--quiet", "--no-checkout", "-c", "core.autocrlf=false", "-c", "core.eol=lf",
        "-c", "core.longpaths=true", str(_espejo(proyecto)), str(trabajo),
    )
    _git("checkout", "--quiet", "--detach", proyecto.commit or "HEAD", cwd=trabajo)
    _git("remote", "remove", "origin", cwd=trabajo)
    presentes = [nombre for nombre in CONTEXTOS if (trabajo / nombre).exists()]
    if presentes:
        raise Falla(
            f"el repositorio ya trae {presentes} en su raíz: 'none' no sería none y 'always_on' lo pisaría"
        )
    return _entregar(trabajo, contexto)


def _andamio(trabajo: Path, contexto: tuple[str, str]) -> str:
    """Repositorio mínimo para comprobar que un agente arranca, edita y lee su archivo de reglas."""
    trabajo.mkdir(parents=True)
    _git("init", "--quiet", cwd=trabajo)
    (trabajo / "README.md").write_text("Repositorio de prueba de LabIA.\n", encoding="utf-8", newline="\n")
    return _entregar(trabajo, contexto)


def _matar(proceso: subprocess.Popen[bytes]) -> None:
    """Termina el agente y todo lo que haya lanzado. Si ya terminó, sólo limpia lo que dejó vivo."""
    if sys.platform == "win32":
        if proceso.poll() is None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proceso.pid)], capture_output=True)
    else:
        try:
            os.killpg(proceso.pid, signal.SIGKILL)
        except OSError:
            pass


def _lanzar(
    orden: Sequence[str], entorno: Mapping[str, str], enunciado: str, trabajo: Path, limite_s: float, registro: Path
) -> tuple[str, int | None, float]:
    """Lanza el agente con el enunciado por stdin. Devuelve (término, código de salida, segundos)."""
    ejecutable = shutil.which(orden[0])
    if ejecutable is None:
        raise Falla(f"no encuentro '{orden[0]}' en el PATH: instálalo o abre una terminal nueva")
    registro.parent.mkdir(parents=True, exist_ok=True)
    completa = [ejecutable, *orden[1:]]
    ambiente = {**os.environ, **entorno}
    inicio = time.monotonic()
    termino = "ok"
    with Path(f"{registro}.out").open("wb") as salida, Path(f"{registro}.err").open("wb") as errores:
        if sys.platform == "win32":
            proceso = subprocess.Popen(
                completa, cwd=trabajo, env=ambiente, stdin=subprocess.PIPE, stdout=salida, stderr=errores,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        else:
            proceso = subprocess.Popen(
                completa, cwd=trabajo, env=ambiente, stdin=subprocess.PIPE, stdout=salida, stderr=errores,
                start_new_session=True,
            )
        try:
            proceso.communicate(enunciado.encode("utf-8"), timeout=limite_s)
        except subprocess.TimeoutExpired:
            termino = "limite_de_tiempo"
        finally:
            # También al interrumpir con Ctrl+C: el agente vive en su propio grupo de procesos.
            _matar(proceso)
            try:
                proceso.wait(timeout=30)
            except subprocess.TimeoutExpired:
                pass
    return termino, (proceso.returncode if termino == "ok" else None), time.monotonic() - inicio


def _texto_de(ruta: Path) -> str:
    """Contenido de un registro del agente, tolerante a bytes inválidos."""
    return ruta.read_text(encoding="utf-8", errors="replace") if ruta.is_file() else ""


def _eventos(salida: str) -> list[dict[str, object]]:
    """Objetos JSON que el agente imprimió, uno por línea (o uno solo)."""
    eventos: list[dict[str, object]] = []
    for linea in salida.splitlines():
        if not linea.lstrip().startswith("{"):
            continue
        try:
            objeto = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if isinstance(objeto, dict):
            eventos.append(como_tabla(objeto))
    return eventos


def _error_reportado(eventos: Sequence[Mapping[str, object]]) -> str | None:
    """Mensaje del primer error que el propio agente declaró en su salida, si lo hay."""
    for evento in eventos:
        if evento.get("type") == "error":
            interno = evento.get("error")
            mensaje = como_tabla(interno).get("message") or evento.get("message") or interno
            return str(mensaje or "error sin mensaje")[:400]
        if evento.get("type") == "result" and evento.get("is_error") is True:
            return str(evento.get("result") or evento.get("subtype") or "error sin mensaje")[:400]
    return None


def _reportado(eventos: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Resumen publicable de lo que el agente dijo de su propia corrida."""
    tipos = Counter((como_texto(e.get("type")) or "?")[:40] for e in eventos)
    resumen: dict[str, object] = {"eventos": dict(sorted(tipos.most_common(20)))}
    final = next((e for e in reversed(eventos) if e.get("type") == "result"), None)
    if final is not None:
        for clave in ("num_turns", "duration_ms", "total_cost_usd"):
            valor = final.get(clave)
            if isinstance(valor, (int, float)) and not isinstance(valor, bool):
                resumen[clave] = valor
        uso = final.get("modelUsage")
        if isinstance(uso, dict):
            resumen["modelos"] = sorted(str(modelo) for modelo in uso)
        denegados = final.get("permission_denials")
        if isinstance(denegados, list):
            resumen["permisos_denegados"] = len(denegados)
    return resumen


def _cola(registro: Path) -> str:
    """Últimas líneas de lo que el agente escribió, para explicar un fallo."""
    lineas = [
        linea.strip() for sufijo in (".err", ".out")
        for linea in _texto_de(Path(f"{registro}{sufijo}")).splitlines() if linea.strip()
    ]
    return " | ".join(lineas[-4:])[-600:] or "sin salida"


def _diff(trabajo: Path, base: str) -> bytes:
    """Diff final contra el estado que recibió el agente, en UTF-8 y sin el estado propio del agente."""
    _git("add", "-A", "--", ".", *_ESTADO_DE_AGENTE, cwd=trabajo)
    salida = subprocess.run(
        ["git", "-c", "core.quotepath=false", "diff", "--cached", "--no-color", "--no-ext-diff", "--no-renames",
         "--ignore-cr-at-eol", base],
        cwd=trabajo, capture_output=True,
    )
    if salida.returncode != 0:
        raise Falla(f"git diff falló: {salida.stderr.decode('utf-8', errors='replace')[-400:]}")
    return salida.stdout.decode("utf-8", errors="replace").encode("utf-8")


def _con_agente(
    agente: Agente, modelo: str, enunciado: str, trabajo: Path, base: str, limite_s: float, registro: Path
) -> Ejecucion:
    """Lanza el agente sobre un árbol ya preparado y recoge lo que dejó."""
    termino, codigo, segundos = _lanzar(agente.orden(modelo), agente.entorno, enunciado, trabajo, limite_s, registro)
    eventos = _eventos(_texto_de(Path(f"{registro}.out")))
    falla: str | None = None
    if termino == "ok":
        declarado = _error_reportado(eventos)
        if codigo != 0:
            falla = f"salió con código {codigo}: {declarado or _cola(registro)}"
        elif declarado is not None:
            falla = declarado
    return Ejecucion(termino, segundos, b"" if falla else _diff(trabajo, base), falla, _reportado(eventos))


def _version(programa: str) -> str:
    """Primera línea de ``programa --version``; vacío si no responde."""
    ejecutable = shutil.which(programa)
    if ejecutable is None:
        return ""
    try:
        salida = subprocess.run(
            [ejecutable, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return next((linea.strip()[:80] for linea in (salida.stdout + salida.stderr).splitlines() if linea.strip()), "")


def _resumen(diff: bytes) -> str:
    """Tamaño de un diff en una frase."""
    texto = diff.decode("utf-8", errors="replace")
    archivos = len(fuente_diff(texto).rutas)
    lineas = sum(linea.startswith("+") and not linea.startswith("+++") for linea in texto.splitlines())
    return f"{archivos} archivo(s), +{lineas} líneas"


def _avisar_contexto_ajeno() -> list[str]:
    """Imprime los archivos de instrucciones ajenos al corredor y devuelve sus nombres publicables."""
    ajeno = contexto_ajeno()
    for _, ruta in ajeno:
        print(f"aviso: {ruta} llega al agente sin que el corredor lo entregue")
    return [publico for publico, _ in ajeno]


def probar(directorio: Path, identificador: str, modelo: str | None) -> int:
    """Comprueba en un repositorio de prueba que el agente arranca, edita y lee su archivo de reglas."""
    proyecto = cargar(directorio)
    agente = proyecto.agente(identificador)
    usado = modelo or agente.modelo
    if not agente.contexto:
        raise Falla(f"[agente.{agente.id}] no dice 'contexto': el nombre del archivo de reglas que lee")
    _avisar_contexto_ajeno()
    registro = _hogar() / "registros" / f"probar__{agente.id}"
    print(f"agente:    {agente.id} · {_version(agente.comando[0]) or 'versión desconocida'} · modelo {usado or '—'}")
    with _trabajo() as trabajo:
        base = _andamio(trabajo, (agente.contexto, CONTEXTO_PRUEBA))
        ejecucion = _con_agente(agente, usado, ENUNCIADO_PRUEBA, trabajo, base, LIMITE_PRUEBA_S, registro)
    if ejecucion.falla is not None:
        print(f"resultado: FALLO — {ejecucion.falla}")
    elif ejecucion.termino != "ok":
        print(f"resultado: FALLO — no terminó en {LIMITE_PRUEBA_S:.0f} s (¿espera un permiso o un inicio de sesión?)")
    elif not ejecucion.diff.strip():
        print("resultado: SIN CAMBIOS — el agente terminó sin editar nada (revisa modelo y permisos)")
    else:
        leido = MARCA.encode() in ejecucion.diff
        print(f"resultado: AGENTE — editó {_resumen(ejecucion.diff)} en {ejecucion.duracion_s:.0f} s")
        print(
            f"contexto:  LEÍDO — {agente.contexto} llegó al agente" if leido else
            f"contexto:  NO LEÍDO — el agente no siguió {agente.contexto}; así 'always_on' no entrega nada"
        )
        if leido:
            return 0
    print(f"registro:  {registro}.out y .err")
    return 1


def _reglas_de(proyecto: Proyecto, diff: bytes) -> list[str]:
    """Resultado de cada regla aplicable sobre un diff, en líneas legibles."""
    resultados = verificar(
        fuente_diff(diff.decode("utf-8", errors="replace")), set(proyecto.aplica), proyecto.tipo, proyecto.reglas
    )
    return [
        f"  {r.regla:4s} {r.violaciones}/{r.oportunidades} violaciones/oportunidades" if r.verificable
        else f"  {r.regla:4s} no verificable en un diff"
        for r in resultados
    ]


def piloto(directorio: Path, identificador: str, modelo: str | None) -> int:
    """Una corrida sin registrar sobre el repositorio real: cuánto tarda y si las reglas tienen oportunidades."""
    proyecto = cargar(directorio)
    agente = proyecto.agente(identificador)
    usado = modelo or agente.modelo
    if not proyecto.piloto.strip():
        raise Falla("el pre-registro no tiene [piloto] enunciado: una tarea de ensayo distinta de las registradas")
    _avisar_contexto_ajeno()
    contexto = (agente.contexto, proyecto.reglas_de_agente) if agente.contexto and proyecto.reglas_de_agente else None
    marca = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    registro = _hogar() / "registros" / proyecto.nombre / f"piloto__{agente.id}"
    print(f"piloto de {proyecto.nombre} con {agente.id} (modelo {usado or '—'}), "
          f"{'con' if contexto else 'sin'} archivo de reglas; no se registra", flush=True)
    with _trabajo() as trabajo:
        base = _clon(proyecto, trabajo, contexto)
        ejecucion = _con_agente(agente, usado, proyecto.piloto, trabajo, base, proyecto.limite_s, registro)
    if ejecucion.falla is not None:
        print(f"resultado: FALLO — {ejecucion.falla}\nregistro:  {registro}.out y .err")
        return 1
    destino = _hogar() / "pilotos" / proyecto.nombre / f"{agente.id}-{marca}.diff"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(ejecucion.diff)
    limite = "" if ejecucion.termino == "ok" else " (agotó el límite de tiempo)"
    print(f"resultado: {_resumen(ejecucion.diff)} en {ejecucion.duracion_s:.0f} s{limite}")
    propio = {clave: valor for clave, valor in ejecucion.reportado.items() if clave != "eventos"}
    if propio:
        print(f"el agente reporta: {json.dumps(propio, ensure_ascii=False)}")
    print("reglas aplicables:")
    print("\n".join(_reglas_de(proyecto, ejecucion.diff)) or "  ninguna")
    print(f"diff:      {destino}")
    return 0 if ejecucion.diff.strip() else 1


def pendientes(proyecto: Proyecto, corridas: Path) -> list[tuple[Tarea, str, str, int]]:
    """Corridas pre-registradas que aún no tienen diff, en un orden al azar fijado por la semilla.

    El orden mezcla agentes y tareas para que la hora del día o un límite de cuota no
    coincidan con un agente.
    """
    faltan = [
        (tarea, agente, estrategia, n)
        for tarea in proyecto.tareas
        for agente in tarea.agentes
        for estrategia in tarea.estrategias
        for n in range(1, tarea.repeticiones + 1)
        if not _destino(corridas, proyecto, tarea, agente, estrategia, n).is_file()
    ]
    random.Random(proyecto.semilla).shuffle(faltan)
    return faltan


def _destino(corridas: Path, proyecto: Proyecto, tarea: Tarea, agente: str, estrategia: str, n: int) -> Path:
    """Ruta del diff de una corrida según la convención del directorio."""
    return corridas / proyecto.nombre / tarea.id / f"{agente}__{estrategia}__{n}.diff"


def _impedimentos(proyecto: Proyecto) -> list[str]:
    """Razones por las que la batería registrada no puede empezar."""
    errores = validar_proyecto(proyecto.directorio)
    estrategias = sorted({e for tarea in proyecto.tareas for e in tarea.estrategias})
    errores += [
        f"el corredor no sabe entregar la estrategia '{e}' (sabe: {', '.join(ESTRATEGIAS)})"
        for e in estrategias if e not in ESTRATEGIAS
    ]
    con_reglas = "always_on" in estrategias
    if con_reglas and proyecto.reglas_de_agente is None:
        errores.append(f"always_on necesita el archivo de reglas {proyecto.directorio / 'AGENTS.md'}")
    for identificador in sorted({a for tarea in proyecto.tareas for a in tarea.agentes}):
        agente = proyecto.agentes.get(identificador)
        if agente is None or not agente.comando:
            errores.append(f"falta [agente.{identificador}] con su 'comando' en el pre-registro")
        elif con_reglas and not agente.contexto:
            errores.append(f"[agente.{identificador}]: falta 'contexto' para entregar always_on")
        elif shutil.which(agente.comando[0]) is None:
            errores.append(f"[agente.{identificador}]: no encuentro '{agente.comando[0]}' en el PATH")
    try:
        if _git("status", "--porcelain", "--", ".", cwd=proyecto.directorio):
            errores.append(f"{proyecto.directorio}: tiene cambios sin commit; el pre-registro se fija antes de correr")
    except Falla:
        errores.append(f"{proyecto.directorio}: no está en un repositorio git; el pre-registro no se puede fijar")
    return errores


def _metadatos(
    proyecto: Proyecto, tarea: Tarea, agente: Agente, estrategia: str, n: int,
    ejecucion: Ejecucion, inicio: str, contexto: tuple[str, str] | None, ajeno: Sequence[str],
) -> dict[str, object]:
    """Metadatos publicables de una corrida: sin rutas, sin nombre de máquina, sin transcripción."""
    try:
        labia = _git("rev-parse", "--short", "HEAD", cwd=proyecto.directorio)
    except Falla:
        labia = ""
    return {
        "proyecto": proyecto.nombre, "tarea": tarea.id, "agente": agente.id, "estrategia": estrategia, "n": n,
        "modelo": agente.modelo,
        "version_agente": _version(agente.comando[0]),
        "commit_base": proyecto.commit,
        "labia": labia,
        "sistema": platform.system(),
        "inicio_utc": inicio,
        "duracion_s": round(ejecucion.duracion_s, 1),
        "termino": ejecucion.termino,
        "sha256_diff": hashlib.sha256(ejecucion.diff).hexdigest(),
        "sha256_enunciado": hashlib.sha256(tarea.enunciado.encode("utf-8")).hexdigest(),
        "sha256_contexto": hashlib.sha256(contexto[1].encode("utf-8")).hexdigest() if contexto else None,
        "contexto_ajeno": list(ajeno),
        "reportado": dict(ejecucion.reportado),
    }


def correr(directorio: Path, corridas: Path, maximo: int | None, simular: bool, con_contexto_ajeno: bool) -> int:
    """Corre las corridas pre-registradas que faltan y guarda diff y metadatos de cada una."""
    proyecto = cargar(directorio)
    errores = _impedimentos(proyecto)
    if errores:
        print("\n".join(errores), file=sys.stderr)
        print(f"la batería no empieza: {len(errores)} cosa(s) por resolver", file=sys.stderr)
        return 1
    faltan = pendientes(proyecto, corridas)
    total = sum(len(t.agentes) * len(t.estrategias) * t.repeticiones for t in proyecto.tareas)
    tanda = faltan if maximo is None else faltan[:maximo]
    print(f"{proyecto.nombre}: {total - len(faltan)} de {total} corridas hechas; esta tanda: {len(tanda)}")
    if simular:
        for tarea, identificador, estrategia, n in tanda:
            agente = proyecto.agentes[identificador]
            print(f"  {tarea.id} · {identificador} · {estrategia} · #{n} · {' '.join(agente.orden(agente.modelo))}")
        return 0
    ajeno = _avisar_contexto_ajeno()
    if ajeno and not con_contexto_ajeno and tanda:
        print("la batería no empieza: aparta esos archivos, o repite con --con-contexto-ajeno "
              "(queda anotado en cada corrida)", file=sys.stderr)
        return 1
    for hechas, (tarea, identificador, estrategia, n) in enumerate(tanda, 1):
        agente = proyecto.agentes[identificador]
        contexto = (agente.contexto, proyecto.reglas_de_agente or "") if estrategia == "always_on" else None
        registro = _hogar() / "registros" / proyecto.nombre / f"{tarea.id}__{identificador}__{estrategia}__{n}"
        print(f"[{hechas}/{len(tanda)}] {tarea.id} · {identificador} · {estrategia} · #{n} … ", end="", flush=True)
        ejecucion: Ejecucion | None = None
        for _ in range(2):
            inicio = datetime.now(timezone.utc).isoformat(timespec="seconds")
            with _trabajo() as trabajo:
                base = _clon(proyecto, trabajo, contexto)
                ejecucion = _con_agente(agente, agente.modelo, tarea.enunciado, trabajo, base, proyecto.limite_s, registro)
            if ejecucion.falla is None:
                break
            print(f"fallo ({ejecucion.falla}) … ", end="", flush=True)
        if ejecucion is None or ejecucion.falla is not None:
            print(f"\nla batería se detiene: {identificador} no llegó a trabajar dos veces seguidas. No se registró "
                  f"nada de esta corrida.\nregistro: {registro}.out y .err\n"
                  "Cuando esté resuelto (cuota, sesión, red), repite el mismo comando: continúa donde quedó.",
                  file=sys.stderr)
            return 2
        destino = _destino(corridas, proyecto, tarea, identificador, estrategia, n)
        destino.parent.mkdir(parents=True, exist_ok=True)
        metadatos = _metadatos(proyecto, tarea, agente, estrategia, n, ejecucion, inicio, contexto, ajeno)
        destino.with_suffix(".json").write_text(
            json.dumps(metadatos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        provisional = destino.with_suffix(".parcial")
        provisional.write_bytes(ejecucion.diff)
        os.replace(provisional, destino)
        limite = "" if ejecucion.termino == "ok" else " · agotó el límite de tiempo"
        print(f"{_resumen(ejecucion.diff)} en {ejecucion.duracion_s:.0f} s{limite}", flush=True)
    quedan = len(faltan) - len(tanda)
    if quedan:
        print(f"faltan {quedan} corridas: repite el comando para continuar")
    else:
        print(f"batería completa: {total} de {total}. Sube {corridas / proyecto.nombre} en un commit propio; "
              "el CI recalcula la tabla y la decisión.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada: probar un agente, correr un piloto o correr la batería pre-registrada."""
    parser = argparse.ArgumentParser(prog="python -m estudios.corrida")
    acciones = parser.add_subparsers(dest="accion", required=True)
    for nombre in ("probar", "piloto"):
        accion = acciones.add_parser(nombre)
        accion.add_argument("proyecto", type=Path)
        accion.add_argument("agente")
        accion.add_argument("--modelo")
    bateria = acciones.add_parser("correr")
    bateria.add_argument("proyecto", type=Path)
    bateria.add_argument("--corridas", type=Path, default=Path("corridas"))
    bateria.add_argument("--max", type=int, dest="maximo")
    bateria.add_argument("--simular", action="store_true")
    bateria.add_argument("--con-contexto-ajeno", action="store_true")
    args = parser.parse_args(argv)
    for flujo in (sys.stdout, sys.stderr):
        if isinstance(flujo, io.TextIOWrapper):
            flujo.reconfigure(errors="replace")
    try:
        if args.accion == "probar":
            return probar(args.proyecto, args.agente, args.modelo)
        if args.accion == "piloto":
            return piloto(args.proyecto, args.agente, args.modelo)
        return correr(args.proyecto, args.corridas, args.maximo, args.simular, args.con_contexto_ajeno)
    except Falla as falla:
        print(f"FALLO — {falla}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrumpido: no se registró la corrida en curso; repite el comando para continuar", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
