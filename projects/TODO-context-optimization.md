# TODO - Context Window Optimization

**Priority:** High  
**Issue:** Frequent "prompt too long; exceeded max context length" errors  
**Target Agents:** MItermClaw, DailyClaw

---

## Problem

Ollama API error 400:
```
prompt too long; exceeded max context length by X tokens
```

The default 128K context fills up during long conversations.

---

## Proposed Solution: Smart Topic-Based Compaction

### Concept
Detect when conversation topic shifts significantly → trigger aggressive compaction or complete purge of old context (from context window only, not from memory files).

### Triggers for Aggressive Compaction

1. **Topic Shift Detection**
   - Semantic similarity check between recent messages vs. earlier messages
   - If similarity < threshold (e.g., 0.3) → topic shift detected

2. **Aggressive Compaction Levels**
   - Level 1: Summarize last N messages (standard)
   - Level 2: Keep only last M messages, summarize rest
   - Level 3: **Complete purge** of old topic from context (but keep in memory file)

3. **Agent-Specific Rules**
   - **MItermClaw**: Light usage, standard compaction
   - **DailyClaw**: Long conversations, smart topic-based compaction
   - **DevClaw**: Handles long tasks, keep full context

### Implementation Ideas

1. **Pre-prompt modification** - Add instruction to detect topic shifts and summarize proactively
2. **Session-level compaction** - Before sending to LLM, check context length and compact if needed
3. **Memory-based approach** - Only keep essential context, rely on memory files for history

---

## Tasks

- [ ] Analyze current memory/compaction system
- [ ] Design topic shift detection (or use LLM to detect)
- [ ] Implement multi-level compaction
- [ ] Test with DailyClaw (long daily conversations)
- [ ] Apply to MItermClaw

---

## Notes

- Don't delete from memory files - only from working context
- Keep conversation summaries in memory for retrieval
- Focus on MItermClaw and DailyClaw (not DevClaw)