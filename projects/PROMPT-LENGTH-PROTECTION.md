# Prompt Length Protection System

Implemented: 2026-03-16

## Problem

OpenClaw was getting "prompt too long; exceeded max context length" errors from Ollama when session context grew too large.

## Solution

A multi-layered approach:

### 1. Prompt Length Guard (`prompt-length-guard.js`)

Core sanitization module that:
- Estimates token count using character-based heuristics
- Knows context windows for various models
- Compresses prompts by removing redundant preamble
- Truncates messages (FIFO for chat, start+end for docs)

**Location:** `~/openclaw-dev/scripts/prompt-length-guard.js`

### 2. Ollama Proxy (`ollama-proxy.js`)

A proxy server that intercepts Ollama API calls:
- Listens on port 11435
- Sanitizes prompts before forwarding to actual Ollama (11434)
- Logs truncation events

**Location:** `~/openclaw-dev/scripts/ollama-proxy.js`

**Usage:**
```bash
node ~/openclaw-dev/scripts/ollama-proxy.js
```

### 3. Context Optimizer Thresholds (Tuned)

Adjusted `context_optimizer.py` thresholds to trigger compaction earlier:

| Setting | Before | After |
|---------|--------|-------|
| CONTEXT_THRESHOLD | 80% | 60% |
| WARN_THRESHOLD | 50% | 40% |
| ACTION_THRESHOLD | 60% | 50% |

**Location:** `~/openclaw-dev/scripts/context_optimizer.py`

## Configuration

All agents now use the proxy (port 11435 instead of 11434):

| Agent | Config File |
|-------|-------------|
| main | `~/.openclaw/agents/main/agent/models.json` |
| daily | `~/.openclaw/agents/daily/agent/models.json` |
| dev | `~/.openclaw/agents/dev/agent/models.json` |
| research | `~/.openclaw/agents/research/agent/models.json` |
| tutorclaw | `~/.openclaw/agents/tutorclaw/agent/models.json` |

## How It Works

```
User Message → OpenClaw → Proxy (11435) → Sanitize → Ollama (11434)
                            ↓
                    Truncate if needed
                    Log sanitization
```

## Files Created/Modified

### Created
- `scripts/prompt-length-guard.js` - Core sanitization
- `scripts/llm-wrapper.js` - Optional wrapper for scripts
- `scripts/README-llm-guard.md` - Documentation
- `scripts/ollama-proxy.js` - Proxy server

### Modified
- `scripts/context_optimizer.py` - Tuned thresholds
- Agent config files - Changed baseUrl from 11434 to 11435

## Testing

```bash
# Test proxy directly
curl http://localhost:11435/health
# {"status":"ok","proxy":"ollama-proxy"}

# Test chat via proxy
curl -X POST http://localhost:11435/api/chat \
  -d '{"model":"minimax-m2.5:cloud","messages":[{"role":"user","content":"hi"}]}'
```

## Notes

- The proxy must be started before OpenClaw gateway
- Existing sessions with >100% context will need to be reset or compacted
- The context_optimizer runs periodically to compact old sessions