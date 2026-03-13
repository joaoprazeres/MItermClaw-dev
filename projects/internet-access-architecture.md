# Internet Access Architecture

## Overview

Two-level internet research system: Simple search + Research loop (reasoning-based).

---

## Available Resources

| Resource | Endpoint | Status |
|----------|----------|--------|
| **Gemini web_search** | Built-in (configured) | ✅ API key in config |
| **SearXNG** | https://searx.alienubserv.joaoprazeres.pt | ✅ Working |
| **Ollama (local)** | 127.0.0.1:11434 | ✅ For reasoning |

---

## Level 1: Simple Search

**Purpose:** Quick answers, single-query lookups.

**Flow:**
```
User query → Search (SearXNG/Gemini) → Return results
```

**Function:**
```python
def simple_search(query, max_results=5):
    # Use SearXNG (self-hosted, free, no rate limits)
    # OR Gemini (already configured)
    # Return: [{title, url, content, score}, ...]
```

**Use cases:**
- Quick fact check
- Find a specific URL
- Instant answers

---

## Level 2: Research Loop

**Purpose:** Deep research with reasoning. Autonomous loop: search → analyze → re-search → refine.

**Flow:**
```
User query
    │
    ▼
┌──────────────────────────────────────┐
│ Loop (max iterations):               │
│  1. Search (SearXNG)                 │
│  2. Read top results (fetch content)│
│  3. LLM analyze: "Do I have enough?" │
│     - Yes → Synthesize answer        │
│     - No → Refine query → Continue   │
└──────────────────────────────────────┘
    │
    ▼
Final answer with sources
```

**Key components:**
1. **Query refinement** — LLM improves search terms based on findings
2. **Content fetching** — Extract relevant content from URLs
3. **Analysis** — LLM decides if more research needed
4. **Synthesis** — Combine findings into coherent answer
5. **Source tracking** — Keep track of all sources for citation

**Function:**
```python
def research_loop(query, max_iterations=3, max_results=5):
    context = []
    for i in range(max_iterations):
        # Search
        results = searxng_search(query)
        
        # Fetch & extract
        content = [fetch_url(r['url']) for r in results[:3]]
        
        # Analyze with LLM
        analysis = llm.analyze(query, context, content)
        
        if analysis['sufficient']:
            return synthesize(context, sources)
        
        # Refine query for next iteration
        query = analysis['refined_query']
        context.append({'iteration': i, 'results': content})
    
    return synthesize(context, sources)  # Max iterations reached
```

---

## Architecture Diagram

```
                    ┌─────────────────┐
                    │   User Query   │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
     ┌─────────────┐               ┌──────────────┐
     │   Simple    │               │   Research   │
     │   Search   │               │     Loop     │
     └──────┬──────┘               └──────┬───────┘
            │                              │
            ▼                              ▼
     ┌─────────────┐               ┌──────────────┐
     │  SearXNG    │               │  Iterations: │
     │  Gemini     │               │  1. Search   │
     └─────────────┘               │  2. Fetch    │
                                   │  3. Analyze  │
                                   │  4. Refine   │
                                   └──────────────┘
```

---

## Implementation Priority

| Priority | Feature | Effort |
|----------|---------|--------|
| 1 | Simple search wrapper (SearXNG) | 30 min |
| 2 | URL content fetcher | 30 min |
| 3 | Research loop with LLM | 1 hr |
| 4 | Query refinement logic | 1 hr |
| 5 | Source tracking & citation | 30 min |

---

## Provider Selection

| Scenario | Provider | Reason |
|----------|----------|--------|
| Simple search | **SearXNG** | Self-hosted, free, no limits |
| Complex research | **SearXNG + Ollama** | Full control |
| Fallback | **Gemini** | Already configured |

---

## Example Usage

### Simple Search
```python
results = simple_search("OpenClaw features")
# Returns: [{title, url, content, score}, ...]
```

### Research Loop
```python
answer = research_loop("What are the latest developments in AI agents?")
# Returns: {answer: "...", sources: [...], iterations: 3}
```

---

## Open Questions

- [ ] Max iterations for research loop?
- [ ] Content fetch timeout?
- [ ] How to handle rate limits?
- [ ] Cache search results?