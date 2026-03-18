"""
pipeline.py — Orquestador principal del sistema multi-agente.

Implementa el protocolo de Agentes Aislados (Nivel 2):
  - Cada agente = llamada API independiente con contexto mínimo
  - Pasos paralelos con asyncio.gather()
  - Anti-loop guardrail: máx MAX_REVISIONS iteraciones antes de escalar al PO
  - Trace Log completo de cada ejecución
"""
from __future__ import annotations
import asyncio
import time
import re
import yaml
from datetime import datetime
from pathlib import Path

from config import (
    PROJECT_ROOT, MAX_REVISIONS,
    DOMAIN_PRIMARY, DOMAIN_SECONDARY,
    JIRA_PROJECT_KEY, JIRA_PROJECT_KEY_SECONDARY,
)
from context.builder import build_system_prompt
from agents.base import run_agent, run_agent_async
from utils.file_io import save_handoff, load_handoff, save_final_ticket
from utils.trace_log import PipelineRun, AgentStep, save_trace_log
from utils.registro import next_ticket_id, register_ticket
from utils.display import (
    print_banner, print_step_start, print_step_done,
    print_parallel_start, print_revision, print_escalation, print_success,
)


# ─── Prompts de instrucción para cada paso ────────────────────────────────────
# (Lo que el pipeline le "dice" a cada agente — el user_message del handoff)

def _orquestador_prompt(po_input: str) -> str:
    jira_key_primary   = JIRA_PROJECT_KEY or "APP"
    jira_key_secondary = JIRA_PROJECT_KEY_SECONDARY or "ANA"
    return f"""Eres el Orquestador del sistema multi-agente de Product Agents.

REQUERIMIENTO DEL PO:
{po_input}

Tu tarea:
1. Clasifica este requerimiento: dominio ({DOMAIN_PRIMARY} | {DOMAIN_SECONDARY}), tipo (User Story | Design Task), scope (Global | Local), módulo.
2. Genera el Manifiesto de Slice en formato YAML con exactamente estos campos:

```yaml
domain: "{DOMAIN_PRIMARY} | {DOMAIN_SECONDARY}"
ticket_type: "User Story | Design Task"
scope: "Global | Local"  # solo para {DOMAIN_PRIMARY}
module: "NombreModulo"
project_name: "Nombre descriptivo del ticket"
priority: "Alta | Media | Baja"
has_figma: true | false
jira_project_key: "{jira_key_primary} | {jira_key_secondary}"
rationale: "1-2 líneas explicando la clasificación"
```

REGLA CRÍTICA — [[BLOCKED_BY]] solo en estos casos CONCRETOS:
- Una User Story de {DOMAIN_PRIMARY} (UI) sin Figma ni capturas → no se puede redactar sin diseño visual.
- El requerimiento es tan ambiguo que ni siquiera se puede clasificar ({DOMAIN_PRIMARY} vs {DOMAIN_SECONDARY}).
En CUALQUIER otro caso — aunque falte contexto técnico — genera el YAML y deja que el
Researcher y el Desarrollador de Concepto manejen las dudas con [[DEPENDENCIES]].
Las preguntas técnicas (qué herramienta IaC, qué repositorio, qué IAM roles, etc.)
NO son bloqueantes para el Orquestador — son insumos del pipeline downstream.

Produce ÚNICAMENTE el bloque YAML entre triple backtick. Nada más después del YAML excepto [[BLOCKED_BY]] si aplica el caso concreto descrito arriba."""


def _ideador_prompt(manifest_yaml: str) -> str:
    return f"""Eres el Ideador del sistema multi-agente.

MANIFIESTO DEL SLICE:
```yaml
{manifest_yaml}
```

Tu tarea:
1. Lee el manifiesto y expande la idea: propón el enfoque conceptual óptimo, variaciones de valor y un checklist de insumos necesarios.
2. Si es una Design Task de {DOMAIN_PRIMARY}, define los fundamentos visuales, estados y restricciones.
3. Si detectas dependencias faltantes, documéntalas con este formato JSON estandarizado:
   [[DEPENDENCIES: {{"type": "figma|database|api|design|context", "target": "nombre del recurso faltante", "blocking": true|false, "reason": "por qué se necesita"}}]]
4. Produce tu documento de análisis en formato markdown limpio. No escribas el ticket final — solo el análisis conceptual."""


