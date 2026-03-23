"""
utils/feedback.py — Human feedback capture and persistence.

Stores PO feedback from ticket review sessions in the reasoning bank.
The Escritor reads this file (via builder.py) to learn PO preferences and
improve future tickets without requiring explicit re-instruction.

Usage:
  save_feedback(...)           → appended immediately after each PO review.
                                 Also triggers async rule extraction (fire-and-forget):
                                 the raw feedback is parsed by the LLM into a structured
                                 rule and feedback_rules.md is updated in a background
                                 thread so the NEXT ticket already has the rule.
  load_recent_feedback(n=10)   → called by builder.py to inject recent N entries
                                 into the Escritor's system prompt (avoids token
                                 bloat from unbounded file growth)
  load_feedback_rules()        → called by builder.py to inject distilled rules into
                                 Escritor and QA context at highest priority
"""
from __future__ import annotations
import json
import re
import sys
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


@contextmanager
def _file_lock(path: Path):
    """File lock cross-platform para append atómico."""
    lock_path = path.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    if sys.platform != "win32":
        import fcntl
        with open(lock_path, "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)
    else:
        import time
        max_wait = 10
        waited   = 0.0
        while lock_path.exists() and waited < max_wait:
            time.sleep(0.1)
            waited += 0.1
        lock_path.touch()
        try:
            yield
        finally:
            lock_path.unlink(missing_ok=True)

try:
    from config import WORKSPACE_DIR
except Exception:
    WORKSPACE_DIR = Path(__file__).resolve().parent.parent.parent / "workspace"

_FEEDBACK_FILE = WORKSPACE_DIR / "context" / ".reasoning_bank" / "human_feedback.md"
_RULES_FILE    = WORKSPACE_DIR / "context" / ".reasoning_bank" / "feedback_rules.md"

# Maximum feedback entries injected into agent context (older entries are kept
# in the file for audit purposes but not sent to the LLM to avoid token bloat).
MAX_FEEDBACK_IN_CONTEXT = 10


def save_feedback(
    ticket_id:    str,
    module:       str,
    ticket_type:  str,
    feedback:     str,
    ticket_draft: str,
) -> None:
    """
    Append a feedback entry to the human feedback log.
    Called immediately after the PO gives feedback during ticket review.
    The full log is kept on disk; only the most recent N entries are
    injected into agent context (see load_recent_feedback).
    """
    _FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)

    entry = (
        f"\n\n---\n"
        f"## Feedback — {ticket_id} | {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"**Module:** {module}  |  **Type:** {ticket_type}\n\n"
        f"**PO Feedback:**\n{feedback}\n\n"
        f"**Applied to ticket draft:**\n"
        f"```\n{ticket_draft[:500]}{'...' if len(ticket_draft) > 500 else ''}\n```\n"
    )

    with _file_lock(_FEEDBACK_FILE):
        if _FEEDBACK_FILE.exists():
            with open(_FEEDBACK_FILE, "a", encoding="utf-8") as f:
                f.write(entry)
        else:
            header = (
                "# HUMAN FEEDBACK LOG\n"
                "## Captured from: ticket review sessions | Used by: Escritor agent\n\n"
                "> Every piece of feedback you give during ticket review is stored here.\n"
                "> The Escritor reads the most recent entries to learn your preferences.\n"
            )
            _FEEDBACK_FILE.write_text(header + entry, encoding="utf-8")

    # Fire-and-forget: extract structured rule in background thread.
    # The raw entry is already saved above; this enrichment is best-effort.
    trigger_rule_extraction(
        feedback=feedback,
        ticket_id=ticket_id,
        module=module,
        ticket_type=ticket_type,
        ticket_draft=ticket_draft,
    )


def load_feedback_rules() -> str:
    """
    Load the distilled feedback rules file for agent context injection.

    feedback_rules.md contains structured, actionable rules derived from PO
    feedback — categorized by violation type with violation counts.
    Unlike human_feedback.md (raw prose), this file is optimized for LLM
    instruction: clear rules, no noise.

    Returns empty string if no rules file exists yet.
    """
    if not _RULES_FILE.exists():
        return ""
    return _RULES_FILE.read_text(encoding="utf-8")


def load_recent_feedback(n: int = MAX_FEEDBACK_IN_CONTEXT) -> str:
    """
    Load the N most recent feedback entries for agent context injection.

    Called by builder.py when building the Escritor's system prompt.
    Using the N most recent entries (not the full file) avoids token bloat
    as the log grows — older feedback is preserved on disk for audit but
    not sent to the LLM.

    Returns empty string if no feedback file exists yet (first-time users).
    """
    if not _FEEDBACK_FILE.exists():
        return ""

    content = _FEEDBACK_FILE.read_text(encoding="utf-8")
    entries = content.split("\n\n---\n")

    if len(entries) <= 1:
        return ""

    # entries[0] is the header, entries[1:] are the actual feedback records
    records = entries[1:]
    recent  = records[max(0, len(records) - n):]
    return "\n\n---\n".join(recent)


# ─── Rule extraction (async, fire-and-forget) ─────────────────────────────────

