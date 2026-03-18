"""
utils/feedback.py — Human feedback capture and persistence.

Stores PO feedback from ticket review sessions in the reasoning bank.
The Escritor reads this file (via builder.py) to learn PO preferences and
improve future tickets without requiring explicit re-instruction.

Usage:
  save_feedback(...)           → appended immediately after each PO review
  load_recent_feedback(n=10)   → called by builder.py to inject recent N entries
                                 into the Escritor's system prompt (avoids token
                                 bloat from unbounded file growth)
"""
from __future__ import annotations
import sys
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
