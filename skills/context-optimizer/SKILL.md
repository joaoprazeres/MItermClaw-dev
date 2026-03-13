---
name: context-optimizer
description: 'Optimize session context to prevent "prompt too long" errors. Use when: (1) session context is growing large, (2) you notice repeated context errors, (3) long conversations. NOT for: short conversations under 50 messages, DevClaw sessions, or when you want to keep full history.'
metadata:
  {
    "openclaw": { "emoji": "📦", "requires": { "anyBins": ["python3"] } },
  }
---

# Context Optimizer

Use the **context_optimizer.py** script to analyze and compact session context.

## Quick Usage

```bash
# Check current session context size
~/openclaw-dev/scripts/context_optimizer.py --session <session-id> --check

# Check main agent (MItermClaw)
~/openclaw-dev/scripts/context_optimizer.py --session main --check

# Check DailyClaw
~/openclaw-dev/scripts/context_optimizer.py --session daily --check

# Compact session (3 levels available)
~/openclaw-dev/scripts/context_optimizer.py --session <session-id> --compact --level 1
```

## Compaction Levels

| Level | Name | When to Use |
|-------|------|-------------|
| 1 | Summarize | Context at 60-70% - summarize older messages |
| 2 | Aggressive | Context at 80-90% - keep fewer messages, summarize more |
| 3 | Purge | Context near limit - keep only recent, discard rest |

## Finding Your Session ID

```bash
# List active sessions
ls ~/.openclaw/agents/main/sessions/*.jsonl | tail -5
ls ~/.openclaw/agents/daily/sessions/*.jsonl | tail -5
```

## Integration

This skill works alongside OpenClaw's built-in context-window-guard which warns at 32K tokens and blocks at 16K tokens.

For automatic optimization, set up a cron job:
```bash
# Check every 30 minutes (adds to cron)
openclaw cron add --name "context-check" --schedule "*/30 * * * *" --agentTurn --message "Check session context sizes and compact if needed"
```