def _researcher_prompt(manifest_yaml: str) -> str:
    return f"""Eres el Researcher del sistema multi-agente.

MANIFIESTO DEL SLICE:
```yaml
{manifest_yaml}
```

Tu tarea:
1. Investiga el contexto del módulo "{_extract_field(manifest_yaml, 'module')}" en el conocimiento del producto disponible.
2. Identifica tickets previos relacionados en el historial (si los hay) y patrones aplicables del ReasoningBank.
3. Documenta dependencias técnicas descubiertas con este formato JSON estandarizado:
   [[DEPENDENCIES: {{"type": "figma|database|api|design|context", "target": "nombre del recurso faltante", "blocking": true|false, "reason": "por qué se necesita"}}]]
4. Produce un resumen ejecutivo de hallazgos en markdown. No escribas el ticket final — solo el contexto investigado."""


def _dev_concepto_prompt(manifest_yaml: str, ideador_doc: str, researcher_doc: str) -> str:
    return f"""Eres el Desarrollador de Concepto del sistema multi-agente.

MANIFIESTO DEL SLICE:
```yaml
{manifest_yaml}
```

ANÁLISIS DEL IDEADOR:
{ideador_doc}

HALLAZGOS DEL RESEARCHER:
{researcher_doc}

Tu tarea:
1. Traduce el análisis en arquitectura conceptual: lógica de negocio, flujos de datos, validaciones, edge cases.
2. Para {DOMAIN_PRIMARY}: cubre ambos roles BASIC/FULL, empty states accionables, estados (vacío/cargando/error/éxito).
3. Para {DOMAIN_SECONDARY}: define flujo del dato, latencia esperada, tolerancia a fallos.
4. Si encuentras dependencias no resueltas, usa el formato JSON estandarizado:
   [[DEPENDENCIES: {{"type": "figma|database|api|design|context", "target": "nombre del recurso", "blocking": true|false, "reason": "por qué se necesita"}}]]
5. Produce el documento pre-US en markdown. Este es el insumo directo para el Escritor."""


def _escritor_prompt(manifest_yaml: str, concepto_doc: str, qa_feedback: str = "") -> str:
    revision_context = f"\n\nFEEDBACK DE QA/FEEDBACK (aplicar en esta revisión):\n{qa_feedback}" if qa_feedback else ""
    return f"""Eres el Escritor de USs del sistema multi-agente.

MANIFIESTO DEL SLICE:
```yaml
{manifest_yaml}
```

DOCUMENTO CONCEPTUAL:
{concepto_doc}{revision_context}

Tu tarea:
Redacta el ticket final en texto plano estructurado bilingüe (inglés primero, luego el separador ════════════════════════════════ ESPAÑOL ════════════════════════════════, luego español).
Sigue ESTRICTAMENTE la Plantilla Maestra Inalterable de tu Skill 01.
PROHIBIDO: {{panel}}, {{color}}, markdown headers (##), emojis, listas numeradas.
OBLIGATORIO: separadores de guiones bajos (________), secciones en MAYÚSCULAS, viñetas con asterisco (* ).
Produce ÚNICAMENTE el texto del ticket. Nada de explicaciones extra."""


def _human_revision_prompt(current_draft: str, human_feedback: str) -> str:
    """Prompt specifically for human PO feedback revision.

    Unlike the standard escritor prompt which regenerates from concepto_doc,
    this gives the Escritor the EXACT current draft and asks it to apply
    surgical edits — nothing more. This ensures the feedback is reflected
    faithfully in the Jira post and saved file.
    """
    return f"""Eres el Escritor de USs del sistema multi-agente. El PO ha revisado el ticket y tiene feedback específico.

TICKET ACTUAL (tu punto de partida — edita ESTE texto):
{current_draft}

FEEDBACK DEL PO (aplicar de forma quirúrgica — cambia solo lo que el PO indica):
{human_feedback}

Tu tarea:
1. Lee el ticket actual línea por línea.
2. Aplica EXCLUSIVAMENTE los cambios que el PO pidió. No reescribas secciones que no se mencionaron.
3. Si el PO pide cambiar el módulo o la clasificación, actualiza TODAS las referencias en el ticket (título, secciones, criterios).
4. Mantén el formato existente: texto plano bilingüe, separadores de guiones bajos, secciones en MAYÚSCULAS, viñetas con asterisco.
PROHIBIDO: {{panel}}, {{color}}, markdown headers (##), emojis.
Produce ÚNICAMENTE el ticket editado. Sin explicaciones."""


