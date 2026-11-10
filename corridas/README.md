# corridas/

`NNN-proyecto/<tarea>/<agente>__<estrategia>__<n>.diff` — el `git diff` que produjo un
agente sobre el commit del manifiesto. El CI comprueba con `python -m estudios.manifiestos
proyectos` que el pre-registro de la tarea está en un commit anterior a la primera corrida
y no cambió después; luego los re-verifica con `python -m estudios.tabla corridas` y
publica la tabla en el artefacto `estado`.

`python -m estudios.corrida correr proyectos/NNN-proyecto` produce estos archivos con los
agentes declarados en el pre-registro y deja junto a cada diff un `.json` con el mismo
nombre: modelo, versión del agente, duración y cómo terminó, sin rutas ni nombre de
máquina. La transcripción del agente no se sube. Cuando están todas las corridas
pre-registradas, `python -m estudios.decision proyectos/NNN-proyecto` dice qué agente
indica la medición, o que no los distingue.
