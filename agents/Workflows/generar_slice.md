---
description: Pipeline automatizado para procesar una Épica o Requerimiento a través de los 8 Agentes PO.
---
# Flujo de Trabajo: Generador de Slices (Automated PO)

Este workflow orquesta la ejecución secuencial de los 8 agentes definidos en `agents/`. Para iniciar este flujo, usa el slash command `/generar_slice` y proporciona tu requerimiento inicial de negocio.

## Pre-requisito Global
Antes del Paso 1, **todos los agentes** deben leer `workspace/context/global.md` como fuente de reglas inmutables.

## Pasos del Pipeline

1. **Paso 1: Orquestación y Triaje**
   - Lee `agents/00_Orquestador/00_Orquestador.md` y todas sus `Skills/`.
   - Lee `workspace/context/global.md`, `workspace/context/sprint_context.md` y `agents/00_Orquestador/Directorio_Equipo.md`.
   - Determina el **dominio** (App o Analytics) y el **módulo/proyecto** al que pertenece usando `workspace/context/product_knowledge.md`.
   - Genera el **Manifiesto de Slice (YAML)** incluyendo: ID (del `_Registro.md`), dominio, módulo, tipo (DT o US).
   - Si faltan insumos críticos, pausa y pídeselos al PO.

2. **Paso 2: Generación de Contexto (Ideador y Researcher)**
   - Lee `agents/02_Ideador/02_Ideador.md` y `agents/03_Researcher/03_Researcher.md` (y sus Skills).
   - El Researcher consulta `workspace/context/product_knowledge.md`, `workspace/context/relationships.md` y `App/Ideas/`.
   - El Researcher busca en `App/[Módulo]/` o `Analitica/[Disciplina]/[Proyecto]/` tickets previos relacionados.
   - El Ideador consulta `workspace/context/.reasoning_bank/patrones_exitosos.md`.

3. **Paso 3: Arquitectura Conceptual**
   - Lee `agents/04_Desarrollador_Concepto/04_Desarrollador_Concepto.md` (y Skills).
   - Consulta `workspace/context/.reasoning_bank/patrones_exitosos.md` y `anti_patrones.md`.
   - Redacta la lógica, los edge cases, y la matriz de fallos.

4. **Paso 4: Redacción de US o Design Task**
   - Lee `agents/05_Escritor_USs/05_Escritor_USs.md` (y Skills).
   - Sintetiza en texto plano estructurado bilingüe (EN/ES).

5. **Paso 5: Calidad y QA / Feedback**
   - Lee `agents/06_QA/06_QA.md` y `agents/07_Feedback/07_Feedback.md` (y Skills).
   - QA agrega criterios (solo para USs). Feedback audita contra `workspace/context/.reasoning_bank/`.
   - Máximo 2 iteraciones internas de mejora.

6. **Paso 6: Documentación Final y Trazabilidad**
   - Lee `agents/01_Documentador/01_Documentador.md` y sus Directory Rules.
   - Consulta `_Registro.md` para asignar el siguiente ID disponible (tabla "PRÓXIMOS IDs DISPONIBLES").
   - **App:** guarda en `App/[Global_Scope|Local_Scope]/[Módulo]/[Design_Tasks|User_Stories]/[ID]_[Nombre].md`
   - **Analítica:** guarda en `Analitica/[DE|DS|BI]/[Proyecto]/[ID]_[Nombre].md`
   - **Trace Log:** Usa `workspace/logs/_TEMPLATE_Trace_Log.md` como base. Crea `workspace/logs/[ID]_Trace_Log.md` con todos los campos completados — incluyendo la trayectoria de cada agente, intervenciones del PO y el Score final.
   - Actualiza `_Registro.md`: incrementa el contador del tipo correspondiente y agrega la nueva fila al historial.

7. **Paso 7: Aprendizaje y Memoria (Meta-Observador)**
   - Lee `agents/08_Agente_Meta_Observador/08_Agente_Meta_Observador.md` y sus Skills (01–04).
   - **Auditoría:** Escribe en `workspace/context/.meta_insights/audit_log_[ID].md`.
   - **Trayectoria (Ruflo):** Destila a `workspace/context/.reasoning_bank/patrones_exitosos.md` o `anti_patrones.md`.
   - **Memoria (Mem0):** Inyecta hechos nuevos en `workspace/context/`.
   - Notifica al PO que el ticket está listo.
