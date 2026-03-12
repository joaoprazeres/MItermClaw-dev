# Memory Architecture Design

## Overview

Self-hosted memory system for OpenClaw using local files and embeddings. No external services required.

---

## Memory Types

| Type | Purpose | Retention | Storage |
|------|---------|-----------|---------|
| **Short** | Raw session logs, in-progress work | 24-72 hours | `memory/daily/YYYY-MM-DD.md` |
| **Mid** | Summarized context from daily logs | 7-30 days | `memory/mid/` |
| **Long** | Curated, permanent knowledge | Indefinite | `MEMORY.md` (root) |
| **Named** | Specific entity/context memories | Indefinite | `memory/named/` |

---

## Storage Locations

```
/data/data/com.termux/files/home/.openclaw/workspace/
├── MEMORY.md                    # Long-term curated memory
├── memory/
│   ├── daily/                   # Short-term (raw session logs)
│   │   └── YYYY-MM-DD.md
│   ├── mid/                     # Mid-term (summarized)
│   │   └── YYYY-MM.md           # Monthly summaries
│   └── named/                   # Named entities/contexts
│       ├── project-*.md
│       ├── person-*.md
│       └── topic-*.md
```

---

## File Formats

### Short-term (Daily)

```markdown
# 2026-03-12 — Session Log

## 14:30 — Session Start
- User: "Set up GitHub backup"

## 14:35 — Actions
- Created backup script
- Pushed to MItermClaw-dev

## 14:45 — Session End
- Completed: Yes
- Next: Review PR
```

### Mid-term (Monthly Summary)

```markdown
# 2026-03 — Monthly Summary

## Key Events
- GitHub backup established (Mar 12)
- Planner skill installed (Mar 12)

## Decisions
- Memory architecture: local-first, no external APIs

## People
- joaoprazeres (GitHub)

## Projects
- OpenClaw v1.0 roadmap created
```

### Long-term (MEMORY.md)

```markdown
# MEMORY.md — Curated Long-Term Memory

## Core Knowledge
- OpenClaw runs on Termux (Android)
- Primary user: John
- Workspace: /data/data/com.termux/files/home/.openclaw/workspace/

## Important Decisions
- Memory: Self-hosted using local files + embeddings
- Strategy: Memory first, then Internet, then RAG
```

### Named Memory

```markdown
# Named: MItermClaw

## Type: Project

## Summary
OpenClaw admin assistant running on John's Android device in Termux.

## Key Details
- Language: Node.js
- Skills: project-management-2, coding-agent, etc.
- GitHub: joaoprazeres/MItermClaw

## Related
- [[MItermClaw-workspace]]
- [[MItermClaw-dev]]
```

---

## How Each Memory Type Works

### Short-term (Daily Logs)
- **Auto-created** at session start
- **Append-only** during session
- **Compacted** after 48h → summarize to mid-term
- Contains raw timestamps, actions, decisions

### Mid-term (Monthly)
- **Generated** from short-term (manual or cron)
- **Retention**: Keep 3-6 months, then prune to long-term
- Key events, decisions, people, projects extracted

### Long-term (MEMORY.md)
- **Curated** — manually updated or distilled from mid-term
- **Core knowledge only** — facts, preferences, patterns
- Read at session start (per AGENTS.md)

### Named Memories
- **Explicitly created** when encountering new entities
- **Updated** when new info relevant to entity
- **Referenced** via `[[entity-name]]` links

---

## Summarization Approach

### Daily → Monthly (Short → Mid)

Manual process for v1.0:
1. Review daily files for the month
2. Extract: key events, decisions, people, projects
3. Create `memory/mid/YYYY-MM.md`
4. Archive or delete daily files (optional)

### Future (v1.1+): Automated

```javascript
// Pseudocode for auto-summarization
async function summarizeDailyFiles(month) {
  const dailyFiles = readFiles(`memory/daily/${month}-*.md`);
  const combined = dailyFiles.join('\n');
  
  const prompt = `Summarize this month's activity. Extract:
    - Key events (max 5)
    - Decisions made
    - People mentioned
    - Projects worked on
    
    Keep it concise. Format as markdown.`;
  
  const summary = await llm.complete(combined, prompt);
  await write(`memory/mid/${month}.md`, summary);
}
```

### Monthly → Long-term

Quarterly review:
1. Read recent monthly summaries
2. Update MEMORY.md with permanent knowledge
3. Discard temporary details

---

## Search Mechanism

### v1.0: Simple Text Search

```bash
# Grep-based search
rg -i "keyword" memory/
rg "decision" memory/daily/
```

### v1.1: Embeddings-based (Local)

Use local embedding model (e.g., nomic-embed-text via Ollama):

```javascript
// Search script
const embeddings = require(' embeddings'); // local lib
const fs = require('fs');

async function semanticSearch(query, topK = 5) {
  // Generate embedding for query
  const query embedding = await embeddings.encode(query);
  
  // Score against indexed memories
  const scores = [];
  for (const file of getMemoryFiles()) {
    const content = fs.readFileSync(file);
    const emb = await embeddings.encode(content);
    const score = cosineSimilarity(queryEmbedding, emb);
    scores.push({ file, score });
  }
  
  // Return top K
  return scores.sort((a, b) => b.score - a.score).slice(0, topK);
}
```

### Index Structure

```
memory/.index/
├── embeddings.json    # { file: [embedding vector], ... }
└── manifest.json      # { lastUpdated: timestamp }
```

Re-index when:
- New memory file created
- Existing memory file modified
- Daily (cron job)

---

## Workflow

### Session Start
1. Read `MEMORY.md` (long-term)
2. Read today's `memory/daily/YYYY-MM-DD.md`
3. Optionally read recent mid-term summaries

### During Session
- Append to daily log with timestamps
- Create/update named memories as needed

### Session End
- Finalize daily log entry

### Periodic (Manual for v1.0)
- **Weekly**: Review daily logs, extract notable items
- **Monthly**: Generate mid-term summary
- **Quarterly**: Update MEMORY.md from mid-term

---

## Implementation Priority

| Priority | Feature | Effort |
|----------|---------|--------|
| 1 | Define folder structure | 1 hr |
| 2 | Create naming conventions | 1 hr |
| 3 | Write MEMORY.md template | 1 hr |
| 4 | Script daily → mid summarization | 2 hr |
| 5 | Semantic search with local embeddings | 4 hr |

---

## Open Questions

- Should we use a database (SQLite) instead of pure files?
- How to handle embedding model selection?
- Automatic compaction frequency?
- [[ ]] wiki-style linking — implement now or later?