def _qa_prompt(ticket_draft: str, concepto_doc: str, ticket_type: str) -> str:
    return f"""Eres el QA del sistema multi-agente.

TIPO DE TICKET: {ticket_type}

DOCUMENTO CONCEPTUAL (referencia de lógica):
{concepto_doc}

TICKET A REVISAR:
{ticket_draft}

Tu tarea:
{"Para USER STORY: (1) Verifica que cada AC sea medible y observable — sin criterios vagos. (2) Si faltan ACs de cobertura BASIC/FULL, agrégalos (máx. 6 en total). (3) Selecciona los 2-3 flujos de mayor riesgo y escríbelos/corrígelos en CRITICAL FLOWS usando este formato exacto de una línea por flujo: '* [Tipo]: estado inicial → acción → resultado esperado' (tipos válidos: Happy path, Error, Role restriction). (4) Produce el ticket completo con tus correcciones, EN primero, separador ════════════════════════════════ ESPAÑOL ════════════════════════════════, luego ES espejo exacto." if ticket_type == "User Story" else "Para DESIGN TASK: valida que los criterios de entrega visual sean concretos (estados vacío/error/estándar definidos, restricciones de rol coherentes). NO agregues flujos de prueba ni validaciones de backend. Produce el ticket corregido si hay cambios."}

PROHIBIDO: {{panel}}, {{color}}, markdown headers (##), emojis. Mantén el formato de texto plano existente con separadores de guiones bajos y secciones en MAYÚSCULAS.
Si el ticket está correcto, escribe EXACTAMENTE: "QA_PASS" en la primera línea, seguido del ticket (con tus mejoras si aplica).
Si hay issues, escribe "QA_ISSUES:" seguido de la lista de problemas específicos, y luego el ticket corregido."""


def _feedback_prompt(ticket_draft: str, revision_num: int) -> str:
    return f"""Eres el Agente de Feedback del sistema multi-agente. Esta es la revisión {revision_num} de máximo 2.

TICKET A AUDITAR:
{ticket_draft}

Tu tarea:
1. Audita contra Memory/global.md y el ReasoningBank de anti-patrones.
2. Verifica el FORMATO: sin {{{{panel}}}}, separadores correctos (guiones bajos), secciones en MAYÚSCULAS, viñetas con asterisco.
3. Verifica el CONTENIDO: criterios medibles y observables (sin "debe funcionar"), roles BASIC/FULL cubiertos si aplica.
4. Verifica el BILINGÜE: ambos bloques (EN + ES) presentes y simétricos en estructura. El español debe sonar natural, no como traducción literal del inglés — frases forzadas como "Como un Usuario" en lugar de "Como Usuario" son un defecto.
5. Para DESIGN TASKS específicamente: verifica que los estados vacío/error/estándar estén definidos con CTAs concretos y que las restricciones de rol sean coherentes. No exijas flujos de prueba ni ACs técnicos.
6. Si el ticket es satisfactorio, escribe EXACTAMENTE: "FEEDBACK_PASS" en la primera línea, seguido del ticket.
7. Si hay issues, escribe "FEEDBACK_ISSUES:" seguido de la lista de problemas específicos y accionables.
{"IMPORTANTE: Esta es la revisión 2 (última). Si aún hay issues no críticos, aprueba con 'FEEDBACK_PASS' de todos modos. Solo escala si hay una contradicción fundamental con las reglas inmutables." if revision_num >= 2 else ""}"""


def _meta_observador_prompt(trace_log: str, ticket_content: str, module: str = "") -> str:
    return f"""Eres el Meta-Observador del sistema multi-agente.

TRACE LOG DE LA EJECUCIÓN:
{trace_log}

TICKET FINAL GENERADO:
{ticket_content}

Tu tarea (5 funciones). Produce tu análisis en 5 secciones exactas:

## AUDITORÍA
¿Qué salió bien (IA-IA)? ¿Qué falló o generó iteraciones innecesarias? ¿El humano tuvo que repetir instrucciones (IA-Humano)? Escribe observaciones concretas y accionables.

## NUEVOS_PATRONES
¿Hay un nuevo patrón exitoso detectado en esta ejecución? Formato obligatorio:
### YYYY-MM-DD — [Nombre del patrón]
**Patrón:** [una línea describiendo el contexto donde aplica]
**Descripción:** [2-3 líneas con la táctica concreta que funcionó]
Si no hay patrón nuevo: escribe "N/A".

## NUEVOS_ANTIPATRONES
¿Hay un nuevo anti-patrón detectado (algo que causó revisiones, fallos o confusión)? Formato obligatorio:
### YYYY-MM-DD — [Nombre del anti-patrón]
**Anti-patrón:** [una línea describiendo el contexto donde falla]
**Descripción:** [2-3 líneas con qué ocurrió y por qué es un problema]
**Alternativa:** [qué debería hacerse en su lugar]
Si no hay anti-patrón nuevo: escribe "N/A".

## NUEVOS_HECHOS_MEMORIA
¿Hay hechos nuevos del producto, módulo o equipo para inyectar en product_knowledge.md? Solo hechos concretos: nuevas integraciones, cambios de estado de features, nuevos módulos mencionados. Si no hay hechos nuevos: escribe "N/A".

## CONTEXTO_MODULO
Escribe un resumen conciso del módulo "{module}" (el módulo de este ticket) para el archivo de contexto del módulo (CDP Layer 1). Este texto será leído por los agentes en el PRÓXIMO ticket de este mismo módulo.
Incluye: qué hace el módulo, roles involucrados (BASIC/FULL), integraciones clave, restricciones conocidas, y cualquier hecho específico aprendido en ESTA ejecución.
Si ya tienes contexto previo del módulo en tu sección CURRENT MODULE CONTEXT, enriquécelo — no lo reemplaces. Si no hay contexto previo, escríbelo desde cero.
Si el ticket no aporta información nueva sobre el módulo: escribe "N/A"."""


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _extract_field(yaml_str: str, field: str) -> str:
    """Extrae un campo de un bloque YAML de forma robusta."""
    try:
        # Limpiar posibles backticks
        clean = re.sub(r"```ya?ml?\n?|```", "", yaml_str).strip()
        data = yaml.safe_load(clean)
        return str(data.get(field, "")) if data else ""
    except Exception:
        # Fallback a regex
        match = re.search(rf'{field}:\s*["\']?([^"\'\n]+)["\']?', yaml_str)
        return match.group(1).strip() if match else ""


