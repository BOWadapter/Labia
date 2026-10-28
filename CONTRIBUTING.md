# Cómo contribuir a LabIA

LabIA mide qué agente de código cumple qué regla. Se contribuye con cuatro cosas, y cada
una tiene una comprobación automática que la acepta o la rechaza. Ninguna se acepta
por estar bien escrita.

## 1. Arranque

Requisitos: Git y Python 3.13.

```powershell
git clone https://github.com/USUARIO/labia.git
cd labia
./scripts/bootstrap.ps1                    # Windows: venv, instalación y todas las comprobaciones
```

En Linux/macOS:

```bash
python -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest -q && python -m mypy && python -m verificador casos
```

Opcional, para que cada commit pase por las mismas comprobaciones que el CI:
`python -m pip install pre-commit` y luego `pre-commit install`.

## 2. Flujo

`main` está protegida: sólo cambia por pull request con el CI en verde. Una rama por
cambio (`feature/...`, `fix/...`, `regla/...`), Conventional Commits, y en el PR una
línea `Evidencia:` con el comando que demuestra el cambio.

## 3. Qué se puede aportar

| Unidad | Dónde | La acepta |
|---|---|---|
| **Regla** general | `verificador/reglas/rN_nombre.py` | el meta-test: trae casos que la cumplen y la violan, y los separa |
| **Regla de proyecto** | `.labia/reglas/` del proyecto | `python -m verificador casos --reglas-proyecto .labia/reglas` |
| **Proyecto** | `proyectos/NNN-nombre/proyecto.toml` + `preregistro.toml` | `python -m estudios.manifiestos proyectos`: claves válidas, asignación pre-registrada entre los agentes de la tarea |
| **Corrida** de un agente | `corridas/NNN-nombre/<tarea>/<agente>__<estrategia>__<n>.diff` | el CI comprueba que el pre-registro es anterior y no cambió, re-verifica el diff y recalcula la tabla |

Una corrida es el `git diff` que produjo el agente sobre el commit del manifiesto, con
el `AGENTS.md` entregado según la estrategia (`none`, `always_on`, `selective`). En el
PR indica agente, versión y modelo.

**Buenas primeras contribuciones:** una regla mecánica para un tipo nuevo
(`typescript`: `tsc --strict`, TSDoc, `*.test.ts` junto al código; hardware:
`kicad-cli pcb drc --format json`), que `verificador directorio` lea `aplica` del
manifiesto en vez de recibir `--reglas`, y la detección de idioma de R2 sin juez de
modelo.

## 4. Lo que el CI rechaza

- Una regla sin casos que la separen, o que devuelve conteos sin oportunidades.
- Un manifiesto o pre-registro con claves desconocidas o tipos equivocados.
- Corridas cuyo pre-registro no sea anterior, o que se haya cambiado después.
- Un test recortado para pasar. Si un fixture estaba mal escrito, corrígelo y dilo.
- Cifras escritas a mano en documentos, o comandos citados que no existen.
- Dependencias de runtime nuevas en `verificador/` sin un caso que se rompa sin ellas.

## 5. Licencia y decisiones

El código y los datos se publican con Apache-2.0; al contribuir aceptas esa licencia
para tu aporte. Las decisiones se toman con evidencia: un PR que cambia una compuerta
o una regla trae el comando y la salida que lo justifican. Hasta que haya tres
contribuidores con PR fusionado decide la persona mantenedora; después, `CODEOWNERS`
por directorio.
