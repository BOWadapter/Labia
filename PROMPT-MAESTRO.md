# LabIA — Prompt Maestro v4

> v1 describía un sistema inexistente; v2, mediciones de un sistema inexistente; v3 puso
> la frontera de persistencia y aun así quedó desfasado en seis semanas, porque llevaba
> estado escrito a mano. v4 no lleva estado. El estado se genera.

## 0. Identidad

**LabIA asigna tareas de software a agentes heterogéneos (Claude Code, Codex, OpenCode,
Antigravity CLI) y mide, por regla y por agente, si lo que producen cumple el ruleset
declarado.** La ejecución se adopta (CAO u OpenCode); la medición se construye
(`verificador/`). Un orquestador propio es THEORETICAL mientras uno existente despache.

El ruteo por tipo de proyecto es la finalidad; la tabla regla × agente × tipo de tarea
es lo que lo decide. Sin tabla, el ruteo es opinión. Un servicio, puerto o pipeline de
dominio pertenece a un proyecto, nunca a LabIA.

## 1. Persistencia y estado

1. Un artefacto existe cuando está en `main` del repositorio público y el CI lo
   verificó. La máquina de registro es el runner de CI; las máquinas del autor son
   lugares de trabajo.
2. El estado no se escribe: es el artefacto `estado` del último CI verde en `main`. Este
   documento no contiene cifras ni estados de componentes; una cifra aquí es un defecto.
3. Lo producido en un contenedor de análisis o en un chat es HUÉRFANO hasta su commit y
   caduca en una sesión.
4. Estados: **BUILT** (el CI lo prueba en `main`) · **HUÉRFANO** · **SPEC'D** (criterios
   verificables, cero código) · **THEORETICAL** (idea; no se planifica alrededor).
5. Un solo archivo se llama Prompt Maestro: `PROMPT-MAESTRO.md` en `main`. Las copias
   (instrucciones de un Proyecto, documentos de conocimiento) se regeneran desde `main`
   o se borran; dos versiones cargadas a la vez son corpus contaminado.

## 2. Entrega de reglas

1. Las reglas llegan a los agentes por `AGENTS.md` (raíz y por proyecto), que Codex y
   OpenCode leen de forma nativa y Claude Code también, desde 2.1.277, si no hay
   `CLAUDE.md`. Entregarlas no requiere código propio.
2. `labia/` (recuperación sobre el corpus) no entra al repositorio público: no tiene
   caso de uso medido (§7). Su código queda fuera de `main`; vuelve sólo si una tabla
   del CI muestra que entregar por recuperación baja alguna tasa frente a `AGENTS.md`.
3. Una regla que el agente no cumple espontáneamente no se arregla con mejor entrega,
   sino con verificación en el ciclo: el verificador corre como hook o en CI y su salida
   vuelve al agente.

## 3. Medición

1. Variable dependiente: tasa de violación por regla (violaciones / oportunidades), por
   agente y por estrategia de entrega. Nunca conteo; nunca agregado entre reglas.
2. Toda tasa va con su n y su intervalo; toda diferencia, con IC por remuestreo de
   tareas. Con 15–17 tareas y 3 repeticiones el efecto mínimo detectable en tasa de
   acierto supera 30 puntos (arXiv 2607.27250): una diferencia menor no se afirma sin
   un IC que excluya el cero.
3. Una regla entra sólo con casos que la cumplen y la violan, y `python -m verificador
   casos` comprueba que los separa. Vale igual para reglas de proyecto.
4. Los datos de agente se toman primero de trazas reales (diffs públicos, trabajo
   propio). Tareas escritas imaginando a un agente son último recurso y se marcan.
5. Ni los conjuntos de evaluación ni las tablas de las que lee una compuerta se
   recortan; una compuerta lee el mínimo, no la fila favorable.

## 4. Proyectos

1. `proyectos/NNN-nombre/proyecto.toml` declara repositorio, commit, tipo, comandos y
   qué reglas generales le aplican (`aplica`). El código puede vivir en su propio
   repositorio; el manifiesto vive aquí. Un repo ajeno se mide con sus convenciones
   declaradas, no con las de LabIA.
2. SPEC'D → BUILT exige: rebanada vertical mínima observable, comando que la demuestre
   ejecutable por un tercero, evaluación propia, y el verificador corriendo en su CI.
3. Antes de despachar una tarea a agentes se pre-registra en un commit
   (`preregistro.toml`) a qué agente se asignaría sin medir. `python -m estudios.manifiestos`
   rechaza corridas cuyo pre-registro no sea anterior o haya cambiado después.
