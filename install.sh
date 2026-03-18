#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  Openspired — One-command installer
#  Run: bash install.sh
# ═══════════════════════════════════════════════════════════════

set -e

# Always run from the directory where this script lives
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Cross-platform sed: macOS requires -i '', Linux requires -i
_sed_inplace() {
    if sed --version 2>/dev/null | grep -q GNU; then
        sed -i "$@"
    else
        sed -i '' "$@"
    fi
}

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
DIM='\033[2m'
BOLD='\033[1m'
RESET='\033[0m'

clear

echo ""
echo -e "${CYAN}${BOLD}"
echo '  ██████╗ ██████╗ ███████╗███╗   ██╗███████╗██████╗ ██╗██████╗ ███████╗██████╗ '
echo ' ██╔═══██╗██╔══██╗██╔════╝████╗  ██║██╔════╝██╔══██╗██║██╔══██╗██╔════╝██╔══██╗'
echo ' ██║   ██║██████╔╝█████╗  ██╔██╗ ██║███████╗██████╔╝██║██████╔╝█████╗  ██║  ██║'
echo ' ██║   ██║██╔═══╝ ██╔══╝  ██║╚██╗██║╚════██║██╔═══╝ ██║██╔══██╗██╔══╝  ██║  ██║'
echo ' ╚██████╔╝██║     ███████╗██║ ╚████║███████║██║     ██║██║  ██║███████╗██████╔╝ '
echo '  ╚═════╝ ╚═╝     ╚══════╝╚═╝  ╚═══╝╚══════╝╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝╚═════╝ '
echo -e "${RESET}"
echo -e "  ${DIM}Multi-agent pipeline · Requirements → Jira tickets${RESET}"
echo ""
echo -e "  ${DIM}──────────────────────────────────────────────────${RESET}"
echo ""

# ── 1. Check Python ────────────────────────────────────────────────────────────
echo -e "  Checking Python..."

if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo -e "  ${RED}✗  Python not found.${RESET}"
    echo -e "     Install Python 3.10+ from: ${CYAN}https://python.org/downloads${RESET}"
    exit 1
fi

PYTHON_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MINOR=$($PYTHON -c "import sys; print(sys.version_info.minor)")
PYTHON_MAJOR=$($PYTHON -c "import sys; print(sys.version_info.major)")

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    echo -e "  ${RED}✗  Python $PYTHON_VERSION found, but 3.10+ is required.${RESET}"
    echo -e "     Download: ${CYAN}https://python.org/downloads${RESET}"
    exit 1
fi

echo -e "  ${GREEN}✓  Python $PYTHON_VERSION${RESET}"

# ── 2. Install dependencies ────────────────────────────────────────────────────
echo ""
echo -e "  Installing dependencies..."
$PYTHON -m pip install -r requirements.txt --quiet --disable-pip-version-check
echo -e "  ${GREEN}✓  Dependencies installed${RESET}"

# ── 3. Create .env if it doesn't exist ────────────────────────────────────────
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "  ${GREEN}✓  Created .env${RESET}"
else
    echo -e "  ${GREEN}✓  .env already exists${RESET}"
fi

# ── 4. Create workspace directories ───────────────────────────────────────────
mkdir -p workspace/context/.reasoning_bank
mkdir -p workspace/modules
mkdir -p workspace/tickets
mkdir -p workspace/logs/pipeline_runs
echo -e "  ${GREEN}✓  Workspace ready${RESET}"

# ── 5. Collect AI provider key ─────────────────────────────────────────────────
# Check if a key is already set (non-placeholder value)
GOOGLE_KEY=$(grep -E '^GOOGLE_API_KEY=' .env | cut -d= -f2 | tr -d ' ')
ANTHROPIC_KEY=$(grep -E '^ANTHROPIC_API_KEY=' .env | cut -d= -f2 | tr -d ' ')
OPENAI_KEY=$(grep -E '^OPENAI_API_KEY=' .env | cut -d= -f2 | tr -d ' ')

