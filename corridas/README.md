# corridas/

`NNN-proyecto/<tarea>/<agente>__<estrategia>__<n>.diff` — el `git diff` que produjo un
agente sobre el commit del manifiesto. El CI comprueba con `python -m estudios.manifiestos
proyectos` que el pre-registro de la tarea está en un commit anterior a la primera corrida
y no cambió después; luego los re-verifica con `python -m estudios.tabla corridas` y
publica la tabla en el artefacto `estado`.
