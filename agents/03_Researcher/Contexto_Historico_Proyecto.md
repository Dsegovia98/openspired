# CONTEXTO HISTÓRICO DEL PROYECTO — {{PRODUCT_NAME}}
## Generado: {{FECHA}} | Fuente: Jira Export ({{N}} tickets, {{PERÍODO}})

> **Cómo usar este archivo:**
> Este documento es el banco de memoria histórica del Agente Researcher.
> Lo genera automáticamente el pipeline al final de cada run (vía Meta-Observador),
> o puedes crearlo manualmente con un export de Jira usando el script incluido.
> Reemplaza los `{{placeholders}}` con la información de tu producto.

---

## 1. VISIÓN GENERAL DEL PROYECTO

{{PRODUCT_NAME}} es {{DESCRIPCIÓN_BREVE_DEL_PRODUCTO}}. Su rol es {{ROL_DEL_PRODUCTO}}.

**Período cubierto:** {{FECHA_INICIO}} – {{FECHA_FIN}}
**Total de tickets analizados:** {{N}} tickets
- **User Stories:** {{N_US}}
- **Design Tasks:** {{N_DT}}

**Plataforma principal:** {{PLATAFORMA}}  (ej: Web Desktop, Mobile, API)

---

## 2. EQUIPO DE DESARROLLO

> Completa con los miembros reales de tu equipo.
> El Orquestador usa esta sección para asignar tickets correctamente.

### Product Owner
| Nombre | Rol | Tickets Generados |
|--------|-----|-------------------|
| {{NOMBRE}} | Product Owner Principal | {{N}} / {{TOTAL}} ({{%}}) |

### Diseño
| Nombre | Especialidad | Tickets Asignados |
|--------|-------------|-------------------|
| {{NOMBRE}} | UI/Product Designer | {{N}} tickets |

### Desarrollo
| Nombre | Especialidad | Tickets Asignados |
|--------|-------------|-------------------|
| {{NOMBRE}} | Frontend Lead | {{N}} USs |
| {{NOMBRE}} | Backend / Fullstack | {{N}} USs |

### QA
| Nombre | Rol |
|--------|-----|
| {{NOMBRE}} | QA Engineer |

---

## 3. FLUJO DE ESTADOS DE UN TICKET

```
{{ESTADO_1}} → {{ESTADO_2}} → {{ESTADO_3}} → {{ESTADO_FINAL}}
```

> Adapta estos estados a los de tu tablero Jira.

**Tasa de finalización:** {{N_FINALIZADAS}} / {{TOTAL}} = {{%}}%

---

## 4. ÁREAS TEMÁTICAS DEL PRODUCTO

| Área | # Tickets | Descripción |
|------|-----------|-------------|
| {{ÁREA_1}} | {{N}} | {{Descripción breve}} |
| {{ÁREA_2}} | {{N}} | {{Descripción breve}} |
| {{ÁREA_3}} | {{N}} | {{Descripción breve}} |

---

## 5. ÉPICAS IDENTIFICADAS

| Épica | Período | Estado |
|-------|---------|--------|
| {{ÉPICA_1}} | {{PERÍODO}} | ✅ Completada |
| {{ÉPICA_2}} | {{PERÍODO}} | 🔄 En progreso |

---

## 6. DECISIONES Y CONVENCIONES DE PRODUCTO

1. {{CONVENCIÓN_1}}  (ej: "La plataforma es 100% Desktop — no hay mobile")
2. {{CONVENCIÓN_2}}  (ej: "Los roles son BASIC y FULL")
3. {{CONVENCIÓN_3}}  (ej: "Design Tasks van siempre al/a la diseñador/a principal")

---

## 7. CONTEXTO DEL SPRINT ACTUAL

Sprint activo: **{{NOMBRE_SPRINT}}**

Tickets recientes (en progreso o recién creados):
- `{{TICKET_KEY}}`: {{Descripción}} ({{Asignado}} – {{Estado}})
- `{{TICKET_KEY}}`: {{Descripción}} ({{Asignado}} – {{Estado}})

---
*Este documento puede ser generado automáticamente por el Agente Meta-Observador
al final de cada pipeline run, o creado manualmente desde un export de Jira.*
