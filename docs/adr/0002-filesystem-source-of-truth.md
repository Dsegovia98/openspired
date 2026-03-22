# ADR 0002 — Filesystem as Domain Source of Truth

## Context
El motor actual persiste contexto, tickets y trazas en `workspace/` y carpetas de dominio runtime. Migrar a DB ahora agregaría riesgo y doble fuente de verdad.

## Decision
Mantener filesystem como fuente de verdad en V1 desktop:
- Registro: `workspace/logs/_Registro.md`
- Trazas: `workspace/logs/*_Trace_Log.md`
- Tickets: carpetas de dominio en runtime root.

## Consequences
- Menor riesgo de migración y mayor compatibilidad con el pipeline existente.
- Búsqueda/filtros de artefactos se implementan sobre lectura de archivos.
- DB queda pospuesta para fase multi-tenant/cloud.
