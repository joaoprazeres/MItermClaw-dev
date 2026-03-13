#!/usr/bin/env python3
"""
Context Optimizer - Topic-based compaction for OpenClaw

Detects topic shifts and triggers compaction to free up context.
"""

import json
import sys
import os
import subprocess
from typing import Optional

# Config
CONTEXT_THRESHOLD = 80  # % of context to trigger check
TOPIC_SHIFT_THRESHOLD = 0.35  # similarity below = topic shift
MAX_CONTEXT_TOKENS = 128000

def get_sessions_json() -> dict:
    """Get session info from openclaw."""
    result = subprocess.run(
        ["openclaw", "sessions", "--all-agents", "--json"],
        capture_output=True, text=True
    )
    return json.loads(result.stdout)

def get_current_session_tokens(agent_id: str = "main") -> tuple[int, int]:
    """Get (input_tokens, context_limit) for current session."""
    data = get_sessions_json()
    for session in data.get("sessions", []):
        if session.get("agentId") == agent_id:
            # Find current session (most recently updated)
            if session.get("key", "").endswith(":main"):
                return session.get("inputTokens", 0), session.get("contextTokens", MAX_CONTEXT_TOKENS)
    return 0, MAX_CONTEXT_TOKENS

def calculate_usage_pct(input_tokens: int, context_tokens: int) -> float:
    """Calculate context usage percentage."""
    if context_tokens == 0:
        return 0
    return (input_tokens / context_tokens) * 100

def check_context_status() -> dict:
    """Check context status for all agents."""
    data = get_sessions_json()
    status = {"agents": [], "total_sessions": 0}
    
    sessions = data.get("sessions", [])
    status["total_sessions"] = len(sessions)
    
    agent_contexts = {}
    for session in sessions:
        agent_id = session.get("agentId", "unknown")
        input_tok = session.get("inputTokens", 0)
        context_tok = session.get("contextTokens", MAX_CONTEXT_TOKENS)
        usage = calculate_usage_pct(input_tok, context_tok)
        
        if agent_id not in agent_contexts:
            agent_contexts[agent_id] = {
                "current_usage": 0,
                "context_limit": context_tok,
                "session_key": session.get("key", "")
            }
        
        # Update if this is the current session
        if ":main" in session.get("key", "") or ":daily" in session.get("key", ""):
            agent_contexts[agent_id]["current_usage"] = max(
                agent_contexts[agent_id]["current_usage"],
                usage
            )
    
    for agent_id, info in agent_contexts.items():
        status["agents"].append({
            "agent": agent_id,
            "usage_pct": info["current_usage"],
            "input_tokens": int(info["current_usage"] * info["context_limit"] / 100),
            "context_limit": info["context_limit"],
            "needs_compaction": info["current_usage"] > CONTEXT_THRESHOLD
        })
    
    return status

def detect_topic_shift_llm() -> dict:
    """
    Use LLM to detect topic shift in conversation.
    Returns: {"shift": bool, "summary": str, "reason": str}
    """
    # This would integrate with the session transcript
    # For now, return a placeholder - needs transcript access
    return {
        "shift": False,
        "summary": "",
        "reason": "LLM-based detection not yet implemented - needs transcript access"
    }

def summarize_old_context() -> str:
    """
    Summarize old context to free up tokens.
    This would call LLM to summarize older messages.
    """
    return "Summarization not yet implemented"

def run_compaction(agent_id: str = "main", level: int = 1) -> dict:
    """
    Run compaction at specified level.
    
    Level 1: Summarize last N messages
    Level 2: Keep only last M messages, summarize rest  
    Level 3: Complete purge of old topic (keep in memory file only)
    """
    result = {
        "agent": agent_id,
        "level": level,
        "success": False,
        "tokens_freed": 0,
        "message": ""
    }
    
    if level == 1:
        # Standard compaction via openclaw
        proc = subprocess.run(
            ["openclaw", "sessions", "cleanup", "--agent", agent_id, "--enforce", "--json"],
            capture_output=True, text=True
        )
        result["success"] = proc.returncode == 0
        result["message"] = "Ran session cleanup"
        
    elif level == 2:
        # Summarize + keep recent
        summary = summarize_old_context()
        result["message"] = f"Summarization: {summary}"
        result["success"] = True
        
    elif level == 3:
        # Full purge - requires transcript modification
        result["message"] = "Full purge not yet implemented"
        
    return result

def main():
    if len(sys.argv) < 2:
        print("Usage: context_optimizer.py <command>")
        print("Commands:")
        print("  status              - Check context usage")
        print("  check               - Check and auto-compact if needed")
        print("  detect-topic        - Detect topic shift")
        print("  compact <level>    - Run compaction (1-3)")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "status":
        status = check_context_status()
        print(json.dumps(status, indent=2))
        
    elif cmd == "check":
        status = check_context_status()
        for agent in status["agents"]:
            if agent["needs_compaction"]:
                print(f"⚠️ {agent['agent']}: {agent['usage_pct']:.1f}% - triggering compaction")
                result = run_compaction(agent["agent"])
                print(json.dumps(result, indent=2))
            else:
                print(f"✅ {agent['agent']}: {agent['usage_pct']:.1f}% - OK")
                
    elif cmd == "detect-topic":
        result = detect_topic_shift_llm()
        print(json.dumps(result, indent=2))
        
    elif cmd == "compact":
        level = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        result = run_compaction(level=level)
        print(json.dumps(result, indent=2))
        
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)

if __name__ == "__main__":
    main()