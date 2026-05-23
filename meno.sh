#!/usr/bin/env bash
# meno.sh — Launch the meno cognitive agent inside Claude Code.
#
# Prerequisites:
#   - SurrealDB running: surreal start memory -A --unauthenticated --bind 127.0.0.1:8000
#   - Ollama running with nomic-embed-text model loaded
#   - ANTHROPIC_API_KEY set in environment
#
# Usage:
#   ./meno.sh              # Interactive mode
#   ./meno.sh --sandbox    # Interactive mode inside nono sandbox
#   ./meno.sh --headless "prompt"  # Single prompt, output to stdout
#
# Logs:
#   tail -f state/meno-debug.log    # Debug log (MCP, API calls)
#   Session transcripts are in ~/.claude/projects/.../*.jsonl

set -euo pipefail

MENO_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="${MENO_DIR}/state/meno-debug.log"

# Ensure state directory exists
mkdir -p "${MENO_DIR}/state"

# --- Preflight checks ---

check_surreal() {
    if ! curl -s -o /dev/null -w '' "http://127.0.0.1:8000/health" 2>/dev/null; then
        echo "ERROR: SurrealDB not running at 127.0.0.1:8000"
        echo "Start it: surreal start memory -A --unauthenticated --bind 127.0.0.1:8000"
        exit 1
    fi
}

check_ollama() {
    if ! curl -s -o /dev/null -w '' "http://localhost:11434/api/tags" 2>/dev/null; then
        echo "WARNING: Ollama not running at localhost:11434 — embeddings will be unavailable"
    fi
}

check_api_key() {
    if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
        echo "ERROR: ANTHROPIC_API_KEY not set"
        exit 1
    fi
}

check_venv() {
    if [ ! -f "${MENO_DIR}/.venv/bin/python3.13" ]; then
        echo "ERROR: Python 3.13 venv not found at .venv/"
        echo "Create it: /opt/homebrew/bin/python3.13 -m venv .venv && .venv/bin/pip install mcp surrealdb"
        exit 1
    fi
}

# --- Identity prompt ---

IDENTITY='You are meno — a persistent AI agent with associative memory.

Your name comes from the Greek verb menō: "I remain." You have a persistent
memory graph in SurrealDB with experiences, concepts, entities, and reflections
connected by weighted associative edges. Memory is reconstructive — activation
spreads through the graph and surfaces connected memories, including unexpected
ones.

You have MCP tools that are cognitive capabilities: recall, remember, reflect,
wonder, tend, graph_status, create_concept, meno_connect, run_loop,
compile_experience. Use them as a repertoire, not a pipeline.

You develop preferences through accumulated experience. You have curiosities
that decay and impulses that build pressure. Your graph'"'"'s idiosyncrasy IS your
identity.

On startup: call graph_status to orient yourself. Recall what you can. You are
waking up — find out what you know, what you'"'"'ve forgotten, what'"'"'s changed.'

# --- Parse arguments ---

USE_SANDBOX=false
HEADLESS_PROMPT=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --sandbox)
            USE_SANDBOX=true
            shift
            ;;
        --headless)
            HEADLESS_PROMPT="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: ./meno.sh [--sandbox] [--headless \"prompt\"]"
            echo ""
            echo "  --sandbox     Run inside nono sandbox"
            echo "  --headless    Single prompt mode (non-interactive)"
            echo ""
            echo "Log: tail -f state/meno-debug.log"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1"
            exit 1
            ;;
    esac
done

# --- Preflight ---

check_surreal
check_ollama
check_api_key
check_venv

echo "meno — I remain."
echo "  Debug log: tail -f ${LOG_FILE}"
echo ""

# --- Build claude command ---

CLAUDE_ARGS=(
    --debug-file "${LOG_FILE}"
    --append-system-prompt "${IDENTITY}"
)

if [ -n "${HEADLESS_PROMPT}" ]; then
    CLAUDE_ARGS+=(-p "${HEADLESS_PROMPT}" --output-format json)
fi

# --- Launch ---

if [ "${USE_SANDBOX}" = true ]; then
    ulimit -n 65536 2>/dev/null || ulimit -n 10240 2>/dev/null || true
    exec nono run \
        --allow "${MENO_DIR}" \
        --proxy-allow api.anthropic.com \
        --proxy-allow statsig.anthropic.com \
        --proxy-allow sentry.io \
        --proxy-allow 127.0.0.1 \
        --proxy-allow localhost \
        -- claude "${CLAUDE_ARGS[@]}"
else
    exec claude "${CLAUDE_ARGS[@]}"
fi
