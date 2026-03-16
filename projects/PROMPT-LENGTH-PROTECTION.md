# Prompt Length Protection System

Implemented: 2026-03-16 | Updated: 2026-03-16

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
- **NEW:** Generates summaries of truncated context for preservation

**Location:** `~/openclaw-dev/scripts/prompt-length-guard.js`

### 2. Ollama Proxy (`ollama-proxy.js`)

A proxy server that intercepts Ollama API calls:
- Listens on port 11435
- Sanitizes prompts before forwarding to actual Ollama (11434)
- Logs truncation events
- **NEW:** Saves truncated contexts to disk + injects summaries into system prompt

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

## How It Works

```
User Message → OpenClaw → Proxy (11435) → Sanitize → Ollama (11434)
                            ↓
                    Truncate if needed
                    Save to disk + inject summary
```

## Truncation Preservation (NEW - 2026-03-16)

When messages are truncated, the system now:

1. **Generates a summary** of what was cut (1-2 sentences)
2. **Saves to disk** at `~/.openclaw/truncated-contexts/{session_id}_{timestamp}.json`
3. **Injects into system prompt** so the LLM knows what context it lost

Example saved file:
```json
{
  "session_id": "main",
  "truncated_at": "2026-03-16T22:28:00.000Z",
  "summary": "50 messages were removed (25 user, 25 assistant). Topics: User message 0...; Response number 0...",
  "messages_removed": 50,
  "model": "minimax-m2.5:cloud",
  "context_window": 128000
}
```

The LLM receives a `[CONTEXT TRUNCATION NOTICE]` block in its system prompt when truncation occurs.

## Provider Coverage

| Provider | Protected by Proxy? |
|----------|-------------------|
| Ollama (localhost) | ✅ Yes - all calls go through 11435 |
| OpenRouter | ❌ No - bypasses proxy |
| Google Direct | ❌ No - bypasses proxy |

**Current Agent Configuration:**
- main → Ollama ✅
- daily → Ollama ✅
- tutorclaw → Ollama ✅
- dev → Ollama ✅
- research → Ollama ✅

## Configuration

All agents use the proxy (port 11435 instead of 11434):

```json
{
  "models": {
    "providers": {
      "ollama": {
        "baseUrl": "http://127.0.0.1:11435"
      }
    }
  }
}
```

## Auto-Start

The proxy is set up to auto-start on boot via cron job:

- **Script:** `~/.config/openclaw/scripts/start-ollama-proxy.sh`
- **Cron:** Runs every 5 minutes to ensure proxy is running

## Files Created/Modified

### Created
- `scripts/prompt-length-guard.js` - Core sanitization + truncation summary
- `scripts/ollama-proxy.js` - Proxy server with file storage
- `scripts/llm-wrapper.js` - Optional wrapper for scripts

### Modified
- `scripts/context_optimizer.py` - Tuned thresholds

## Testing

```bash
# Test proxy directly
curl http://localhost:11435/health
# {"status":"ok","proxy":"ollama-proxy"}

# Check truncated contexts
ls -la ~/.openclaw/truncated-contexts/

# Test chat via proxy
curl -X POST http://localhost:11435/api/chat \
  -d '{"model":"minimax-m2.5:cloud","messages":[{"role":"user","content":"hi"}]}'
```

## Notes

- The proxy must be started before OpenClaw gateway
- Existing sessions with >100% context will need to be reset or compacted
- The context_optimizer runs periodically to compact old sessions
- Truncated contexts are preserved on disk for potential recovery