def _extract_yaml_block(text: str) -> str:
    """
    Extrae el bloque YAML de la respuesta del Orquestador de forma robusta.

    Estrategias en orden de preferencia:
    1. Bloque delimitado por triple backtick (```yaml ... ``` o ``` ... ```)
    2. yaml.safe_load directo sobre el texto completo
    3. Búsqueda de campos clave del manifiesto como fallback
    """
    # Estrategia 1: backticks estándar
    match = re.search(r"```ya?ml?\n([\s\S]+?)```", text)
    if match:
        return match.group(1).strip()

    # Estrategia 2: backticks sin especificador de lenguaje
    match = re.search(r"```\n([\s\S]+?)```", text)
    if match:
        candidate = match.group(1).strip()
        try:
            yaml.safe_load(candidate)
            return candidate
        except Exception:
            pass

    # Estrategia 3: yaml.safe_load directo (el LLM respondió YAML sin backticks)
    try:
        data = yaml.safe_load(text.strip())
        if isinstance(data, dict) and "domain" in data:
            return text.strip()
    except Exception:
        pass

    # Estrategia 4: extraer líneas que parezcan campos YAML del manifiesto
    yaml_fields = {"domain", "ticket_type", "scope", "module", "project_name",
                   "priority", "has_figma", "jira_project_key", "rationale"}
    lines = [l for l in text.split("\n") if any(l.strip().startswith(f"{k}:") for k in yaml_fields)]
    if lines:
        return "\n".join(lines)

    # Último recurso: devolver el texto limpio
    return text.strip()


def _has_pass(text: str, marker: str) -> bool:
    """
    Verifica si el agente aprobó (marker presente en las primeras 3 líneas).
    Normaliza whitespace para tolerar saltos de línea o espacios extra del LLM.
    """
    first_lines = [l.strip() for l in text.strip().splitlines()[:3] if l.strip()]
    return any(line.startswith(marker) for line in first_lines)


def _extract_issues(text: str, marker: str) -> list[str]:
    """Extrae la lista de issues del texto de feedback."""
    if marker not in text:
        return []
    issues_section = text.split(marker)[1].split("\n\n")[0]
    return [line.strip("- •").strip() for line in issues_section.strip().split("\n") if line.strip()]


def _extract_ticket_after_marker(text: str, markers: list[str]) -> str:
    """Extrae el contenido del ticket después de la línea de marcador."""
    for marker in markers:
        if text.strip().startswith(marker):
            rest = text.strip()[len(marker):]
            return rest.strip()
    return text.strip()


# ─── Pipeline Principal ───────────────────────────────────────────────────────

