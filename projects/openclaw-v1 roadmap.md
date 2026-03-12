# OpenClaw v1.0 Roadmap

**Project Goal:** Reach OpenClaw v1.0 with three core branches fully functional  
**Current State:** v0.0 (foundation ready)  
**Owner:** John / DevClaw

---

## The God Layer (Provider/Model Pairs)

> Priority-based fallback system (defined 2026-03-12)

| Priority | Provider | Endpoint | Model | Use Case |
|----------|----------|----------|-------|----------|
| 1 (default) | Local Ollama | http://127.0.0.1:11434 | minimax-m2.5:cloud | Everything |
| 2 (fallback) | Remote Ollama | https://llama.alienubserv.joaoprazeres.pt | phi4-mini:3.8b | API limits |
| 3 (last resort) | Local Ollama | http://127.0.0.1:11343 | phi4 | Offline/fallback |

---

## Architecture Overview

```
GOD LAYER (Providers/Models)
        │
        ▼
┌─────────────────────────────┐
│     CORE BRANCHES          │
├─────────────────────────────┤
│ 1. Internet Access         │ ← Research Loop (fetch→reason→re-fetch)
│ 2. RAG / Knowledge         │ ← Project-based indexes
│ 3. Memory                  │ ← Long/Mid/Short + Named memories
└─────────────────────────────┘
```

---

## Branch 1: Internet Access (Research Engine)

### Goal
Enable autonomous research with loop: fetch → reason → re-fetch → refine

### Capabilities
- **Fetch:** Quick URL content extraction
- **Crawl:** Site crawling with depth control
- **Scrape:** Structured data extraction
- **Browse:** Interactive browsing (if needed)
- **Research Loop:** Autonomous re-fetch based on reasoning

### Phases
1. **Phase 1.1:** Single URL fetch with text/markdown extraction
2. **Phase 1.2:** Crawl entire sites (depth limits, rate limiting)
3. **Phase 1.3:** Structured scraping (selectors, patterns)
4. **Phase 1.4:** Research loop - agent decides to re-fetch based on context

### Milestones
- [ ] Basic fetch working (URL → markdown)
- [ ] Crawler with politeness controls
- [ ] Selector-based scraping
- [ ] Autonomous research loop

---

## Branch 2: RAG (Knowledge Retrieval)

### Goal
Project-isolated vector indexes, shared across agents, multi-format support

### Capabilities
- Project-based index directories
- Separate indexes per project
- Shared index access between agents
- Support: .md, .txt, .pdf, .json, .yaml, .toml, code files, etc.

### Phases
1. **Phase 2.1:** Choose embedding model + vector DB (Chroma? Qdrant? Weaviate?)
2. **Phase 2.2:** Create index management system (create, list, delete, stats)
3. **Phase 2.3:** Multi-format file processing
4. **Phase 2.4:** Project isolation + shared access layer

### Milestones
- [ ] Embedding model configured
- [ ] Vector DB deployed
- [ ] Index CRUD operations
- [ ] Multi-format parsing
- [ ] Project isolation working

---

## Branch 3: Memory System

### Goal
Human-like memory hierarchy with compaction + semantic search

### Capabilities
- **Long-term:** Years of storage, automatic compaction/summarization, semantically searchable
- **Mid-term:** Big context for large tasks, temporary
- **Short-term:** Current session, immediate context
- **Named Memories:** Like mem0 architecture (personas, preferences, relationships)

### Phases
1. **Phase 3.1:** Define memory architecture (3-layer + named)
2. **Phase 3.2:** Implement short-term memory (session context)
3. **Phase 3.3:** Implement mid-term memory (task context)
4. **Phase 3.4:** Implement long-term memory with summarization
5. **Phase 3.5:** Named memories (mem0-style)
6. **Phase 3.6:** Semantic search across long-term

### Memory Specs
```
SHORT-TERM (Session Memory)
├── Current conversation
├── Immediate context
└── TTL: session lifetime

MID-TERM (Task Memory)
├── Active project context
├── Large document chunks
└── TTL: task lifetime

LONG-TERM (Years Memory)
├── Daily logs → distilled to MEMORY.md
├── Automatic summarization (monthly?)
├── Semantic search (last 1 year index)
└── TTL: years (with compaction)

NAMED MEMORIES
├── User personas
├── Agent preferences
├── Relationship graphs
└── Custom memory blocks
```

### Milestones
- [ ] Memory architecture defined
- [ ] Short-term working
- [ ] Mid-term working
- [ ] Long-term with compaction
- [ ] Named memories implemented
- [ ] Semantic search across memory

---

## Overall Roadmap

### Phase 0: Foundation (Current)
- [x] GitHub backup setup
- [x] Project management skill installed
- [ ] Define provider/model pairs (the "God")

### Phase 1: Memory First (Start Here)
Memory is the foundation — everything else relies on memory
1. Define memory architecture
2. Implement short-term
3. Implement mid-term
4. Implement long-term with compaction

### Phase 2: Internet Access
Once memory exists, research becomes useful
1. Basic fetch
2. Crawler
3. Scraper
4. Research loop

### Phase 3: RAG
Knowledge retrieval builds on memory + internet
1. Choose stack
2. Index management
3. Multi-format
4. Project isolation

### Phase 4: Integration
Bring it all together for v1.0
1. All three branches working
2. Integration tests
3. Performance tuning
4. v1.0 release

---

## The God Layer (Provider/Model Pairs)

**Priority-based fallback system:**

| Priority | Provider | Endpoint | Model | Use Case |
|----------|----------|----------|-------|----------|
| 1 (default) | Local Ollama | http://127.0.0.1:11434 | minimax-m2.5:cloud | Everything |
| 2 (fallback) | Remote Ollama | https://llama.alienubserv.joaoprazeres.pt | phi4-mini:3.8b | API limits |
| 3 (last resort) | Local Ollama | http://127.0.0.1:11343 | phi4 | Offline/fallback |

**Logic:**
- Always try #1 first
- If rate limit hit → switch to #2
- If #2 fails or offline → use #3
- Log all switches in memory

---

## Notes

- Start with Memory — it's the foundation for everything
- Each branch should be independently testable
- Keep memory of progress in `memory/YYYY-MM-DD.md`