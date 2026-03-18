# Contributing to Openspired

Thanks for being here. Openspired is built on a belief: AI should free product people to do more discovery, more definition, more hypothesis validation — not replace the thinking that makes products good. If that resonates with you, we'd love your contribution.

---

## Before you start

Read the README, especially the **Context Discovery Protocol** and **How it works** sections. Understanding the pipeline architecture will make your contribution much more grounded.

---

## Ways to contribute

**Improve an agent** — Each agent lives in `agents/` as a Markdown file. If you have ideas for better prompts, new skills, or improved reasoning patterns, this is the highest-leverage place to contribute. You don't need to know Python for this.

**Add a new integration** — Jira is the first integration. Linear, Notion, Shortcut, GitHub Issues — all are welcome. Integrations live in `engine/utils/`.

**Add language support** — UI strings live in `engine/setup_wizard.py` and `engine/tui.py` in `_T` and `_REVIEW_LABELS` dicts. Adding a new language means adding a dict entry.

**New AI provider** — Providers live in `engine/providers/`. See `base.py` for the interface and `google_prov.py` as a reference implementation.

**Bug reports** — Open an issue with the label `bug`. Include your Python version, provider, and the full error message.

**Workflow templates** — `agents/Workflows/` contains `.md` workflow definitions. New workflows for common PM activities (PRD generation, hypothesis framing, release notes) are very welcome.

---

## Development setup

```bash
git clone https://github.com/Dsegovia98/openspired.git
cd openspired
pip3 install -r requirements.txt
cp .env.example .env
# Add your AI key, then:
python3 engine/tui.py
```

No build step, no compilation. The pipeline is pure Python — you can modify an agent definition or engine file and run immediately.

---

## Code conventions

- **Python**: 3.10+, no external dependencies beyond `rich` and `python-dotenv`. If a new integration needs a library, it goes in `requirements.txt` with a comment explaining why.
- **Agent definitions**: Markdown files in `agents/`. Keep the structure consistent with existing agents — header, role, skills list, guardrails.
- **No hardcoded product knowledge**: `engine/` should be product-agnostic. Everything product-specific belongs in `workspace/` (gitignored) or `templates/`.
- **Graceful degradation**: Any new context layer must fail silently if the file doesn't exist. First-time users should never see an error about missing context.

---

## Pull request checklist

- [ ] I've tested with at least one AI provider
- [ ] New features degrade gracefully when optional config is missing
- [ ] Agent changes don't assume any specific product domain
- [ ] No workspace files or `.env` included in the commit
- [ ] Commit messages describe *what* changed and *why*, not just *how*

---

## Philosophy note

Openspired is a tool for product people, not just developers. When adding features, ask: *would a non-technical PM understand this?* If the answer is no, consider whether the complexity is necessary — or whether it belongs in `engine/` where users never see it.

---

## Questions?

Open a Discussion on GitHub. We'd rather answer a question in public where others can find it than have you stuck.
