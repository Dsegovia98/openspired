---
description: Pipeline para construir un PRD completo a partir de un proyecto, con loops iterativos de gap-analysis hasta que no queden huecos.
---
# Workflow: Generador de PRD (Product Requirements Document)

Este workflow recibe un proyecto completo (descripción, contexto, capturas, especificaciones) y construye un PRD maduro y sin huecos a través de loops iterativos de análisis de brechas. Al terminar, produce una lista priorizada de Slices listos para ser procesados individualmente con `/generar_slice`.

## Diagrama del Flujo

```
[Input del PO] → Paso 1: Construcción del PRD
                       ↓
                 Paso 2: Gap Analysis (agentes buscan huecos)
                       ↓
              ┌── ¿Hay huecos? ──┐
              │                   │
             SÍ                  NO
              │                   │
        Paso 3: Presentar        Paso 5: Slice Breakdown
        preguntas al PO          + Guardar PRD final
              │
        Paso 4: PO responde
              │
              └──→ Volver a Paso 1 (enriquecer PRD con respuestas)
```

## Pasos del Pipeline

### Paso 1: Construcción / Enriquecimiento del PRD

- Lee `agents/00_Orquestador/00_Orquestador.md`, `agents/02_Ideador/02_Ideador.md`, `agents/03_Researcher/03_Researcher.md` y sus Skills.
- Lee `workspace/context/global.md`, `workspace/context/product_knowledge.md` y `workspace/context/relationships.md`.
- Si es la **primera iteración**: Toma el input crudo del PO y construye un borrador del PRD siguiendo la plantilla `PRD_Template.md` (ver abajo).
- Si es una **iteración posterior**: Lee el PRD existente + las respuestas del PO a las preguntas del loop anterior. Enriquece el PRD con la nueva información.
- El Researcher consulta `App/Ideas/` y el historial de tickets en `App/`, `Analitica/` y `workspace/logs/` por contexto previo relevante.

### Paso 2: Gap Analysis (Detección de Huecos)

- Lee `agents/04_Desarrollador_Concepto/04_Desarrollador_Concepto.md`, `agents/07_Feedback/07_Feedback.md` y sus Skills.
- Consulta `workspace/context/.reasoning_bank/anti_patrones.md` para detectar errores conocidos.
- Ejecuta un análisis de brechas estructurado sobre el PRD:

**Checklist de Validación del PRD:**
1. **Alcance:** ¿Están claros los límites del proyecto? ¿Qué incluye y qué NO incluye?
2. **Usuarios:** ¿Se definieron los usuarios afectados y sus roles?
3. **Dependencias:** ¿Hay módulos, APIs, datos o equipos de los que depende? ¿Están mapeados?
4. **Edge Cases:** ¿Qué pasa si falta data? ¿Qué pasa si el usuario es BASIC? ¿Qué pasa si hay errores de conexión?
5. **Estados:** ¿Se cubrieron los estados vacío, cargando, error y exitoso?
6. **Impacto:** ¿Esto afecta solo a una CU o a todas (Global vs Local)?
7. **Diseño:** ¿Se necesitan Design Tasks antes de las USs? ¿Se tiene Figma o se necesita generar?
8. **Prioridad:** ¿Cuál es el orden lógico de implementación?
9. **Métricas:** ¿Cómo se mide el éxito de este proyecto?
10. **Contradicciones:** ¿Algo en este PRD contradice las reglas de `workspace/context/global.md` o un patrón del ReasoningBank?

- Genera una lista de `[[GAPS]]` — preguntas específicas y accionables sobre lo que falta.

### Paso 3: Evaluación de Huecos

- **Si hay `[[GAPS]]`:**
  - Formula las preguntas al PO de forma estructurada y concisa.
  - Presenta al PO: (a) el PRD en su estado actual, (b) las preguntas organizadas por prioridad.
  - Usa `ask_user` / `notify_user` para entregar las preguntas.
  - **PAUSA — Espera respuestas del PO.**

- **Si NO hay `[[GAPS]]`:**
  - Salta directamente al **Paso 5**.

### Paso 4: Integración de Respuestas

- El PO responde las preguntas.
- Incorpora las respuestas al PRD (enriquece las secciones correspondientes).
- **Vuelve al Paso 2** — El agente vuelve a buscar huecos con la nueva información.
- Este loop se repite hasta que el Paso 2 no produzca más `[[GAPS]]`.

> **Anti-Loop Guardrail:** Máximo 3 iteraciones del loop (Paso 2 → Paso 4). Si después de 3 rondas aún hay huecos, marca los restantes como `[ASUNCIÓN: ...]` con la mejor hipótesis del sistema y sigue adelante. No bloquear al PO indefinidamente.

### Paso 5: Slice Breakdown y Documentación Final

- Lee `agents/00_Orquestador/Skills/02_Skill_Deconstruccion_Epicas.md`.
- Toma el PRD finalizado y lo descompone en **Slices individuales** (cada uno = un futuro ticket).
- Para cada Slice, define:
  - **Nombre corto**
  - **Tipo:** User Story o Design Task
  - **Dependencias:** De qué otro Slice depende
  - **Prioridad:** Orden lógico de implementación
  - **Resumen:** Qué cubre este Slice en 1-2 líneas
- **App:** guarda el PRD en `/PRDs/App/PRD_[Nombre_Proyecto].md`.
- **Analítica:** guarda el PRD en `/PRDs/Analitica/PRD_[Nombre_Proyecto].md`.
- Guarda la lista de Slices al final del PRD.
- Notifica al PO que el PRD está listo y que puede ejecutar `/generar_slice` para cada Slice individual.

---

## PLANTILLA: PRD (Product Requirements Document)

```markdown
---
Proyecto: [Nombre del Proyecto]
Dominio: [App | Analítica | Ambos]
Estado: [Borrador | En Revisión | Aprobado]
Iteración: [1]
Fecha: YYYY-MM-DD
---

# PRD: [Nombre del Proyecto]

## 1. Objetivo
[¿Qué se quiere lograr? ¿Qué problema resuelve?]

## 2. Contexto
[¿Por qué ahora? ¿Qué lo motivó? Background del negocio.]

## 3. Alcance
### Incluye
- [Qué SÍ cubre este proyecto]
### No incluye
- [Qué queda explícitamente fuera]

## 4. Usuarios Afectados
| Rol | Impacto |
|-----|---------|
| [Rol] | [Qué cambia para este rol] |

## 5. Requerimientos Funcionales
### 5.1 [Módulo / Feature 1]
- [Detalle del requerimiento]
### 5.2 [Módulo / Feature 2]
- [Detalle del requerimiento]

## 6. Dependencias
- [De qué depende este proyecto: módulos, APIs, datos]

## 7. Edge Cases y Estados
- [¿Qué pasa si...?]

## 8. Diseño
- [¿Se necesita Figma? ¿Hay Design Tasks previas?]

## 9. Fases de Implementación
| Fase | Descripción | Prioridad |
|------|-------------|-----------|
| 1 | [Qué se hace primero] | Alta |
| 2 | [Qué sigue] | Media |

## 10. Métricas de Éxito
- [¿Cómo se mide que esto funcionó?]

## 11. Asunciones
- [Lo que se asumió por falta de info]

---

## SLICES (Lista de Tickets a Generar)
| # | Nombre | Tipo | Depende de | Prioridad | Resumen |
|---|--------|------|------------|-----------|---------|
| 1 | [nombre] | US / DT | — | Alta | [1 línea] |
| 2 | [nombre] | US / DT | Slice 1 | Alta | [1 línea] |
```
