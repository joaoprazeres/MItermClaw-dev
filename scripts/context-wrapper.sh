#!/usr/bin/env bash
# Context Optimizer Wrapper
# Usage: ./context-wrapper.sh [check|compact|status] [--agent main|daily] [--level 1|2|3]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OPTIMIZER="$SCRIPT_DIR/context_optimizer.py"

AGENT="main"
LEVEL=1
ACTION="check"

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        check|compact|status)
            ACTION="$1"
            ;;
        --agent)
            AGENT="$2"
            shift
            ;;
        --level)
            LEVEL="$2"
            shift
            ;;
        *)
            echo "Unknown: $1"
            exit 1
            ;;
    esac
    shift
done

# Resolve session ID from sessions.json using Python
get_session_id() {
    local sessions_file="$HOME/.openclaw/agents/$AGENT/sessions/sessions.json"
    if [[ ! -f "$sessions_file" ]]; then
        echo "Error: No sessions.json for '$AGENT'" >&2
        exit 1
    fi
    python3 -c "
import json
with open('$sessions_file') as f:
    data = json.load(f)
    for key in data:
        if key.startswith('agent:$AGENT:'):
            print(data[key].get('sessionId', ''))
            break
"
}

SESSION_ID=$(get_session_id)

if [[ -z "$SESSION_ID" ]]; then
    echo "No active session for $AGENT"
    exit 1
fi

case $ACTION in
    check)
        python3 "$OPTIMIZER" --session "$SESSION_ID" --agent "$AGENT" --check
        ;;
    compact)
        python3 "$OPTIMIZER" --session "$SESSION_ID" --agent "$AGENT" --compact --level "$LEVEL"
        ;;
    status)
        echo "Agent: $AGENT"
        echo "Session: $SESSION_ID"
        python3 "$OPTIMIZER" --session "$SESSION_ID" --agent "$AGENT" --check
        ;;
esac