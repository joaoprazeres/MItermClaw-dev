# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your dev setup.

## What Goes Here

Things like:
- Camera names and locations
- SSH hosts and aliases
- Device nicknames
- OpenClaw-specific config paths
- Model endpoints
- Anything environment-specific

## God Layer (Model Providers)

| Priority | Name | Endpoint | Model | Status |
|----------|------|----------|-------|--------|
| 1 (default) | local-ollama | http://127.0.0.1:11434 | minimax-m2.5:cloud | ✅ Tested |
| 2 (fallback) | remote-ollama | https://llama.alienubserv.joaoprazeres.pt | phi4-mini:3.8b | ✅ Tested |

**Tested 2026-03-12:** Both providers responding. Local has 5 models, Remote has 28 models.

## Examples

```markdown
### OpenClaw Paths

- Config: ~/.config/openclaw/
- Gateway: /data/data/com.termux/files/usr/lib/node_modules/openclaw/

### SSH

- home-server → 192.168.1.100, user: admin
```

---

Add whatever helps you do your job.