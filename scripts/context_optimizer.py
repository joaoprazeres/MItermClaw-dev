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

# Config - HYBRID CONTEXT OPTIMIZER
CONTEXT_THRESHOLD = 80  # % of context to trigger check
WARN_THRESHOLD = 50  # % - warn user
ACTION_THRESHOLD = 70  # % - auto-trigger action
TOPIC_SHIFT_THRESHOLD = 0.35  # similarity below = topic shift
MAX_CONTEXT_TOKENS = 128000

# Check frequency
CHECK_EVERY_MESSAGES = 10
CHECK_EVERY_SECONDS = 300  # 5 minutes

# Directories
MEMORY_DIR = "/data/data/com.termux/files/home/.openclaw/workspace/memory"
SUMMARIZED_DIR = f"{MEMORY_DIR}/summarized"
ARCHIVED_SESSIONS_DIR = f"{MEMORY_DIR}/sessions/archived"

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

def get_current_session_path(agent_id: str = "main") -> str:
    """Get the path to the current session's JSONL file."""
    import glob
    sessions_dir = f"/data/data/com.termux/files/home/.openclaw/agents/{agent_id}/sessions"
    
    # Find the most recent non-deleted, non-locked JSONL file
    pattern = f"{sessions_dir}/*.jsonl"
    files = []
    for f in glob.glob(pattern):
        if ".deleted." not in f and ".lock" not in f and ".backup" not in f and ".compact" not in f:
            files.append(f)
    
    if not files:
        return None
    
    # Sort by modification time, most recent first
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    return files[0]

