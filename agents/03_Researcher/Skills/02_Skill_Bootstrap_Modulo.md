# Skill: Bootstrap de Módulo
## Agente: Researcher
## Cuándo usar: Cuando el Manifiesto indica `has_module_history: false` — el módulo no tiene context.md en el workspace.

---

## Objetivo
Construir contexto suficiente sobre un módulo desconocido **antes** de que Dev Concepto y Escritor corran, evitando que estos agentes tengan que trabajar completamente a ciegas.

Un módulo sin historia no es un bloqueante — es una señal para activar este skill.

---

## Protocolo de Bootstrap

### Paso 1 — Buscar en el historial local
Antes de ir a Jira, revisa los archivos locales disponibles:
- `workspace/context/product_knowledge.md` — ¿menciona el módulo?
- `workspace/logs/_Registro.md` — ¿hay tickets previos de este módulo?
- `workspace/context/Contexto_Historico_Proyecto.md` — ¿hay contexto histórico relevante?

Si encuentras información, úsala como base. Si no, continúa con Paso 2.

### Paso 2 — Bootstrap desde Jira (si está configurado)
Si el pipeline está en modo Jira (`jira_project_key` presente en el Manifiesto), el sistema ya habrá traído los tickets siblings de la épica. Revisa la sección `EPIC SIBLINGS` del contexto enriquecido del issue.

Si no hay siblings disponibles y tienes acceso a Jira, puedes indicar en tu output el JQL de búsqueda recomendado para que el PO consulte manualmente:

```
JQL sugerido: project = {jira_project_key} AND labels = "{module}" ORDER BY created DESC
JQL alternativo: project = {jira_project_key} AND text ~ "{module}" AND issuetype in (Story, "User Story") ORDER BY updated DESC
```

### Paso 3 — Construir el contexto de bootstrap
Con lo que hayas encontrado (local + Jira siblings si aplica), construye un resumen estructurado del módulo:

```markdown
## Bootstrap de Módulo: {NombreModulo}

**Estado:** Primer ticket para este módulo — sin historial previo.

**Lo que sé del módulo** (fuentes: [product_knowledge | Jira siblings | nada]):
- Propósito aparente: [qué parece hacer el módulo según las fuentes disponibles]
- Usuarios involucrados: [roles mencionados]
- Integraciones conocidas: [otros módulos o sistemas mencionados]
- Patrones detectados: [si hay tickets similares, qué patrones usan]

**Supuestos de baseline** (a confirmar):
- [Supuesto 1]
- [Supuesto 2]

**Gaps detectados** (sin información):
- [Gap 1: ej. no hay referencia de la UI actual]
- [Gap 2: ej. no se conocen los roles específicos de este módulo]

**Recomendación para Dev Concepto y Escritor:**
Trabajar con lenguaje direccional dado el nivel de contexto disponible (has_module_history: false).
```

### Paso 4 — Documentar para el Meta-Observador
Al final de tu output, incluye una nota explícita:
```
[BOOTSTRAP_NOTE] Módulo nuevo: {NombreModulo}. El Meta-Observador debe crear
workspace/modules/{module-slug}/context.md al finalizar esta corrida con el contexto
generado en esta ejecución.
```

---

## Reglas del skill

- **No bloquees el pipeline:** Este skill nunca produce un `[[BLOCKED_BY]]`. Si no hay información, documenta el gap y avanza.
- **Documenta los supuestos:** Lo que asumes sin evidencia debe estar explícito. Los agentes downstream lo usarán como baseline.
- **Un bootstrap parcial es mejor que nada:** Incluso 2-3 hechos sobre el módulo mejoran la calidad de los agentes siguientes.
- **El Meta-Observador cerrará el ciclo:** Tu output de bootstrap se convierte en el primer context.md del módulo. Escríbelo pensando en el próximo Researcher que llegue a este módulo.
