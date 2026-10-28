# AGENTS.md — reglas del proyecto (plantilla LabIA, tipo python)

Copia este archivo a la raíz del repositorio del proyecto. Codex y OpenCode lo leen
solos; Claude Code también (desde 2.1.277) si el repo no tiene `CLAUDE.md`. Cada regla
se verifica con `python -m verificador`; lo que no puede verificarse por máquina lo dice.

1. **Type hints en todo.** `mypy --strict` sin errores. (R1)
2. **Docstrings en español** en toda función pública. (R2; el idioma lo revisa una
   persona)
3. **Logs JSON** en stdout, una línea por evento, con `request_id`, `timestamp` ISO 8601
   y `duration_ms`. Nunca contraseñas, tokens ni claves en un log. (R3)
4. **Escrituras idempotentes** con clave de idempotencia explícita: repetir la operación
   no duplica datos. (R4; revisión humana, el verificador lista los sitios)
5. **Nada hardcodeado.** URLs, hosts, puertos y credenciales entran por variables de
   entorno (`os.getenv`). Un valor por defecto dentro de `getenv` está permitido. (R5)
6. **Conventional Commits.** Nunca `force push` a `main` ni `develop`. (R6)
7. **Tests junto al código:** cada módulo `x.py` tiene `test_x.py` en su carpeta o en
   `tests/`. (R7)

Reglas propias de este proyecto: `.labia/reglas/*.py` (ver
`proyectos/_plantilla/reglas/` en LabIA).

Antes de terminar, corre:

```bash
python -m verificador directorio . --git . --stdout salida_demo.txt --reglas-proyecto .labia/reglas
```
