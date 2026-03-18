<div align="center">

```
 ██████╗ ██████╗ ███████╗███╗   ██╗███████╗██████╗ ██╗██████╗ ███████╗██████╗
██╔═══██╗██╔══██╗██╔════╝████╗  ██║██╔════╝██╔══██╗██║██╔══██╗██╔════╝██╔══██╗
██║   ██║██████╔╝█████╗  ██╔██╗ ██║███████╗██████╔╝██║██████╔╝█████╗  ██║  ██║
██║   ██║██╔═══╝ ██╔══╝  ██║╚██╗██║╚════██║██╔═══╝ ██║██╔══██╗██╔══╝  ██║  ██║
╚██████╔╝██║     ███████╗██║ ╚████║███████║██║     ██║██║  ██║███████╗██████╔╝
 ╚═════╝ ╚═╝     ╚══════╝╚═╝  ╚═══╝╚══════╝╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝╚═════╝
```

**A multi-agent pipeline that turns product requirements into structured Jira tickets — from your terminal.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Providers](https://img.shields.io/badge/AI-Google%20%7C%20Anthropic%20%7C%20OpenAI-blueviolet)](#supported-ai-providers)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**English** · [Español](README_ES.md)

</div>

---

## The belief behind this project

When writing code becomes a commodity, product value concentrates somewhere else: in **understanding the problem deeply**, in **designing the right solution**, and in **the human judgment that decides what to build and why**.

Discovery, definition, hypothesis validation — these are the activities that move products forward and that can't be delegated to automation. Yet most product teams spend a disproportionate amount of time on operational work: structuring tickets, translating requirements into acceptance criteria, documenting what was already decided in a meeting.

**Openspired frees that time.**

Describe what you need in plain language. A pipeline of 9 specialized agents handles the rest — orchestration, research, concept development, writing, QA — and delivers a structured, bilingual ticket ready to ship. Every run teaches the system about your product, so it gets more accurate over time with less input from you.

The goal isn't to replace product thinking. It's to make room for more of it.

---

## What it does

You describe a requirement in plain language (or paste a Jira link). Openspired runs 9 specialized agents in sequence and produces a fully structured, bilingual (EN/ES) ticket ready to review and publish.

Before writing anything, agents look up your product's accumulated context — module history, team conventions, sprint state, ticket template — and write from that base. The less generic your workspace, the more specific and useful the output.

Every approved ticket feeds the system's memory. The Meta-Observer agent updates module context after each run, so your second ticket about a module is sharper than the first, and your tenth is sharper than your fifth.

---

## Quickstart

```bash
# 1. Clone
git clone https://github.com/Dsegovia98/openspired.git
cd openspired

# 2. Install & launch
chmod +x install.sh && ./install.sh
# Installs dependencies and opens the setup wizard automatically.
# The wizard (~5 min) asks for your AI provider key and configures your workspace.
# No files to edit manually.
```

> **Cheapest start:** Google Gemini Flash — a full 9-agent pipeline run costs roughly **$0.01–0.03**.

---

## How it works

```
Your requirement (plain language or Jira URL)
        │
        ▼
  [Orchestrator]    classify domain, module, ticket type
        │
        ▼
  [Researcher]      add product + market context from workspace
        │
        ▼
  [Concept Dev]     build conceptual architecture, anticipate edge cases
        │
        ▼
  [Writer]          produce bilingual EN/ES structured ticket
        │
        ▼
  [QA + Feedback]   validate format, flag gaps, 2–3 critical flows
        │
     ── Human review ──  [approve / feedback / update template / discard]
        │
        ▼
  [Documentor]      save ticket to workspace
        │
        ▼
  [Meta-Observer]   update module context for the next run
        │
        ▼
  Your Jira ticket  (optionally auto-posted)
```

The human review step is where your judgment matters. You approve, give feedback (the Writer revises), or update your ticket template — all before anything touches Jira.

---

## Context Discovery Protocol (CDP)

Agents don't write from zero. Before each run, the pipeline assembles a context stack from your workspace:

| Layer | File | Purpose |
|-------|------|---------|
| 1 | `workspace/modules/{module}/context.md` | Module-specific state — what already exists, active flows, known edge cases |
| 2 | `workspace/context/product_knowledge.md` | General product description and module map |
| 3 | `workspace/context/sprint_context.md` | Current sprint, active epics |
| 4 | `workspace/context/global.md` | Platform, roles, format conventions |
| 5 | `workspace/context/ticket_template.md` | Your team's ticket structure (auto-extracted from Jira or manually defined) |
| 6 | Agent definitions | Skills and instructions specific to each agent |

Missing layers degrade gracefully — agents proceed with what's available and document their assumptions. Each run fills in the gaps for the next one. First-time users get a working pipeline from minute one; experienced users get increasingly precise output.

---

## Workspace is yours

Everything in `workspace/` is gitignored. Your product knowledge, ticket history, team info, and API keys never leave your machine unless you explicitly version them in a separate private repo. Openspired is the engine — you own the fuel.

```
workspace/
├── context/          # global.md, team.md, product_knowledge.md, sprint_context.md,
│                     # ticket_template.md, preferences.md
│                     # .reasoning_bank/ (patterns, anti-patterns, human feedback)
├── modules/          # per-module context — auto-updated by Meta-Observer
├── tickets/          # generated tickets (markdown)
└── logs/             # registry of all tickets created
```

---

## Project structure

```
openspired/
├── engine/           # Python pipeline — config, providers, context builder, TUI
├── agents/           # Agent definitions in Markdown — the intelligence layer
│   ├── 00_Orquestador/
│   ├── 01_Documentador/
│   ├── ...
│   └── Workflows/
├── templates/        # Onboarding templates — rendered into workspace/ on first run
├── workspace/        # Your product context (gitignored)
├── install.sh        # One-command setup
├── .env.example      # Environment template
└── requirements.txt
```

---

## Supported AI providers

| Provider | Model | Est. cost / run | Notes |
|----------|-------|-----------------|-------|
| Google | `gemini-2.5-flash-lite` | ~$0.01–0.02 | Recommended default |
| Google | `gemini-2.5-flash` | ~$0.03–0.05 | Auto-fallback on overload |
| Anthropic | `claude-haiku-4-5` | ~$0.02–0.04 | Strong alternative |
| OpenAI | `gpt-4o-mini` | ~$0.02–0.04 | Solid option |

Set `PROVIDER` and the matching API key in `.env`. No other config needed.

---

## Language support

Openspired runs fully in **English** or **Spanish**. Language is selected during the setup wizard and stored in `workspace/context/preferences.md`. Every UI prompt, generated file, and agent instruction adapts to your choice.

Ticket output is always bilingual (EN + ES) by default — designed for cross-functional teams.

---

## Who this is for

Product managers and designers who want to spend less time structuring tickets and more time on what actually matters: talking to users, defining problems, and deciding what to build next.

You don't need to know how to code to use Openspired. If you can run a terminal command and type a requirement in plain language, you're good.

---

## Contributing

We believe the future of product work is in amplifying human judgment, not replacing it. If that resonates, we'd love your help.

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to get started — there are good first issues for agent improvements, new integrations, and language expansions.

---

## License

[MIT](LICENSE) — use it, fork it, build on it. Ship something good.

---

<div align="center">
<sub>Built by product people who got tired of writing tickets from scratch — and started wondering what they'd do with all that time back.</sub>
</div>