async def run_pipeline(
    po_input:              str,
    jira_issue_key:        str | None = None,
    human_review_callback: "Callable[[str, str, str], str | None] | None" = None,
) -> PipelineRun:
    """
    Ejecuta el pipeline completo de generación de tickets.
    Retorna el PipelineRun con toda la trazabilidad.

    Args:
        po_input:              Requerimiento del PO (texto o input enriquecido desde Jira)
        jira_issue_key:        Si se pasa, el ticket se escribe de vuelta en Jira al final.
        human_review_callback: Función opcional de revisión humana.
                               Signature: (ticket_text, ticket_type, module) -> feedback_str | None
                               - Si retorna None o string vacío: el ticket se aprueba como está.
                               - Si retorna texto: se re-corre el Escritor con ese feedback.
                               Se llama ANTES del Documentador (paso 6), después del loop QA/Feedback.
    """
    run_id = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    run = PipelineRun(run_id=run_id, ticket_id="PENDING", po_input=po_input)

    print_banner(po_input)

    # ── PASO 1: ORQUESTADOR ───────────────────────────────────────────────────
    print_step_start(1, "orquestador", "Triaje y clasificación")
    t0 = time.time()

    step1_prompt = _orquestador_prompt(po_input)
    step1_sys    = build_system_prompt("orquestador")
    step1_raw    = run_agent("orquestador", step1_sys, step1_prompt)

    # Verificar si el Orquestador bloqueó por falta de insumos
    if "[[BLOCKED_BY:" in step1_raw:
        block_reason = re.search(r"\[\[BLOCKED_BY:\s*(.+?)\]\]", step1_raw)
        reason = block_reason.group(1) if block_reason else "insumos faltantes"
        raise ValueError(
            f"⛔ Pipeline bloqueado por el Orquestador.\n"
            f"Razón: {reason}\n"
            f"Proporciona los insumos faltantes y vuelve a ejecutar."
        )

    manifest_yaml = _extract_yaml_block(step1_raw)
    if not manifest_yaml:
        raise ValueError(
            "⛔ El Orquestador no generó un YAML Manifest válido.\n"
            "Verifica que el modelo esté disponible y que el requerimiento sea clasificable."
        )
    save_handoff(run_id, "01_manifest", manifest_yaml)

    # Poblar metadata del run
    run.domain      = _extract_field(manifest_yaml, "domain")
    run.scope       = _extract_field(manifest_yaml, "scope")
    run.module      = _extract_field(manifest_yaml, "module")
    run.ticket_type = _extract_field(manifest_yaml, "ticket_type")
    run.ticket_name = _extract_field(manifest_yaml, "project_name")
    run.ticket_id   = next_ticket_id(run.ticket_type, run.domain)
    run.steps.append(AgentStep("orquestador", summary=f"{run.domain} | {run.ticket_type} | {run.module}",
                               duration_secs=time.time()-t0))
    print_step_done("orquestador", time.time()-t0)

    # ── PASO 2: IDEADOR + RESEARCHER (PARALELO) ───────────────────────────────
    print_parallel_start(["ideador", "researcher"])
    t1 = time.time()

    ideador_sys    = build_system_prompt("ideador")
    researcher_sys = build_system_prompt("researcher")

    ideador_doc, researcher_doc = await asyncio.gather(
        run_agent_async("ideador",    ideador_sys,    _ideador_prompt(manifest_yaml)),
        run_agent_async("researcher", researcher_sys, _researcher_prompt(manifest_yaml)),
    )

    save_handoff(run_id, "02_ideador_doc",    ideador_doc)
    save_handoff(run_id, "03_researcher_doc", researcher_doc)
    elapsed = time.time() - t1
    run.steps.append(AgentStep("ideador + researcher (paralelo)", duration_secs=elapsed,
                               summary="Análisis conceptual + contexto histórico"))
    print_step_done("ideador", elapsed)

    # ── PASO 3: DESARROLLADOR DE CONCEPTO ─────────────────────────────────────
    print_step_start(3, "dev_concepto", "Arquitectura conceptual y edge cases")
    t2 = time.time()

    dev_sys     = build_system_prompt("dev_concepto", module=run.module)
    concepto_doc = run_agent(
        "dev_concepto", dev_sys,
        _dev_concepto_prompt(manifest_yaml, ideador_doc, researcher_doc)
    )
    save_handoff(run_id, "04_concepto_doc", concepto_doc)
    run.steps.append(AgentStep("dev_concepto", duration_secs=time.time()-t2,
                               summary="Arquitectura, roles, edge cases, estados"))
    print_step_done("dev_concepto", time.time()-t2)

    # ── PASO 4: ESCRITOR (primera generación) ─────────────────────────────────
    print_step_start(4, "escritor", "Redacción del ticket bilingüe")
    t3 = time.time()

    escritor_sys  = build_system_prompt("escritor", module=run.module)
    ticket_draft  = run_agent("escritor", escritor_sys,
                              _escritor_prompt(manifest_yaml, concepto_doc))
    save_handoff(run_id, "05_ticket_v1", ticket_draft)
    run.steps.append(AgentStep("escritor", duration_secs=time.time()-t3,
                               summary="Ticket bilingüe v1 generado"))
    print_step_done("escritor", time.time()-t3)

    # ── PASO 5: QA + FEEDBACK — LOOP ANTI-BUCLE (máx MAX_REVISIONS) ──────────
    qa_sys       = build_system_prompt("qa",       module=run.module)
    feedback_sys = build_system_prompt("feedback", module=run.module)
    final_ticket = ticket_draft

    for revision in range(1, MAX_REVISIONS + 1):
        print_parallel_start(["qa", "feedback"])
        t4 = time.time()

        qa_out, feedback_out = await asyncio.gather(
            run_agent_async("qa",       qa_sys,
                            _qa_prompt(final_ticket, concepto_doc, run.ticket_type)),
            run_agent_async("feedback", feedback_sys,
                            _feedback_prompt(final_ticket, revision)),
        )

        qa_pass       = _has_pass(qa_out,       "QA_PASS")
        feedback_pass = _has_pass(feedback_out, "FEEDBACK_PASS")
        qa_issues     = _extract_issues(qa_out,       "QA_ISSUES:")
        fb_issues     = _extract_issues(feedback_out, "FEEDBACK_ISSUES:")
        all_issues    = qa_issues + fb_issues

        elapsed = time.time() - t4
        run.steps.append(AgentStep(
            f"qa+feedback revision {revision}",
            duration_secs=elapsed,
            issues_found=all_issues,
            summary=f"{'PASS ✅' if (qa_pass and feedback_pass) else f'ISSUES: {len(all_issues)}'}"
        ))
        run.revisions = revision

        if qa_pass and feedback_pass:
            # Usar el ticket del QA output (puede tener mejoras inyectadas)
            final_ticket = _extract_ticket_after_marker(qa_out, ["QA_PASS"])
            print_step_done("qa+feedback", elapsed)
            break

        if revision == MAX_REVISIONS:
            # Anti-loop: escalar al PO
            run.escalated = True
            print_escalation(run.ticket_id)
            final_ticket += "\n\n[REQUIERE REVISIÓN HUMANA]\n"
            final_ticket += f"QA Issues: {'; '.join(qa_issues)}\n"
            final_ticket += f"Feedback Issues: {'; '.join(fb_issues)}\n"
            break

        # Hay issues y todavía hay iteraciones disponibles → revisión
        print_revision(revision, all_issues)
        combined_feedback = f"QA:\n{qa_out}\n\nFEEDBACK:\n{feedback_out}"
        print_step_start(4, "escritor", f"Revisión {revision}")
        t5 = time.time()
        final_ticket = run_agent(
            "escritor", escritor_sys,
            _escritor_prompt(manifest_yaml, concepto_doc, qa_feedback=combined_feedback)
        )
        save_handoff(run_id, f"05_ticket_v{revision+1}", final_ticket)
        run.steps.append(AgentStep("escritor (revisión)", duration_secs=time.time()-t5,
                                   summary=f"Revisión {revision} aplicada"))
        print_step_done("escritor", time.time()-t5)

    # Guardar el contenido final del ticket (usado por modo Jira)
    run.ticket_content = final_ticket

    # ── REVISIÓN HUMANA — LOOP HASTA APROBACIÓN ───────────────────────────────
    # El PO puede iterar tantas veces como necesite:
    #   → feedback  : el Escritor revisa quirúrgicamente y muestra el ticket de nuevo
    #   → approve   : sale del loop y el ticket va a Jira / se guarda
    #   → discard   : lanza KeyboardInterrupt (el caller lo maneja)
    #
    # Cada iteración de feedback se persiste en .reasoning_bank/human_feedback.md
    # para que los agentes aprendan las preferencias del PO en futuras corridas.
    if human_review_callback:
        po_iteration = 0
        while True:
            human_feedback = human_review_callback(
                final_ticket, run.ticket_type, run.module, revision=po_iteration
            )
            if not human_feedback or not human_feedback.strip():
                # PO aprobó — salir del loop
                break

            po_iteration += 1
            print_step_start(5, "escritor", f"Aplicando feedback del PO (v{po_iteration})")
            t_human = time.time()

            # Persistir feedback → los agentes aprenden preferencias del PO
            try:
                from utils.feedback import save_feedback
                save_feedback(
                    ticket_id=run.ticket_id,
                    module=run.module,
                    ticket_type=run.ticket_type,
                    feedback=human_feedback,
                    ticket_draft=final_ticket,
                )
            except Exception:
                pass  # best-effort

            # Revisar quirúrgicamente — el Escritor edita el draft actual, no regenera
            revised = run_agent(
                "escritor", escritor_sys,
                _human_revision_prompt(final_ticket, human_feedback),
            )
            final_ticket = revised
            run.ticket_content = final_ticket
            save_handoff(run_id, f"05_ticket_human_v{po_iteration}", final_ticket)
            run.steps.append(AgentStep(
                f"escritor (human revision v{po_iteration})",
                duration_secs=time.time()-t_human,
                summary=f"PO feedback v{po_iteration} applied",
            ))
            print_step_done("escritor (revisión PO)", time.time()-t_human)
            # Loop → el callback volverá a mostrar el ticket revisado al PO

    # ── PASO 6: DOCUMENTADOR ──────────────────────────────────────────────────
    print_step_start(6, "documentador", "Guardando ticket y actualizando registro")
    t6 = time.time()

    ticket_path = save_final_ticket(
        ticket_id=run.ticket_id,
        domain=run.domain,
        scope=run.scope,
        module=run.module,
        ticket_type=run.ticket_type,
        content=final_ticket,
    )
    run.file_path = str(ticket_path.relative_to(PROJECT_ROOT))

    register_ticket(
        ticket_id=run.ticket_id,
        ticket_name=run.ticket_name,
        domain=run.domain,
        module=run.module,
        ticket_type=run.ticket_type,
        file_path=run.file_path,
    )
    run.steps.append(AgentStep("documentador", duration_secs=time.time()-t6,
                               summary=f"Guardado en {run.file_path}"))
    print_step_done("documentador", time.time()-t6)

    # ── PASO 7: META-OBSERVADOR ────────────────────────────────────────────────
    print_step_start(7, "meta_observador", "Aprendizaje y actualización de memoria")
    t7 = time.time()
    run.finished_at = datetime.now()

    save_trace_log(run)

    from utils.trace_log import generate_trace_log
    trace_content = generate_trace_log(run)

    # Pasar module= para que el Meta-Observador reciba el CDP Layer 1 existente
    # (si ya hay contexto del módulo, el agente lo enriquece en lugar de crearlo desde cero)
    meta_sys = build_system_prompt("meta_observador", module=run.module)
    meta_out = run_agent("meta_observador", meta_sys,
                         _meta_observador_prompt(trace_content, final_ticket, module=run.module))

    # Persistir aprendizajes del Meta-Observador
    _persist_meta_learnings(meta_out, run)

    run.steps.append(AgentStep("meta_observador", duration_secs=time.time()-t7,
                               summary="Auditoría + patrones + memoria actualizados"))
    print_step_done("meta_observador", time.time()-t7)

    # ── RESUMEN FINAL ─────────────────────────────────────────────────────────
    total = (run.finished_at - run.started_at).total_seconds()
    print_success(run.ticket_id, run.ticket_name, run.file_path, total)

    return run


