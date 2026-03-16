# LLM Wrapper & Prompt Length Guard

This directory contains tools for protecting LLM calls from "prompt too long" errors.

## Files

- `prompt-length-guard.js` - Core sanitization module (exports `sanitizePrompt`)
- `llm-wrapper.js` - Wrapper that integrates the guard into LLM calls

## Usage

### As a Module

```javascript
const { callLlmWithGuard, sanitizePrompt } = require('./llm-wrapper.js');

// Just sanitize (no LLM call)
const result = sanitizePrompt({
  messages: [{ role: 'user', content: 'Hello' }],
  systemPrompt: 'You are helpful.',
  model: 'minimax-m2.5:cloud'
});
console.log(result.truncated, result.tokensUsed);

// Or wrap an LLM call
const response = await callLlmWithGuard({
  messages: [...],
  systemPrompt: '...',
  model: 'minimax-m2.5:cloud',
  llmCallFn: async (opts) => {
    // Your LLM call logic here
    return await fetchOllama(opts);
  }
});
```

### As CLI

```bash
# Dry run (just see sanitization stats)
node llm-wrapper.js -m '[{"role":"user","content":"Hello"}]' -M phi4-mini -d

# With file input
node llm-wrapper.js -f ./prompt.json -M minimax-m2.5:cloud -d
```

## Integration Points

Since OpenClaw's core is compiled TypeScript without exposed message hooks, the integration options are:

1. **Custom scripts** - Use `llm-wrapper.js` in any scripts that call LLMs
2. **Future plugin** - Could create an OpenClaw plugin if hooks become available
3. **llm-task extension** - The `llm-task` extension could be modified (not recommended - keep pi-ai clean)

## Token Counting

The guard uses character-based estimation (~4 chars/token for English, adjusted for code).
Models with known context windows are pre-configured in `prompt-length-guard.js`.

### Known Context Windows

| Model | Context |
|-------|---------|
| minimax-m2.5:cloud | 128000 |
| phi4-mini | 4096 |
| qwen2.5:7b | 4096 |
| llama3.1:8b | 4096 |
| deepseek-r1:70b | 4096 |
| google/gemini-2.0-flash-001 | 200000 |
| gemini-2.5-flash | 1000000 |

## Strategies

When prompt exceeds context window:

1. **none** - Prompt fits within limits
2. **fifo** - Truncate oldest messages (FIFO)
3. **compress** - Remove redundant preamble from system prompt