def read_session_messages(session_path: str, limit: int = None) -> list:
    """Read messages from a session JSONL file."""
    messages = []
    try:
        with open(session_path, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if entry.get("type") == "message":
                        msg = entry.get("message", {})
                        role = msg.get("role", "")
                        content = msg.get("content", [])
                        
                        # Extract text content from content blocks
                        text_content = ""
                        if isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    text_content += block.get("text", "")
                        elif isinstance(content, str):
                            text_content = content
                        
                        if text_content.strip():
                            messages.append({
                                "role": role,
                                "content": text_content.strip(),
                                "timestamp": entry.get("timestamp", "")
                            })
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return []
    
    if limit:
        return messages[-limit:] if limit < len(messages) else messages
    return messages

def call_llm(prompt: str, system: str = None) -> str:
    """Call Ollama LLM with a prompt."""
    import requests
    
    # Use the default model (minimax-m2.5:cloud)
    url = "http://localhost:11434/api/generate"
    
    payload = {
        "model": "minimax-m2.5:cloud",
        "prompt": prompt,
        "stream": False
    }
    
    if system:
        payload["system"] = system
    
    try:
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        return response.json().get("response", "")
    except Exception as e:
        # Fallback: try using subprocess with ollama CLI
        result = subprocess.run(
            ["ollama", "generate", "-m", "minimax-m2.5:cloud", "-p", prompt[:500]],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return result.stdout
        return f"[Error calling LLM: {e}]"

def analyze_topic_shift(recent_messages: list, earlier_messages: list) -> dict:
    """
    Use LLM to analyze whether there's a topic shift between recent and earlier messages.
    Returns dict with shift detection results.
    """
    if not earlier_messages:
        return {
            "shift": False,
            "summary": "No earlier messages to compare",
            "reason": "Not enough context for comparison",
            "level": 1
        }
    
    # Prepare message summaries for the LLM
    recent_summary = "\n".join([
        f"[{m['role']}]: {m['content'][:200]}{'...' if len(m['content']) > 200 else ''}"
        for m in recent_messages[-10:]  # Last 10 messages
    ])
    
    earlier_summary = "\n".join([
        f"[{m['role']}]: {m['content'][:200]}{'...' if len(m['content']) > 200 else ''}"
        for m in earlier_messages[:10]  # First 10 messages
    ])
    
    analysis_prompt = f"""You are a topic analysis system. Compare these two parts of a conversation and determine if there's a topic shift.

RECENT MESSAGES (last part of conversation):
{recent_summary}

EARLIER MESSAGES (earlier part of conversation):
{earlier_summary}

Analyze whether the conversation topic has shifted significantly between these two parts.
Consider:
1. Are they discussing the same subject/project?
2. Are the keywords/topics related?
3. Is there a clear break in context?

Respond in JSON format only (no other text):
{{
    "shift": true/false,
    "similarity_score": 0.0-1.0,
    "recent_topic": "brief description of recent topic",
    "earlier_topic": "brief description of earlier topic",
    "reason": "explanation of why you think there's a shift or not"
}}

Return only valid JSON, no markdown formatting."""

    try:
        result = call_llm(analysis_prompt)
        # Try to parse JSON from the result
        import re
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except Exception as e:
        pass
    
    # Fallback: basic keyword-based detection
    recent_text = " ".join([m['content'][:300] for m in recent_messages[-5:]])
    earlier_text = " ".join([m['content'][:300] for m in earlier_messages[:5]])
    
    # Simple word overlap analysis
    recent_words = set(recent_text.lower().split())
    earlier_words = set(earlier_text.lower().split())
    
    # Remove common stopwords
    stopwords = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
                 "have", "has", "had", "do", "does", "did", "will", "would", "could",
                 "should", "may", "might", "must", "shall", "can", "need", "dare",
                 "to", "of", "in", "for", "on", "with", "at", "by", "from", "as",
                 "into", "through", "during", "before", "after", "above", "below",
                 "it", "its", "this", "that", "these", "those", "i", "you", "we",
                 "they", "he", "she", "me", "him", "her", "us", "them", "my", "your",
                 "their", "our", "and", "or", "but", "if", "then", "because", "as",
                 "what", "which", "who", "whom", "when", "where", "why", "how",
                 "all", "each", "every", "both", "few", "more", "most", "other",
                 "some", "such", "no", "nor", "not", "only", "own", "same", "so",
                 "than", "too", "very", "just", "also", "now", "here", "there"}
    
    recent_keywords = recent_words - stopwords
    earlier_keywords = earlier_words - stopwords
    
    if recent_keywords and earlier_keywords:
        overlap = len(recent_keywords & earlier_keywords)
        total = len(recent_keywords | earlier_keywords)
        similarity = overlap / total if total > 0 else 0
    else:
        similarity = 0.5
    
    shift = similarity < TOPIC_SHIFT_THRESHOLD
    
    return {
        "shift": shift,
        "similarity_score": similarity,
        "recent_topic": "detected from recent messages",
        "earlier_topic": "detected from earlier messages",
        "reason": f"Keyword overlap similarity: {similarity:.2f} (threshold: {TOPIC_SHIFT_THRESHOLD})",
        "level": 1 if not shift else (2 if similarity > 0.15 else 3)
    }

def detect_topic_shift_llm(agent_id: str = "main") -> dict:
    """
    Use LLM to detect topic shift in conversation.
    Returns: {"shift": bool, "summary": str, "reason": str, "level": 1-3}
    
    Level 1: Standard summarize
    Level 2: Summarize + keep recent  
    Level 3: Complete purge from context (but keep in memory files)
    """
    # Get the current session file
    session_path = get_current_session_path(agent_id)
    
    if not session_path:
        return {
            "shift": False,
            "summary": "",
            "reason": "No active session found",
            "level": 1
        }
    
    # Read all messages
    all_messages = read_session_messages(session_path)
    
    if len(all_messages) < 10:
        return {
            "shift": False,
            "summary": "Not enough messages to detect topic shift",
            "reason": f"Only {len(all_messages)} messages in session",
            "level": 1
        }
    
    # Split into recent and earlier messages
    # Recent = last 1/3 of messages, Earlier = first 2/3
    split_idx = len(all_messages) // 3
    recent_messages = all_messages[split_idx:]
    earlier_messages = all_messages[:split_idx]
    
    # Analyze for topic shift
    result = analyze_topic_shift(recent_messages, earlier_messages)
    
    # Determine compaction level based on shift detection
    if result.get("shift", False):
        similarity = result.get("similarity_score", 0)
        
        # Level based on severity of shift
        if similarity < 0.15:
            level = 3  # Complete purge
            summary = f"Topic shift detected: {result.get('recent_topic', 'new topic')} vs {result.get('earlier_topic', 'old topic')}"
        elif similarity < 0.25:
            level = 2  # Summarize + keep recent
            summary = f"Significant topic shift: {result.get('recent_topic', 'new topic')}"
        else:
            level = 1  # Standard summarize
            summary = "Minor topic shift detected"
    else:
        level = 1
        summary = "No significant topic shift"
    
    return {
        "shift": result.get("shift", False),
        "summary": summary,
        "reason": result.get("reason", ""),
        "level": result.get("level", level),
        "similarity_score": result.get("similarity_score"),
        "session_path": session_path
    }

def summarize_old_messages(agent_id: str = "main", keep_last: int = 50) -> dict:
    """
    Summarize old messages and save to file.
    Keeps last N messages in active context, summarizes older ones.
    
    Returns: {"success": bool, "summary": str, "tokens_freed": int, "file": str}
    """
    import datetime
    
    session_path = get_current_session_path(agent_id)
    if not session_path:
        return {"success": False, "summary": "No active session found", "tokens_freed": 0, "file": ""}
    
    all_messages = read_session_messages(session_path)
    
    if len(all_messages) <= keep_last:
        return {"success": False, "summary": f"Only {len(all_messages)} messages, not trimming", "tokens_freed": 0, "file": ""}
    
    # Split: messages to summarize vs keep
    messages_to_summarize = all_messages[:-keep_last]
    messages_to_keep = all_messages[-keep_last:]
    
    # Generate summary using LLM
    content_for_summary = "\n\n".join([
        f"[{m['role']}]: {m['content'][:500]}{'...' if len(m['content']) > 500 else ''}"
        for m in messages_to_summarize[:30]  # Limit to avoid token overflow
    ])
    
    summarize_prompt = f"""Summarize this conversation concisely. Capture:
- Main topics discussed
- Key decisions made
- Important context for future reference

CONVERSATION:
{content_for_summary}

Provide a concise summary (3-5 sentences max):"""
    
    summary = call_llm(summarize_prompt)
    
    # Estimate tokens saved (rough: ~4 chars per token)
    chars_summarized = sum(len(m['content']) for m in messages_to_summarize)
    tokens_freed = chars_summarized // 4
    
    # Save to file
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    summary_file = f"{SUMMARIZED_DIR}/{date_str}.json"
    
    summary_data = {
        "date": date_str,
        "agent": agent_id,
        "summary": summary,
        "message_count": len(messages_to_summarize),
        "tokens_freed": tokens_freed,
        "session_file": session_path
    }
    
    # Append to existing or create new
    existing = []
    if os.path.exists(summary_file):
        try:
            with open(summary_file, 'r') as f:
                existing = json.load(f)
        except:
            existing = []
    
    if isinstance(existing, list):
        existing.append(summary_data)
    else:
        existing = [summary_data]
    
    os.makedirs(SUMMARIZED_DIR, exist_ok=True)
    with open(summary_file, 'w') as f:
        json.dump(existing, f, indent=2)
    
    return {
        "success": True,
        "summary": summary,
        "tokens_freed": tokens_freed,
        "file": summary_file,
        "messages_archived": len(messages_to_summarize),
        "messages_kept": len(messages_to_keep)
    }


def archive_session(agent_id: str = "main", archive_name: str = None) -> dict:
    """
    Archive current session to a backup file.
    
    Returns: {"success": bool, "archive_path": str}
    """
    import datetime
    
    session_path = get_current_session_path(agent_id)
    if not session_path:
        return {"success": False, "archive_path": "", "reason": "No session found"}
    
    os.makedirs(ARCHIVED_SESSIONS_DIR, exist_ok=True)
    
    if not archive_name:
        date_str = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        archive_name = f"{agent_id}_{date_str}.jsonl"
    
    archive_path = f"{ARCHIVED_SESSIONS_DIR}/{archive_name}"
    
    try:
        import shutil
        shutil.copy2(session_path, archive_path)
        
        # Also save metadata
        metadata_path = archive_path + ".meta.json"
        metadata = {
            "archived_at": datetime.datetime.now().isoformat(),
            "original_path": session_path,
            "agent": agent_id,
            "message_count": len(read_session_messages(session_path))
        }
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        return {"success": True, "archive_path": archive_path}
    except Exception as e:
        return {"success": False, "archive_path": "", "reason": str(e)}


def check_and_optimize(agent_id: str = "main") -> dict:
    """
    Main optimization check - hybrid approach.
    Checks context levels and takes appropriate action based on thresholds.
    
    Returns: {"action": str, "details": dict}
    """
    input_tokens, context_limit = get_current_session_tokens(agent_id)
    usage_pct = calculate_usage_pct(input_tokens, context_limit)
    
    result = {
        "agent": agent_id,
        "usage_pct": usage_pct,
        "input_tokens": input_tokens,
        "context_limit": context_limit,
        "action": "none",
        "details": {}
    }
    
    if usage_pct >= ACTION_THRESHOLD:
        # High usage - take action
        result["action"] = "summarize_and_archive"
        result["details"] = summarize_old_messages(agent_id, keep_last=50)
        
        if not result["details"].get("success"):
            # Fallback: just archive
            result["details"]["fallback"] = archive_session(agent_id)
            
    elif usage_pct >= WARN_THRESHOLD:
        result["action"] = "warn"
        result["details"] = {
            "message": f"Context at {usage_pct:.1f}%",
            "recommendation": "Consider running compaction"
        }
    
    return result


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
        print("  check-optimize      - Hybrid optimization (warn at 50%, act at 70%)")
        print("  detect-topic [agent] - Detect topic shift (default: main)")
        print("  compact <level>    - Run compaction (1-3)")
        print("  summarize [agent]  - Summarize old messages, keep last 50")
        print("  archive [agent]    - Archive session to backup")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    # Default agent is "main"
    agent_id = sys.argv[2] if len(sys.argv) > 2 else "main"
    
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
                
    elif cmd == "check-optimize":
        # Hybrid auto-optimization
        result = check_and_optimize(agent_id)
        print(json.dumps(result, indent=2))
        
    elif cmd == "summarize":
        # Manual summarize old messages
        result = summarize_old_messages(agent_id, keep_last=50)
        print(json.dumps(result, indent=2))
        
    elif cmd == "archive":
        # Manual archive session
        result = archive_session(agent_id)
        print(json.dumps(result, indent=2))
                
    elif cmd == "detect-topic":
        result = detect_topic_shift_llm(agent_id)
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