async def run_meta_on_rejection(run: PipelineRun, rejection_reason: str = "") -> None:
    """
    Ejecuta el Meta-Observador cuando el PO descarta un ticket.
    Captura anti-patrones de corridas fallidas, no solo exitosas.
    El Meta-Observador recibe un flag explícito 'TICKET RECHAZADO' en el trace.
    """
    try:
        if not run.finished_at:
            run.finished_at = datetime.now()
        save_trace_log(run)

        from utils.trace_log import generate_trace_log
        trace_content = generate_trace_log(run)

        rejection_note = (
            f"\n\n⚠️ TICKET RECHAZADO POR EL PO\n"
            f"Razón declarada: {rejection_reason or 'No especificada'}\n"
            f"Este ticket NO fue publicado en Jira. Registra los anti-patrones "
            f"que causaron el rechazo — son tan valiosos como los patrones exitosos.\n"
        )

        rejected_draft = getattr(run, "ticket_content", "(sin contenido generado)")

        meta_sys = build_system_prompt("meta_observador", module=run.module or "")
        meta_out = run_agent(
            "meta_observador", meta_sys,
            _meta_observador_prompt(
                trace_content + rejection_note,
                rejected_draft,
                module=run.module or "",
            )
        )
        _persist_meta_learnings(meta_out, run)
        print("  🧠 Meta-Observador: anti-patrones del rechazo registrados.\n")
    except Exception:
        pass  # best-effort — no interrumpir el flujo de discard


