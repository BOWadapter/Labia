# LabIA

**¿Qué agente de código cumple qué regla, y con qué forma de entregarle las reglas?**
LabIA lo mide: reglas mecánicas con casos de referencia, tasa de violación por regla y
por agente, intervalos honestos y cifras que sólo produce el CI.

No es otro orquestador. Para despachar tareas a Claude Code, Codex, OpenCode o
Antigravity CLI se usan los que ya existen; LabIA pone la medición que decide a cuál
asignar cada tipo de tarea.

## Probarlo en un minuto

```bash
python -m pip install -e ".[dev]"
python -m verificador reglas                        # reglas registradas
python -m verificador directorio RUTA --git RUTA    # un proyecto, por regla
git diff | python -m verificador diff -             # lo que acaba de hacer un agente
```

En Windows, `./scripts/bootstrap.ps1` deja la máquina lista y verificada (el CI corre
el mismo script).

Primer estudio, sobre 291 corridas públicas de Claude Code y Codex (arXiv 2607.27250):

```bash
git clone https://github.com/codeprakhar25/context-files-coding-agents ../cfa
python -m estudios.contexto_2607_27250 ../cfa/data/experiment_full.db
```

La tabla vigente es el artefacto `estado` del último CI en `main`.

## Estructura

| Ruta | Qué es |
|---|---|
| `verificador/` | reglas como módulos con casos; CLI; sólo biblioteca estándar |
| `estudios/` | tablas con intervalos, estudios sobre corridas públicas, validador de manifiestos |
| `proyectos/` | manifiestos de proyectos y su pre-registro; `_plantilla/` para empezar |
| `corridas/` | diffs de agentes enviados por la comunidad, re-verificados por el CI |
| `scripts/` | arranque reproducible en cualquier máquina |

Contribuir: [`CONTRIBUTING.md`](CONTRIBUTING.md). Reglas para agentes que trabajan aquí:
[`AGENTS.md`](AGENTS.md). Principios y falsación: [`PROMPT-MAESTRO.md`](PROMPT-MAESTRO.md).
Licencia: Apache-2.0.
