# OpenClaw Instance Documentation

**Instance:** MItermClaw (main), DevClaw (dev), DailyClaw (daily companion)  
**Last Updated:** 2026-03-13  
**Owner:** John

---

## 🦔 Instance Overview

This is a self-hosted OpenClaw AI assistant instance running on Termux (Android). It features multiple agents with separate workspaces, WhatsApp integration, and custom memory/research capabilities.

---

## 👥 Agents

### MItermClaw (Main)
- **Workspace:** `~/.openclaw/workspace/`
- **Role:** Primary assistant
- **Emoji:** 🦔

### DevClaw (Development)
- **Workspace:** `~/openclaw-dev/`
- **Role:** OpenClaw development & configuration
- **Emoji:** 🛠️

### DailyClaw (Daily Companion)
- **Workspace:** `~/dailyclaw/`
- **Role:** Daily conversation & research buddy
- **Emoji:** 🔍
- **Special:** Long memory for daily conversations, read-only outside workspace
- **Channels:** WhatsApp (all messages route here)

---

## 👑 The God Layer (Model Fallback System)

Priority-based model selection with automatic fallback:

| Priority | Provider | Endpoint | Model | Use Case |
|----------|----------|----------|-------|----------|
| 1 | Local Ollama | http://127.0.0.1:11434 | minimax-m2.5:cloud | Default - everything |
| 2 | Remote Ollama | https://llama.alienubserv.joaoprazeres.pt | phi4-mini:3.8b | API rate limits |
| 3 | Local Ollama (alt) | http://127.0.0.1:11343 | phi4 | Offline/fallback |

**Location:** `~/.openclaw/openclaw.json` → `models.providers`

---

## 🧠 Memory Architecture

### Three-Layer System

| Layer | Purpose | Storage | TTL |
|-------|---------|---------|-----|
| **Short** | Session logs, raw conversation | `memory/daily/YYYY-MM-DD.md` | 24-72h |
| **Mid** | Task context, large documents | `memory/mid/YYYY-MM.md` | 7-30 days |
| **Long** | Curated knowledge, distilled memories | `MEMORY.md` (root) | Years |

### Named Memories
- Entity-specific memories (user preferences, personas)
- Location: `memory/named/*.md`

### Scripts
- `~/openclaw-dev/scripts/memory_index.py` - Vector-based memory search
- Uses `nomic-embed-text` embedding model

---

## 🔍 Internet Access Framework

### Two-Level System

**Level 1: Simple Search**
- SearXNG: `https://searx.alienubserv.joaoprazeres.pt`
- Gemini (fallback): Configured via `openclaw.json`

**Level 2: Research Loop**
```
Query → Search → Fetch → LLM Analyze → Refine → Repeat (max 3x)
```

### Scripts
- `~/openclaw-dev/scripts/internet.py` (~517 lines)
  - Web search via SearXNG/Gemini
  - Content fetching with text extraction
  - Provider fallback (SearXNG → Gemini)
  - Max content limit: 8000 chars per URL

---

## 📚 RAG (Knowledge Retrieval)

### Architecture
- Project-isolated vector indexes
- Index stored inside project: `<project>/.index/embeddings.json`
- Embedding model: `nomic-embed-text`

### Scripts
- `~/openclaw-dev/scripts/rag.py` (~400 lines)

### Commands
```bash
# Index a project
python3 rag.py index ~/project-path

# Query
python3 rag.py query "search terms" --top-k 5
```

### Current Indexes
- `~/openclaw-dev/projects/.index/embeddings.json` (229KB)

---

## 📋 Config Files

| File | Purpose |
|------|---------|
| `~/.openclaw/openclaw.json` | Main config (agents, channels, models) |
| `~/.openclaw/openclaw.json.damaged` | Broken config (reference) |
| `~/.openclaw/openclaw.json.bak.1` | Backup |
| `~/.openclaw/openclaw.json.bak.2` | Old backup |

---

## 📦 GitHub Backup

Three repositories backed up to `github.com/joaoprazeres/`:

| Repo | Contents |
|------|----------|
| MItermClaw | OpenClaw npm module |
| MItermClaw-workspace | Main workspace |
| MItermClaw-dev | Dev workspace |

---

## 🔌 Channels

| Channel | Status | Routes To |
|---------|--------|-----------|
| WebChat | ✅ Default | MItermClaw (main) |
| WhatsApp | ✅ Paired | DailyClaw |
| Telegram | ❌ Not configured | - |
| Discord | ❌ Not configured | - |

---

## 🛠️ Skills Installed

| Skill | Location |
|-------|----------|
| project-management-2 | `~/openclaw-dev/skills/project-management-2/` |

---

## 🔧 Recovery Tools

**Script:** `~/openclaw-dev/scripts/openclaw-recover.sh`

| Option | Description |
|--------|-------------|
| `-d` | Diagnostic (health check) |
| `-g` | Fix gateway |
| `-c` | Fix config (restore from backup) |
| `-o` | Fix broken openclaw command |
| `-a` | Fix all |
| `-b` | Create backup |

---

## 📁 File Locations

| Component | Path |
|-----------|------|
| OpenClaw module | `/data/data/com.termux/files/usr/lib/node_modules/openclaw/` |
| Main config | `~/.openclaw/openclaw.json` |
| Main workspace | `~/.openclaw/workspace/` |
| Dev workspace | `~/openclaw-dev/` |
| Daily workspace | `~/dailyclaw/` |
| Extensions | `~/.openclaw/extensions/` |
| Logs | `~/.openclaw/logs/` |
| Gateway | Port 18789 |

---

## 🚀 Quick Commands

```bash
# Gateway
openclaw gateway status
openclaw gateway restart

# Diagnostic
~/openclaw-dev/scripts/openclaw-recover.sh -d

# Channels
openclaw channels login --channel whatsapp

# WhatsApp pairing
openclaw pairing list whatsapp
openclaw pairing approve whatsapp <CODE>
```

---

*Last updated: 2026-03-13*