_RULE_EXTRACTION_PROMPT = """\
You are a feedback analyst. A PO (Product Owner) has given feedback on a ticket draft.
Your job: extract ONE structured rule from this feedback and return it as JSON.

RULES FILE (current state — use to check if rule already exists):
{rules_content}

PO FEEDBACK:
{feedback}

TICKET CONTEXT (module: {module}, type: {ticket_type}):
{ticket_snippet}

Extract the PRIMARY rule violation this feedback is correcting. Return ONLY valid JSON:
{{
  "rule_name": "Short name in CAPS (e.g. NEVER_SKELETON_LOADERS)",
  "rule_text": "One clear sentence: what to NEVER do. Start with NEVER or ALWAYS.",
  "evidence": "Ticket ID + direct quote from PO feedback (max 100 chars)",
  "is_new": true or false  // false if a rule with the same name already exists in the rules file
}}

If the feedback is too vague to extract a clear rule, return: {{"skip": true}}
Return ONLY the JSON object. No explanation."""


def _extract_rule_background(
    feedback:     str,
    ticket_id:    str,
    module:       str,
    ticket_type:  str,
    ticket_draft: str,
) -> None:
    """
    Background thread: call LLM to extract a structured rule from raw PO feedback,
    then update feedback_rules.md immediately.

    Fails silently — raw feedback is already saved, this is best-effort enrichment.
    """
    try:
        # Import here to avoid circular imports at module load time
        from agents.base import run_agent

        rules_content = load_feedback_rules() or "(no rules yet)"
        ticket_snippet = ticket_draft[:300]

        prompt = _RULE_EXTRACTION_PROMPT.format(
            rules_content=rules_content[:2000],  # cap to avoid token bloat
            feedback=feedback,
            module=module,
            ticket_type=ticket_type,
            ticket_snippet=ticket_snippet,
        )

        raw = run_agent(
            agent_name="feedback",   # uses DEFAULT_MODEL — cheapest available
            system_prompt="You are a feedback analyst. Return only valid JSON.",
            user_message=prompt,
            max_tokens=512,
        )

        # Parse JSON — handle markdown fences if model wraps it
        clean = re.sub(r"```json\s*|```", "", raw).strip()
        data = json.loads(clean)

        if data.get("skip"):
            return

        rule_name  = str(data.get("rule_name", "")).strip().upper()
        rule_text  = str(data.get("rule_text", "")).strip()
        evidence   = str(data.get("evidence",  "")).strip()
        is_new     = bool(data.get("is_new", True))

        if not rule_name or not rule_text:
            return

        _upsert_rule(rule_name, rule_text, evidence, ticket_id, is_new)

    except Exception:
        pass  # never surface errors from background enrichment


def _upsert_rule(
    rule_name: str,
    rule_text:  str,
    evidence:   str,
    ticket_id:  str,
    is_new:     bool,
) -> None:
    """
    Add a new rule or increment the violation count of an existing one.
    Uses the same file lock as save_feedback for safety.
    """
    _RULES_FILE.parent.mkdir(parents=True, exist_ok=True)

    with _file_lock(_RULES_FILE):
        content = _RULES_FILE.read_text(encoding="utf-8") if _RULES_FILE.exists() else ""

        # Find existing rule block by name
        pattern = rf"(## REGLA \d+ — {re.escape(rule_name)} \[VIOLACIONES: )(\d+)(\])"
        match = re.search(pattern, content)

        if match:
            # Increment violation count
            new_count = int(match.group(2)) + 1
            content = content[:match.start(2)] + str(new_count) + content[match.end(2):]
            # Append evidence line after the existing Evidence line
            evidence_line = f"\n**Evidencia adicional ({ticket_id}):** {evidence}"
            # Insert after first "**Evidencia:" line within this rule block
            ev_match = re.search(r"\*\*Evidencia[^*]*\*\*:[^\n]*", content[match.start():])
            if ev_match:
                abs_pos = match.start() + ev_match.end()
                content = content[:abs_pos] + evidence_line + content[abs_pos:]
        else:
            # Count existing rules to assign number
            existing = len(re.findall(r"^## REGLA \d+", content, re.MULTILINE))
            rule_num = existing + 1
            new_block = (
                f"\n---\n\n"
                f"## REGLA {rule_num} — {rule_name} [VIOLACIONES: 1]\n"
                f"**Regla:** {rule_text}\n"
                f"**Evidencia ({ticket_id}):** {evidence}\n"
                f"**Aplica a:** Todos los tickets.\n"
            )
            content = content.rstrip() + "\n" + new_block

        _RULES_FILE.write_text(content, encoding="utf-8")


def trigger_rule_extraction(
    feedback:     str,
    ticket_id:    str,
    module:       str,
    ticket_type:  str,
    ticket_draft: str,
) -> None:
    """
    Launch rule extraction in a background daemon thread.
    Called by save_feedback() — non-blocking, fails silently.
    """
    t = threading.Thread(
        target=_extract_rule_background,
        args=(feedback, ticket_id, module, ticket_type, ticket_draft),
        daemon=True,
    )
    t.start()