HAS_KEY=false
if [[ "$GOOGLE_KEY" != "" && "$GOOGLE_KEY" != "AIza..." ]]; then HAS_KEY=true; fi
if [[ "$ANTHROPIC_KEY" != "" && "$ANTHROPIC_KEY" != "sk-ant-..." ]]; then HAS_KEY=true; fi
if [[ "$OPENAI_KEY" != "" && "$OPENAI_KEY" != "sk-..." ]]; then HAS_KEY=true; fi

if [ "$HAS_KEY" = false ]; then
    echo ""
    echo -e "  ${DIM}──────────────────────────────────────────────────${RESET}"
    echo ""
    echo -e "  ${BOLD}AI Provider${RESET}"
    echo -e "  ${DIM}Pick one — you only need one key to get started.${RESET}"
    echo ""
    echo -e "  ${CYAN}[1]${RESET}  Google Gemini Flash   ${DIM}~\$0.01–0.02 / run · free tier available${RESET}  ${YELLOW}← recommended${RESET}"
    echo -e "  ${CYAN}[2]${RESET}  Anthropic Claude Haiku ${DIM}~\$0.02–0.04 / run${RESET}"
    echo -e "  ${CYAN}[3]${RESET}  OpenAI GPT-4o Mini    ${DIM}~\$0.02–0.04 / run${RESET}"
    echo ""
    printf "  Provider [1]: "
    read PROVIDER_CHOICE
    PROVIDER_CHOICE="${PROVIDER_CHOICE:-1}"

    case "$PROVIDER_CHOICE" in
        2)
            PROVIDER_NAME="anthropic"
            MODEL_NAME="claude-haiku-4-5-20251001"
            KEY_VAR="ANTHROPIC_API_KEY"
            KEY_HINT="https://console.anthropic.com/settings/keys"
            ;;
        3)
            PROVIDER_NAME="openai"
            MODEL_NAME="gpt-4o-mini"
            KEY_VAR="OPENAI_API_KEY"
            KEY_HINT="https://platform.openai.com/api-keys"
            ;;
        *)
            PROVIDER_NAME="google"
            MODEL_NAME="gemini-2.5-flash-lite"
            KEY_VAR="GOOGLE_API_KEY"
            KEY_HINT="https://aistudio.google.com/apikey"
            ;;
    esac

    echo ""
    echo -e "  Get your key at: ${CYAN}${KEY_HINT}${RESET}"
    printf "  Paste your API key (hidden): "
    read -s API_KEY_INPUT
    echo ""

    if [ -n "$API_KEY_INPUT" ]; then
        # Write provider, model, and key to .env
        _sed_inplace "s|^PROVIDER=.*|PROVIDER=${PROVIDER_NAME}|" .env
        _sed_inplace "s|^DEFAULT_MODEL=.*|DEFAULT_MODEL=${MODEL_NAME}|" .env
        _sed_inplace "s|^${KEY_VAR}=.*|${KEY_VAR}=${API_KEY_INPUT}|" .env
        echo -e "  ${GREEN}✓  API key saved${RESET}"
    else
        echo -e "  ${YELLOW}⚠  No key entered — you can add it later in .env${RESET}"
    fi
fi

# ── 6. Done ────────────────────────────────────────────────────────────────────
echo ""
echo -e "  ${DIM}──────────────────────────────────────────────────${RESET}"
echo ""
echo -e "  ${GREEN}${BOLD}✅  Ready to go!${RESET}"
echo ""
echo -e "  ${BOLD}Start Openspired:${RESET}"
echo ""
echo -e "    ${BOLD}${CYAN}$PYTHON engine/tui.py${RESET}"
echo ""
echo -e "  ${DIM}Once inside, select [0] Setup to configure your product workspace (~5 min).${RESET}"
echo ""
