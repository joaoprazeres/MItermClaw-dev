# RAG Architecture Design

## Overview

RAG (Retrieval-Augmented Generation) for project-based knowledge retrieval. Uses the same vector/embedding foundation as Memory.

---

## Core Design

### Project Isolation
Each project gets its own vector index stored inside the project:

```
<project>/
├── .index/
│   ├── embeddings.json   # Vector data
│   └── manifest.json    # Metadata
├── source-files...
└── ...
```

### Why Inside Project?
- Self-contained — move project, index moves with it
- Easy to share with collaborators
- Simple to understand

---

## Supported File Types

### v1.0
- `.md` — Markdown
- `.txt` — Plain text
- `.py` — Python
- `.js` — JavaScript
- `.json` — JSON
- `.yaml` / `.yml` — YAML configs

### Excluded
- Binary files (images, executables)
- Hidden files (starting with `.`)
- Files > 1MB

---

## Chunking Strategy

### Token-based Chunking
- **Chunk size:** 512 tokens
- **Overlap:** 50 tokens
- **Why:** Balances searchability with context preservation

### Alternative (Simpler v1.0)
- By file for small files (< 2KB)
- By paragraphs for larger files

---

## Data Flow

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│ Source Files│───▶│ Chunking     │───▶│ Embedding   │
└─────────────┘    └──────────────┘    └─────────────┘
                                             │
                                             ▼
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│ Query       │◀───│ Similarity   │◀───│ JSON Index  │
└─────────────┘    └──────────────┘    └─────────────┘
```

---

## API Functions

### index_project(project_path, verbose=True)
```python
# Index all supported files in a project
index_project("/path/to/project")
# Creates <project>/.index/
```

### query_project(project_path, query, top_k=5)
```python
# Search project knowledge
results = query_project("/path/to/project", "how does auth work", top_k=5)
# Returns: [{file, chunk, score, line_num}, ...]
```

### list_indexed_projects()
```python
# List all projects with indexes
projects = list_indexed_projects()
```

### get_index_stats(project_path)
```python
# Get index info: file count, chunk count, last updated
stats = get_index_stats("/path/to/project")
```

---

## Example Use Case

### 1. Index a project
```bash
python3 rag.py index ~/openclaw-dev/projects
```

### 2. Query it
```python
results = query_project("~/openclaw-dev/projects", "memory architecture")
# Returns relevant chunks with file paths and line numbers
```

### 3. Use in LLM context
```python
context = "\n\n".join([r['chunk'] for r in results])
prompt = f"Based on this code:\n\n{context}\n\nAnswer: {user_question}"
```

---

## Re-use Memory System

We already built:
- `memory_index.py` — embedding + cosine similarity
- JSON vector storage
- Ollama `nomic-embed-text` integration

RAG will extend this to index files, not just memories.

---

## Implementation Priority

| Priority | Feature | Effort |
|----------|---------|--------|
| 1 | File walker (find all supported files) | 1 hr |
| 2 | Chunker (split files into chunks) | 1 hr |
| 3 | Embed & store in project .index/ | 1 hr |
| 4 | Query function with results | 1 hr |
| 5 | CLI wrapper | 30 min |

---

## Open Questions

- [ ] How to handle file updates? (re-index or incremental)
- [ ] Chunk size tunable per project?
- [ ] Cross-project search? (future)
- [ ] Hybrid keyword + vector search?

---

## Integration with Memory

RAG shares infrastructure with Memory:
- Same embedding model (nomic-embed-text)
- Same vector format (JSON)
- Different collections (memory vs project)

Can potentially query both in one search later.