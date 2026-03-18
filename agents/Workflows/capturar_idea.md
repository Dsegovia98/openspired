---
description: Captura una idea cruda en el pre-backlog sin activar el pipeline completo de agentes.
---

# Workflow: Capturar Idea (Pre-Backlog)

Este workflow NO genera USs ni Design Tasks. Solo guarda una idea en el pre-backlog para madurarla después. Úsalo cuando tengas una idea que salió de una reunión, un chat, o un insight propio que aún no está listo para el pipeline.

## Pasos

1. **Recibir la Idea**
   - Escucha al PO describir la idea en lenguaje natural, sin formalismos.
   - Haz máximo **2 preguntas de clarificación** si hay ambigüedad crítica (ej: ¿a qué dominio pertenece, App o Analytics?). No hagas más preguntas — el objetivo es capturar rápido, no refinar.

2. **Generar el Archivo de la Idea**
   - Crea el archivo en `App/Ideas/ideas/[YYYY-MM-DD]_[nombre_corto_idea].md`.
   - Usa la plantilla de Idea Cruda (ver abajo).
   - Llena los campos con la información que el PO acaba de dar. Lo que no se sepa, déjalo como `[PENDIENTE]`.
   - **Agrega el dominio:** `App` o `Analitica` para que cuando se promueva al pipeline sepa si debe ir por `/generar_prd` (y guardarse en `PRDs/`) o directo por `/generar_slice` (y terminar en `App/` o `Analitica/`).

3. **Actualizar el Índice**
   - Abre `App/Ideas/_Ideas_Pendientes.md` (ruta relativa a la raíz del proyecto).
   - Agrega una nueva fila a la tabla del Índice con la fecha, el nombre corto, el origen y el estado `💡 Cruda`.

4. **Confirmar al PO**
   - Notifica que la idea fue guardada correctamente y en qué ruta vive.
   - **NO actives ningún agente adicional ni generes USs.** El trabajo termina aquí.

---

## PLANTILLA: IDEA CRUDA

```markdown
---
Fecha: YYYY-MM-DD
Dominio: [App | Analítica | Ambos]
Estado: 💡 Cruda
Origen: [Reunión | Chat | Insight propio | Otro]
---

## ¿Qué?
[Descripción de la idea en palabras del PO, sin formalismo. Sin User Story.]

## ¿Por qué?
[Contexto: ¿qué problema resuelve? ¿Por qué surgió ahora?]

## Preguntas abiertas / Info que falta
- [PENDIENTE]

## Notas adicionales
[Cualquier otra referencia, screenshot mental, o contexto relacionado]
```
