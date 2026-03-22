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

## Download — macOS Desktop App

> The easiest way to use Openspired. No terminal required after the first setup.

**[⬇ Download Openspired for macOS (Apple Silicon + Intel)](https://github.com/Dsegovia98/openspired/releases/latest)**

### Setup (first time, ~5 minutes)

1. **Download** the `.dmg` from the link above
2. **Open** the `.dmg` and drag **Openspired** to your `/Applications` folder
3. **Launch** the app — macOS may warn "unverified developer", go to **System Settings → Privacy & Security → Open Anyway**
4. The app opens and shows the **Ajustes (Settings)** screen automatically on first run
5. **Choose your AI provider** and paste your API key:
   - **Google Gemini** (recommended, cheapest): get a free key at [aistudio.google.com](https://aistudio.google.com) → API Keys
   - **Anthropic Claude**: [console.anthropic.com](https://console.anthropic.com) → API Keys
   - **OpenAI**: [platform.openai.com](https://platform.openai.com) → API Keys
6. **Optional — connect Jira**: fill in Base URL (`https://yourcompany.atlassian.net`), email, and an [Atlassian API token](https://id.atlassian.com/manage-profile/security/api-tokens). Use **"Probar conexión"** to verify.
7. Click **Guardar configuración** — the backend restarts and you're ready

### Your first ticket

1. Click **Nueva US** in the left sidebar
2. Type your requirement in plain language — e.g. *"Add a filter by date range to the analytics dashboard"*
3. Click **Generar** and watch 9 agents work in real time on the **Pipeline** screen
4. When the agents finish, a **review card** appears — read the ticket, approve it or give written feedback
5. If Jira is connected, the ticket is posted automatically on approval

> **Your data stays on your machine.** API keys and all generated tickets are stored in `~/Library/Application Support/com.openspired.desktop/` — never uploaded anywhere.

---

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

# 2. One command: install + run + open UI
chmod +x openspired && ./openspired
```

> **Cheapest start:** Google Gemini Flash — a full 9-agent pipeline run costs roughly **$0.01–0.03**.

### Launcher modes

```bash
./openspired             # default: API + web UI (auto-opens browser)
./openspired --desktop   # API + Tauri desktop window
./openspired --no-open   # useful for remote/SSH sessions
```

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

`workspace/` is gitignored and stores context + runtime logs. Generated tickets are saved in domain folders at the runtime root (for example `App/` or `Analitica/`), which are also gitignored by default in this repo.

```
workspace/
├── context/          # global.md, team.md, product_knowledge.md, sprint_context.md,
│                     # ticket_template.md, preferences.md
│                     # .reasoning_bank/ (patterns, anti-patterns, human feedback)
├── modules/          # per-module context — auto-updated by Meta-Observer
└── logs/             # registry of all tickets created

Runtime root (gitignored by default):
├── App/              # primary-domain generated tickets (US/DT)
└── Analitica/        # secondary-domain generated tickets
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

## Local API + Desktop (new)

Openspired now includes a local API layer for desktop/web UI integration without changing the core pipeline logic.

### Start local API (manual/debug)

```bash
python engine/run.py --serve-api
```

By default it binds to `127.0.0.1:8765` and writes a session token to:

`workspace/logs/.api_token`

### API endpoints

- `POST /runs`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/events` (SSE)
- `POST /runs/{run_id}/review`
- `GET /config/status`
- `POST /setup`
- `GET /artifacts`

### Desktop scaffold

A Tauri + React desktop shell is available in `desktop/`:

```bash
cd desktop
npm install
npm run tauri dev
```

Desktop app now boots the local backend automatically when it opens.
For end users, no extra API terminal is required.

### Build macOS installer (.app + .dmg)

```bash
bash scripts/build-macos-installer.sh
```

Artifacts are generated in `dist/macos/`.

Signed + notarized release:

```bash
# one-time: store Apple credentials in keychain profile
bash scripts/setup-notary-profile.sh openspired-notary

# every release
MACOS_SIGN_IDENTITY="Developer ID Application: YOUR COMPANY (TEAMID1234)" \
MACOS_NOTARY_PROFILE="openspired-notary" \
bash scripts/build-macos-installer.sh --notarize
```

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
