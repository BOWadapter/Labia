# AGENTS.md — trabajar en el repositorio de LabIA

Este archivo es para agentes (Claude Code, Codex, OpenCode) que modifican LabIA. Las
reglas que LabIA impone a los proyectos que se le encargan están en
`proyectos/_plantilla/AGENTS.md`.

## Comprobaciones (deben pasar antes de dar algo por terminado)

```bash
python -m pytest -q
python -m mypy
python -m verificador casos
python -m estudios.manifiestos proyectos --corridas corridas
```

En Windows/PowerShell usa `python`, no `python3`; `./scripts/bootstrap.ps1` corre todo.

## Reglas

1. Python 3.13, sólo biblioteca estándar en `verificador/` y `estudios/`. Una
   dependencia nueva en runtime necesita un caso de uso que se rompa sin ella.
2. Type hints en todo; `mypy --strict` limpio. Docstrings en español.
3. Una regla nueva es un módulo en `verificador/reglas/` con `REGLA = Regla(...)` y
   casos que la cumplen y la violan. Sin casos que la separen, el test la rechaza.
4. Una regla reporta tasa sobre oportunidades. No devuelvas conteos sin denominador ni
   promedios entre reglas.
5. No escribas cifras ni estados de componentes en documentos (`PROMPT-MAESTRO.md`,
   `README.md`). Las cifras las produce el CI.
6. No recortes conjuntos de evaluación ni casos para que un test pase. Si un test
   falla, corrige el código o el fixture mal escrito, y dilo en el PR.
7. No edites un `preregistro.toml` que ya tenga corridas: el validador lo rechaza.
8. Conventional Commits (`feat(verificador): ...`, `fix(estudios): ...`). Una rama por
   cambio; `main` sólo cambia por PR con CI verde.
9. No añadas recuperación sobre el corpus (`labia/`) sin la tabla que lo justifique
   (`PROMPT-MAESTRO.md` §2).