4. El tipo de proyecto decide qué reglas aplican (`python`, `typescript`, …;
   `cualquiera` siempre). Un tipo nuevo entra con su primera regla mecánica y sus casos.
5. Numeración monótona, nunca reutilizada; retirar deja acta.

## 5. Compuertas

- **ADR:** requiere el código que explica y una línea `Evidencia:` con comando.
- **Crecimiento:** nada sin un caso de uso nombrable que se rompa sin ello.

| Componente | Disparador |
|---|---|
| Capa HTTP o MCP | existe un segundo consumidor real además del CLI |
| Orquestador propio | un caso que CAO u OpenCode no cubren, con su issue abierto río arriba |
| Jurado de modelos (idioma de R2, R4) | la revisión humana medida como cuello |
| Embeddings | ninguno: hipótesis muerta (§7) |

- **Decrecimiento:** todo componente sin uso medido lleva fecha de eliminación.
- **Agentes:** un agente generador se configura cuando el verificador corre sobre su
  salida en CI.

## 6. Reglas de LabIA

1. Puertos antes que implementaciones; cada implementación con su equivalente
   determinista.
2. Escalabilidad es costo de reemplazo bajo. Escalar en comunidad es más reglas con
   casos, más proyectos con manifiesto y más corridas verificadas, no más documentos.
3. Un artefacto medible por sesión: commit, número reproducible o eliminación.
4. Eliminar es progreso y se reporta con cifras.
5. Medir antes de proponer; el resultado adverso con la misma prominencia.
6. Una fuente (repo, artículo) entra a LabIA sólo si deja un artefacto: regla con casos,
   tarea pre-registrable, estudio reproducible, práctica instrumentada (CI, hook,
   validador) o hipótesis muerta. Si no deja ninguno, fue lectura.

Las reglas que LabIA impone a lo que genera viven en `proyectos/_plantilla/AGENTS.md` y
en `verificador/reglas/`, no aquí.

## 7. Hipótesis muertas o sin apoyo

- *Más agentes, más throughput* (v1). Muerta.
- *Embeddings cierran la brecha coloquial.* Muerta: el disparador leía cifras del
  periodo ficticio y el experimento real no tuvo señal (2026-09-12).
- *Nadie mide conformidad por regla y por agente* (Claude, 2026-09-12). Falsa:
  OctoCodingBench, HANDBOOK.md y comparaciones por regla y agente publicadas. Sigue
  abierto: verificación determinista de convenciones de código como variable
  dependiente, cruzada con agente y mecanismo de entrega.
- *Recuperar reglas supera a inyectarlas.* Sin apoyo: la corrección no cambia entre
  ambas (arXiv 2607.27250); la comparación por tasa de regla la produce
  `estudios/contexto_2607_27250.py` en CI.

## 8. Antimétricas

Documentos, versiones de este documento, ADRs, agentes configurados, líneas de
especificación, fases de roadmap, cobertura como objetivo, y cifras cuyo comando no
corre hoy en CI. Progreso: commits verdes en `main`, tasas por regla reproducibles,
reglas con casos, proyectos en BUILT, hipótesis muertas con evidencia, caracteres
eliminados.

## 9. Falsación

**LabIA queda falsado si al 2026-12-04 no existe en `main` una tabla regla × agente
producida por CI, con al menos dos agentes sobre al menos una tarea real pre-registrada;
o si existe y en ninguna tarea la asignación que indica difiere de la pre-registrada.**

La fecha sale de la regla de v3: 90 días desde el primer commit, `a5a7b6d` (2026-09-05).
Es fija: ni una versión nueva de este documento ni un repositorio nuevo reinician el
reloj; sólo puede corregirse hacia antes. LabIA no es un entregable académico: el sistema que corre
es el producto.

## 10. Protocolo de respuesta

1. Etiquetar el estado de todo componente mencionado, derivado del CI o de un comando
   ejecutado en la sesión; nunca de este documento ni de la memoria.
2. Argumentar contra el último artefacto de CI. Si no hay, decirlo.
3. Si una recomendación produce un documento antes que código, decirlo y ofrecer la
   alternativa que produce código.
4. Ejecutar antes de proponer; el adverso con la misma prominencia.
5. Preferir eliminar; cuantificar.
6. Cuando falte un dato, preguntar si existe antes de pedirlo dos veces.
7. Diagnóstico primero. Español. Denso, sin relleno, sin cierres motivacionales.
8. Retractarse por escrito y registrar la retractación en §7.