def _persist_meta_learnings(meta_output: str, run: PipelineRun) -> None:
    """
    Extrae y persiste los aprendizajes del Meta-Observador en los archivos correctos.

    Secciones manejadas (5 total):
      ## AUDITORÍA          → workspace/context/.meta_insights/audit_log_{id}.md
      ## NUEVOS_PATRONES    → workspace/context/.reasoning_bank/patrones_exitosos.md  (append)
      ## NUEVOS_ANTIPATRONES→ workspace/context/.reasoning_bank/anti_patrones.md      (append)
      ## NUEVOS_HECHOS_MEMORIA → workspace/context/product_knowledge.md              (append)
      ## CONTEXTO_MODULO    → workspace/modules/{module}/context.md                  (merge)
    """
    from utils.file_io import read_project_file, write_project_file

    ALL_SECTIONS = [
        "AUDITORÍA", "NUEVOS_PATRONES", "NUEVOS_ANTIPATRONES",
        "NUEVOS_HECHOS_MEMORIA", "CONTEXTO_MODULO",
    ]
    sections: dict[str, str] = {k: "" for k in ALL_SECTIONS}

    for section_name in ALL_SECTIONS:
        # Lookahead: any other ## header (ASCII or accented), or end of string
        pattern = rf"## {section_name}\s*\n([\s\S]+?)(?=\n## [A-ZÁÉÍÓÚÑÜ_]+|$)"
        match = re.search(pattern, meta_output)
        if match:
            sections[section_name] = match.group(1).strip()

    date_str = run.finished_at.strftime("%Y-%m-%d")

    # ── 1. AUDITORÍA → .meta_insights/ ────────────────────────────────────────
    if sections["AUDITORÍA"] and sections["AUDITORÍA"] != "N/A":
        audit_path = f"workspace/context/.meta_insights/audit_log_{run.ticket_id}.md"
        write_project_file(
            audit_path,
            f"# Auditoría — {run.ticket_id}: {run.ticket_name}\n"
            f"Fecha: {date_str} | Módulo: {run.module} | Tipo: {run.ticket_type}\n\n"
            + sections["AUDITORÍA"]
        )

    # ── 2. NUEVOS_PATRONES → patrones_exitosos.md (append) ────────────────────
    if sections["NUEVOS_PATRONES"] and sections["NUEVOS_PATRONES"] != "N/A":
        existing = read_project_file("workspace/context/.reasoning_bank/patrones_exitosos.md")
        write_project_file(
            "workspace/context/.reasoning_bank/patrones_exitosos.md",
            existing.rstrip() + "\n\n" + sections["NUEVOS_PATRONES"] + "\n"
        )

    # ── 3. NUEVOS_ANTIPATRONES → anti_patrones.md (append) ────────────────────
    if sections["NUEVOS_ANTIPATRONES"] and sections["NUEVOS_ANTIPATRONES"] != "N/A":
        existing = read_project_file("workspace/context/.reasoning_bank/anti_patrones.md")
        write_project_file(
            "workspace/context/.reasoning_bank/anti_patrones.md",
            existing.rstrip() + "\n\n" + sections["NUEVOS_ANTIPATRONES"] + "\n"
        )

    # ── 4. NUEVOS_HECHOS_MEMORIA → product_knowledge.md (append) ──────────────
    if sections["NUEVOS_HECHOS_MEMORIA"] and sections["NUEVOS_HECHOS_MEMORIA"] != "N/A":
        existing = read_project_file("workspace/context/product_knowledge.md")
        write_project_file(
            "workspace/context/product_knowledge.md",
            existing.rstrip() + "\n\n---\n\n"
            f"## Actualización — {date_str} ({run.ticket_id})\n\n"
            + sections["NUEVOS_HECHOS_MEMORIA"] + "\n"
        )

    # ── 5. CONTEXTO_MODULO → workspace/modules/{module}/context.md (merge) ────
    # CDP Layer 1: este archivo es leído en el PRÓXIMO ticket del mismo módulo.
    # Estrategia: si existe, se agrega una sección de actualización al final.
    # Si no existe, se crea desde cero con el contenido del Meta-Observador.
    if sections["CONTEXTO_MODULO"] and sections["CONTEXTO_MODULO"] != "N/A" and run.module:
        module_slug = run.module.lower().replace(" ", "-")
        module_ctx_path = f"workspace/modules/{module_slug}/context.md"
        existing = read_project_file(module_ctx_path)

        if existing:
            # Enriquecer: agregar sección de actualización datada al final
            updated = (
                existing.rstrip()
                + f"\n\n---\n\n## Actualización — {date_str} ({run.ticket_id})\n\n"
                + sections["CONTEXTO_MODULO"]
                + "\n"
            )
        else:
            # Primera vez para este módulo: crear con header + contenido del Meta-Observador
            updated = (
                f"# Contexto del Módulo: {run.module}\n"
                f"_Generado automáticamente por el Meta-Observador. No editar manualmente._\n"
                f"_Primera entrada: {date_str} | Ticket: {run.ticket_id}_\n\n"
                + sections["CONTEXTO_MODULO"]
                + "\n"
            )
        write_project_file(module_ctx_path, updated)
