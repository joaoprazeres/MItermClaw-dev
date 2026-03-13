# OpenClaw Disaster Recovery Guide

Comprehensive recovery procedures for OpenClaw v1.0 when the system hangs, breaks, or fails to start.

---

## Table of Contents

1. [Quick Health Check](#1-quick-health-check)
2. [Gateway Service Recovery](#2-gateway-service-recovery)
3. [Configuration Recovery](#3-configuration-recovery)
4. [Agent Session Recovery](#4-agent-session-recovery)
5. [Workspace & Memory Recovery](#5-workspace--memory-recovery)
6. [Extensions & Plugins Recovery](#6-extensions--plugins-recovery)
7. [Skills Recovery](#7-skills-recovery)
8. [Custom Scripts Recovery](#8-custom-scripts-recovery)
9. [Complete Reinstall Procedure](#9-complete-reinstall-procedure)
10. [Prevention & Monitoring](#10-prevention--monitoring)

---

## 1. Quick Health Check

Run these commands to diagnose the current state:

```bash
# Check if Gateway is running
openclaw gateway status

# Check openclaw command works
openclaw --version
# or: node /path/to/openclaw.mjs --version

# Check config syntax
cat ~/.openclaw/openclaw.json | python3 -m json.tool > /dev/null && echo "Config OK" || echo "Config BROKEN"

# Check disk space
df -h ~/.openclaw

# Check Node.js availability
which node && node --version
```

### Common Quick Fixes

| Symptom | Quick Fix |
|---------|-----------|
| Gateway won't start | `openclaw gateway restart` |
| Config invalid JSON | Restore from backup (see Section 3) |
| Command not found | Reinstall: `npm install -g openclaw` |
| Module errors | Clear cache: `rm -rf ~/.openclaw/node_modules` |

---

## 2. Gateway Service Recovery

The Gateway is the daemon that handles all OpenClaw connections.

### Check Gateway Status

```bash
openclaw gateway status
```

### Recovery Steps

```bash
# Stop Gateway
openclaw gateway stop

# Kill any stuck processes
pkill -f openclaw
pkill -f "node.*openclaw"

# Clear any lock files
rm -f ~/.openclaw/gateway.lock

# Start Gateway fresh
openclaw gateway start

# Verify
openclaw gateway status
```

### Manual Gateway Start (Debug Mode)

```bash
# If Gateway won't start, run in foreground to see errors
cd /data/data/com.termux/files/usr/lib/node_modules/openclaw
node openclaw.mjs gateway start --verbose

# Or use the CLI directly
openclaw gateway start --debug
```

### Gateway Logs

```bash
# View Gateway logs
tail -100 ~/.openclaw/logs/gateway.log

# Watch logs in real-time
tail -f ~/.openclaw/logs/gateway.log
```

---

## 3. Configuration Recovery

OpenClaw stores its main config at `~/.openclaw/openclaw.json`.

### Backup Files

OpenClaw automatically creates backups:
- `~/.openclaw/openclaw.json.bak.1` - Most recent backup
- `~/.openclaw/openclaw.json.bak.2` - Older backup

### Restore from Backup

```bash
# Check which backup is good
cat ~/.openclaw/openclaw.json.bak.1 | python3 -m json.tool > /dev/null && echo "bak.1 OK"
cat ~/.openclaw/openclaw.json.bak.2 | python3 -m json.tool > /dev/null && echo "bak.2 OK"

# Restore from backup
cp ~/.openclaw/openclaw.json.bak.1 ~/.openclaw/openclaw.json

# Restart Gateway
openclaw gateway restart
```

### Restore from .damaged File

If you have a `openclaw.json.damaged` file that contains valid (just formatted differently) config:

```bash
# Validate the damaged file is valid JSON
python3 -c "import json; json.load(open('/data/data/com.termux/files/home/.openclaw/openclaw.json.damaged'))" && echo "Valid"

# If valid, restore it
cp ~/.openclaw/openclaw.json.damaged ~/.openclaw/openclaw.json
```

### Manual Config Fix

If you know what's broken in the config, edit it directly:

```bash
# Make a backup first
cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.backup

# Edit with your editor
nano ~/.openclaw/openclaw.json

# Validate after edit
python3 -m json.tool ~/.openclaw/openclaw.json > /dev/null && echo "Valid JSON"
```

### Known Config Sections to Restore

If you've lost the plugins section, restore this (from damaged file):

```json
"plugins": {
  "entries": {
    "openclaw-web-search": {
      "enabled": true,
      "config": {
        "apiKey": "YOUR-API-KEY-HERE"
      }
    }
  },
  "installs": {
    "openclaw-web-search": {
      "source": "npm",
      "spec": "@ollama/openclaw-web-search",
      "installPath": "/data/data/com.termux/files/home/.openclaw/extensions/openclaw-web-search",
      "version": "0.1.7"
    }
  }
}
```

---

## 4. Agent Session Recovery

### View Active Sessions

```bash
# List all sessions
openclaw sessions list

# Or use the API directly
ls -la ~/.openclaw/agents/
```

### Kill Stuck Sessions

```bash
# Find stuck session ID from sessions list
openclaw sessions kill <SESSION-ID>

# Or kill all sessions
pkill -f "openclaw.*agent"
```

### Clear Session History (Nuclear Option)

```bash
# Stop Gateway first
openclaw gateway stop

# Clear session data
rm -rf ~/.openclaw/agents/*/sessions/*
rm -rf ~/.openclaw/subagents/*

# Restart Gateway
openclaw gateway start
```

### Session Database Location

```
~/.openclaw/agents/
├── main/
│   └── sessions/
│       └── <session-id>.jsonl
└── (other agents)

~/.openclaw/subagents/
```

---

## 5. Workspace & Memory Recovery

Your workspace contains your agent's memory and working files.

### Workspace Locations

| Workspace | Location | Purpose | Agent |
|-----------|----------|---------|-------|
| Main | `~/.openclaw/workspace/` | Primary agent | MItermClaw 🦔 |
| Dev | `~/openclaw-dev/` | Development | DevClaw 🛠️ |
| Daily | `~/dailyclaw/` | Daily companion + WhatsApp | DailyClaw 🔍 |

### Backup/Restore Workspace

```bash
# Backup (run regularly!)
tar -czvf openclaw-workspace-backup-$(date +%Y%m%d).tar.gz \
  ~/.openclaw/workspace/ \
  ~/openclaw-dev/

# Restore from backup
tar -xzvf openclaw-workspace-backup-20260312.tar.gz
```

### Memory Files Location

```
~/.openclaw/workspace/
├── MEMORY.md                    # Long-term curated memory
├── memory/
│   ├── daily/                   # Short-term (session logs)
│   │   └── YYYY-MM-DD.md
│   ├── mid/                     # Mid-term (monthly summaries)
│   │   └── YYYY-MM.md
│   └── named/                   # Named entity memories
│       └── *.md

~/openclaw-dev/
├── MEMORY.md
└── memory/
    └── 2026-03-12.md
```

### Rebuild Memory Index

If you've lost the embeddings index:

```bash
# From dev workspace, rebuild the index
cd ~/openclaw-dev
python3 scripts/memory_index.py add "Your seed memory text"
```

### Rebuild RAG Index

```bash
# Rebuild project index
cd ~/openclaw-dev
python3 scripts/rag.py index ./projects
```

---

## 6. Extensions & Plugins Recovery

Extensions add capabilities like web search.

### List Installed Extensions

```bash
ls -la ~/.openclaw/extensions/
```

### Reinstall Extensions

```bash
# Check config for extensions to install
grep -A5 "plugins" ~/.openclaw/openclaw.json

# Manually reinstall an extension
cd ~/.openclaw/extensions
npm install @ollama/openclaw-web-search@0.1.7

# Or reinstall all from config
openclaw plugins install
```

### Known Extensions

| Extension | Package | Purpose |
|-----------|---------|---------|
| openclaw-web-search | @ollama/openclaw-web-search | Web search capability |

### Extension Logs

```bash
# Check extension-specific logs
ls -la ~/.openclaw/logs/
tail -50 ~/.openclaw/logs/extensions.log
```

---

## 7. Skills Recovery

Skills provide specialized tools for the agent.

### List Installed Skills

```bash
# In main workspace
ls -la ~/.openclaw/workspace/skills/

# In dev workspace  
ls -la ~/openclaw-dev/skills/
```

### Reinstall Skills

```bash
# Using clawdhub
clawdhub install project-management-2 --dir ~/.openclaw/workspace/skills/
clawdhub install project-management-2 --dir ~/openclaw-dev/skills/

# Or manually copy skill directories
cp -r /path/to/skill ~/.openclaw/workspace/skills/
```

### Known Skills

| Skill | Source | Purpose |
|-------|--------|---------|
| project-management-2 | clawdhub | Task management, planning |

---

## 8. Custom Scripts Recovery

Your custom Python scripts for RAG, Memory, and Internet.

### Script Locations

```
~/openclaw-dev/scripts/
├── memory_index.py       # Vector memory search
├── rag.py                # RAG indexing & query
├── internet.py           # Web search & research loop
└── openclaw-recover.sh   # Recovery script (Bash)
```

### Recovery Script (openclaw-recover.sh)

Located at: `~/openclaw-dev/scripts/openclaw-recover.sh`

**Usage:**
```bash
# Diagnostic (health check)
~/openclaw-dev/scripts/openclaw-recover.sh -d

# Fix gateway
~/openclaw-dev/scripts/openclaw-recover.sh -g

# Fix config (restore from backup)
~/openclaw-dev/scripts/openclaw-recover.sh -c

# Fix broken openclaw command
~/openclaw-dev/scripts/openclaw-recover.sh -o

# Fix all
~/openclaw-dev/scripts/openclaw-recover.sh -a

# Create backup
~/openclaw-dev/scripts/openclaw-recover.sh -b
```

### DailyClaw Workspace (NEW)

| Property | Value |
|----------|-------|
| Location | `~/dailyclaw/` |
| Agent | DailyClaw 🔍 |
| Special | Read-only outside workspace, long memory, WhatsApp routing |

**Files:**
```
~/dailyclaw/
├── IDENTITY.md       # Name: DailyClaw, Emoji: 🔍
├── SOUL.md           # Personality & rules
├── USER.md           # About John
├── AGENTS.md         # Workspace rules
├── MEMORY.md         # Long-term memory
├── TOOLS.md          # Tool notes
├── boot.md           # Session initialization
└── memory/           # Daily conversation logs
```

### Backup/Restore Scripts

```bash
# Backup
tar -czvf openclaw-scripts-backup.tar.gz ~/openclaw-dev/scripts/

# Restore
tar -xzvf openclaw-scripts-backup.tar.gz
```

### Test Scripts

```bash
# Test memory index
cd ~/openclaw-dev
python3 scripts/memory_index.py add "test memory"
python3 scripts/memory_index.py search "test"

# Test RAG
python3 scripts/rag.py index ./projects
python3 scripts/rag.py query "memory architecture"

# Test Internet
python3 scripts/internet.py search "OpenClaw"
python3 scripts/internet.py research "AI agents"
```

---

## 9. Complete Reinstall Procedure

If everything is broken and you need a fresh start but keep your data:

### Step 1: Stop Gateway

```bash
openclaw gateway stop
pkill -f openclaw
```

### Step 2: Backup Everything

```bash
# Create disaster recovery backup
mkdir -p ~/openclaw-backup
cp ~/.openclaw/openclaw.json ~/openclaw-backup/
cp -r ~/.openclaw/workspace ~/openclaw-backup/workspace
cp -r ~/openclaw-dev ~/openclaw-backup/dev-workspace
cp -r ~/.openclaw/extensions ~/openclaw-backup/extensions
cp -r ~/.openclaw/logs ~/openclaw-backup/logs
tar -czvf ~/openclaw-backup/configs.tar.gz ~/.openclaw/*.json*
```

### Step 3: Reinstall OpenClaw Module

```bash
# Reinstall OpenClaw
npm install -g openclaw

# Or if that fails, reinstall from GitHub
npm install -g github:joaoprazeres/MItermClaw
```

### Step 4: Restore Configuration

```bash
# Restore config
cp ~/openclaw-backup/openclaw.json ~/.openclaw/openclaw.json

# Validate
python3 -m json.tool ~/.openclaw/openclaw.json > /dev/null
```

### Step 5: Restore Workspace

```bash
# Restore workspace
cp -r ~/openclaw-backup/workspace/* ~/.openclaw/workspace/
cp -r ~/openclaw-backup/dev-workspace/* ~/openclaw-dev/
```

### Step 6: Restore Extensions

```bash
# Restore extensions
cp -r ~/openclaw-backup/extensions ~/.openclaw/
```

### Step 7: Start Gateway

```bash
openclaw gateway start
openclaw gateway status
```

### Step 8: Verify Everything Works

```bash
# Test basic command
openclaw --version

# Test gateway
openclaw gateway status

# Test agent connection
openclaw sessions list
```

---

## 10. Prevention & Monitoring

### Automated Backups (Cron)

Add to your crontab:

```bash
# Edit crontab
crontab -e

# Add daily backups at 3 AM
0 3 * * * tar -czf ~/openclaw-backups/workspace-$(date +\%Y\%m\%d).tar.gz -C ~ .openclaw/workspace
0 3 * * * tar -czf ~/openclaw-backups/dev-$(date +\%Y\%m\%d).tar.gz -C ~ openclaw-dev
0 3 * * * cp ~/.openclaw/openclaw.json ~/openclaw-backups/config-$(date +\%Y\%m\%d).json
```

### Health Check Script

Create `~/openclaw-dev/scripts/health-check.sh`:

```bash
#!/bin/bash
# OpenClaw Health Check

echo "=== OpenClaw Health Check ==="
echo ""

# Check Gateway
echo "Checking Gateway..."
if openclaw gateway status 2>/dev/null | grep -q "running"; then
    echo "✓ Gateway: RUNNING"
else
    echo "✗ Gateway: NOT RUNNING"
fi

# Check Config
echo "Checking Config..."
if python3 -m json.tool ~/.openclaw/openclaw.json >/dev/null 2>&1; then
    echo "✓ Config: VALID"
else
    echo "✗ Config: INVALID"
fi

# Check Disk Space
echo "Checking Disk..."
df -h ~ | tail -1 | awk '{print "Disk: " $5 " used"}'

# Check Workspaces
echo "Checking Workspaces..."
[ -d ~/.openclaw/workspace ] && echo "✓ Main workspace exists" || echo "✗ Main workspace MISSING"
[ -d ~/openclaw-dev ] && echo "✓ Dev workspace exists" || echo "✗ Dev workspace MISSING"

echo ""
echo "=== Done ==="
```

Make it executable: `chmod +x ~/openclaw-dev/scripts/health-check.sh`

### Log Rotation

Ensure logs don't fill up disk:

```bash
# Check log sizes
ls -lh ~/.openclaw/logs/
```

---

## 11. Context Optimization (NEW)

**Task:** Address "prompt too long; exceeded max context length" errors

**File:** `~/openclaw-dev/projects/TODO-context-optimization.md`

### Problem
Ollama API error 400: prompt too long, exceeded max context length

### Proposed Solution: Smart Topic-Based Compaction

- Detect topic shifts (semantic similarity drop)
- Trigger aggressive compaction or complete purge from context
- Apply to MItermClaw and DailyClaw (not DevClaw)

**Levels:**
1. Standard summarization
2. Aggressive compaction (keep recent, summarize rest)
3. Complete purge from context (keep in memory file only)

---

## 12. WhatsApp Channel Setup (NEW)

**Status:** Configured and paired

**Routing:** All WhatsApp messages → DailyClaw agent

**Config in openclaw.json:**
```json
{
  "bindings": [
    { "match": { "channel": "whatsapp" }, "agentId": "daily" }
  ],
  "channels": {
    "whatsapp": { "enabled": true }
  }
}
```

**Re-pair if needed:**
```bash
openclaw channels login --channel whatsapp
```

---

## Quick Reference: Recovery Commands

```bash
# === EMERGENCY RECOVERY ===

# 1. Restart Gateway
openclaw gateway restart

# 2. Kill stuck processes
pkill -f openclaw && openclaw gateway start

# 3. Restore config from backup
cp ~/.openclaw/openclaw.json.bak.1 ~/.openclaw/openclaw.json

# 4. Clear locks and restart
rm -f ~/.openclaw/*.lock && openclaw gateway restart

# 5. View what's broken
openclaw doctor

# 6. Full reinstall (keeps workspace)
npm install -g openclaw && openclaw gateway restart
```

---

## File Locations Reference

| Component | Path |
|-----------|------|
| OpenClaw module | `/data/data/com.termux/files/usr/lib/node_modules/openclaw/` |
| Main config | `~/.openclaw/openclaw.json` |
| Main workspace | `~/.openclaw/workspace/` |
| Dev workspace | `~/openclaw-dev/` |
| Daily workspace | `~/dailyclaw/` |
| Extensions | `~/.openclaw/extensions/` |
| Skills | `~/.openclaw/workspace/skills/` |
| Logs | `~/.openclaw/logs/` |
| Agents | `~/.openclaw/agents/` |
| Cron jobs | `~/.openclaw/cron/` |
| Gateway socket | `~/.openclaw/gateway.sock` |
| Credentials | `~/.openclaw/credentials/` |

## Project Documentation

| Document | Path |
|----------|------|
| Main README | `~/openclaw-dev/projects/OPENCLAW-README.md` |
| TODO - Context Optimization | `~/openclaw-dev/projects/TODO-context-optimization.md` |
| Memory Architecture | `~/openclaw-dev/projects/memory-architecture.md` |
| Internet Access | `~/openclaw-dev/projects/internet-access-architecture.md` |
| RAG Architecture | `~/openclaw-dev/projects/rag-architecture.md` |

---

*Last updated: 2026-03-13*
*For OpenClaw v0.0-v1.0*