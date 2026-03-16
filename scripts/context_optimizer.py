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
CONTEXT_THRESHOLD = 60  # % of context to trigger check (lowered from 80)
WARN_THRESHOLD = 40  # % - warn user (lowered from 50)
ACTION_THRESHOLD = 50  # % - auto-trigger action (lowered from 60)
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
                ["openclaw-wrapper", "sessions", "--all-agents", "--json"],
        capture_output=True, text=True
    )
    return json.loads(result.stdout)

def get_current_session_tokens(agent_id: str = "main") -> tuple[int, int]:
    """Get (input_tokens, context_limit) for current session."""
    data = get_sessions_json()
    for session in data.get("sessions", []):
        if session.get("agentId") == agent_id:
            # Find current session (most recently updated by timestamp)
            # Key format: agent:main:tui-uuid or agent:daily:whatsapp:direct:+number
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
    date_str = datetime.datetime.now().strftime("%d-%m-%Y")
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
        date_str = datetime.datetime.now().strftime("%d-%m-%Y_%H:%M:%S")
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
    
    Priority: Prune → Summarize → Truncate
    
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
        # High usage - try pruning first (lightweight)
        prune_result = prune_low_value_messages(agent_id, min_value=0.3, max_prune_ratio=0.2)
        
        if prune_result.get("success") and prune_result.get("pruned_count", 0) > 0:
            result["action"] = "prune"
            result["details"] = prune_result
            
            # Re-check after pruning
            input_tokens_after, _ = get_current_session_tokens(agent_id)
            usage_pct_after = calculate_usage_pct(input_tokens_after, context_limit)
            
            # If still high, do full summarization
            if usage_pct_after >= ACTION_THRESHOLD:
                result["action"] = "prune_then_summarize"
                result["details"]["summarize"] = summarize_and_truncate(agent_id, target_tokens=30000, force=True)
        else:
            # Pruning didn't help enough, go straight to truncate
            result["action"] = "summarize_and_truncate"
            result["details"] = summarize_and_truncate(agent_id, target_tokens=30000, force=True)
        
        # If still failing (runtime context bloat), force archive and start fresh
        if not result["details"].get("success"):
            # This happens when runtime context (system prompts, tools) is bloated
            # Solution: archive current session, start fresh
            print("⚠️ Runtime context bloated, forcing session archive...")
            archive_result = archive_session(agent_id)
            result["action"] = "force_archive_due_to_runtime_bloat"
            result["details"]["fallback"] = archive_result
            result["details"]["reason"] = "Session file is small but runtime context exceeds limit (system prompts, tools)"
            
    elif usage_pct >= WARN_THRESHOLD:
        # Warning zone - light prune only
        prune_result = prune_low_value_messages(agent_id, min_value=0.25, max_prune_ratio=0.15)
        
        if prune_result.get("pruned_count", 0) > 0:
            result["action"] = "prune_only"
            result["details"] = prune_result
        else:
            result["action"] = "warn"
            result["details"] = {
                "message": f"Context at {usage_pct:.1f}%",
                "recommendation": "Consider running compaction"
            }
    
    return result



# ============================================================
# NEW FUNCTIONS - Session truncation for actual context reduction
# ============================================================
def truncate_session_file(session_path: str, keep_messages: list) -> dict:
    """
    Actually truncate the session JSONL file to keep only specified messages.
    """
    import datetime
    
    try:
        # Read the full JSONL and filter to only keep_messages
        kept_contents = []
        with open(session_path, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if entry.get("type") == "message":
                        msg = entry.get("message", {})
                        role = msg.get("role", "")
                        content = msg.get("content", [])
                        
                        # Extract text to match against kept messages
                        text_content = ""
                        if isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    text_content += block.get("text", "")
                        elif isinstance(content, str):
                            text_content = content
                        
                        text_content = text_content.strip()
                        
                        # Check if this message is in our keep list
                        for km in keep_messages:
                            if km.get("role") == role and km.get("content", "").startswith(text_content[:100]):
                                kept_contents.append(line.strip())
                                break
                except json.JSONDecodeError:
                    continue
        
        # Backup original
        backup_path = session_path + f".backup.{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Write truncated version
        with open(session_path, 'w') as f:
            for line in kept_contents:
                f.write(line + '\n')
        
        return {
            "success": True,
            "backup_path": backup_path,
            "messages_kept": len(kept_contents),
            "original_size": "N/A"  # Skip backup size calculation for speed
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def estimate_message_tokens(message: dict) -> int:
    """Rough estimate of tokens in a message."""
    content = message.get("content", "")
    if isinstance(content, list):
        text = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    else:
        text = content
    # Rough: ~4 chars per token
    return len(text) // 4


def summarize_and_truncate(agent_id: str = "main", target_tokens: int = 30000, force: bool = False) -> dict:
    """
    Summarize old messages and ACTUALLY truncate the session file.
    
    Keeps last N messages that sum to approximately target_tokens.
    Everything older gets summarized and removed from session.
    
    Args:
        agent_id: Target agent
        target_tokens: Target token count to keep
        force: Force truncation even if under target (to free runtime context)
    """
    import datetime
    
    session_path = get_current_session_path(agent_id)
    if not session_path:
        return {"success": False, "error": "No active session found"}
    
    all_messages = read_session_messages(session_path)
    
    if not all_messages:
        return {"success": False, "error": "No messages in session"}
    
    # Calculate token counts for each message
    message_tokens = []
    for i, msg in enumerate(all_messages):
        tok = estimate_message_tokens(msg)
        message_tokens.append((i, msg, tok))
    
    # Find how many messages from the end to keep
    # (we want to keep the most recent ones)
    kept_messages = []
    total_tokens = 0
    
    # Go backwards from the end
    for i, msg, tok in reversed(message_tokens):
        if total_tokens + tok > target_tokens and kept_messages:
            break
        kept_messages.insert(0, msg)  # Insert at front to maintain order
        total_tokens += tok
    
    messages_to_summarize = all_messages[:len(all_messages) - len(kept_messages)]
    
    if not messages_to_summarize and not force:
        return {"success": False, "error": "No messages to summarize (already within target)"}
    
    if not messages_to_summarize and force:
        # Force mode: even if nothing to summarize, archive current session and start fresh
        print("Force mode: archiving session and starting fresh")
        archive_result = archive_session(agent_id)
        return {
            "success": True,
            "action": "force_archive",
            "archive": archive_result,
            "tokens_freed": total_tokens,
            "message": "Archived session in force mode"
        }
    
    print(f"Summarizing {len(messages_to_summarize)} messages, keeping {len(kept_messages)} ({total_tokens} tokens)")
    
    # Generate summary
    content_for_summary = "\n\n".join([
        f"[{m['role']}]: {m['content'][:500]}{'...' if len(m['content']) > 500 else ''}"
        for m in messages_to_summarize[:20]
    ])
    
    summarize_prompt = f"""Summarize this conversation concisely. Capture:
- Main topics discussed
- Key decisions made
- Important context for future reference

CONVERSATION:
{content_for_summary}

Provide a concise summary (3-5 sentences max):"""
    
    summary = call_llm(summarize_prompt)
    
    # Save summary to file
    date_str = datetime.datetime.now().strftime("%d-%m-%Y")
    summary_file = f"{SUMMARIZED_DIR}/{date_str}.json"
    
    chars_summarized = sum(len(m['content']) for m in messages_to_summarize)
    tokens_freed = chars_summarized // 4
    
    summary_data = {
        "date": date_str,
        "agent": agent_id,
        "summary": summary,
        "message_count": len(messages_to_summarize),
        "tokens_freed": tokens_freed,
        "session_file": session_path
    }
    
    # Append to existing
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
    
    # ACTUALLY TRUNCATE THE SESSION FILE
    truncate_result = truncate_session_file(session_path, kept_messages)
    
    return {
        "success": True,
        "summary": summary,
        "tokens_freed": tokens_freed,
        "file": summary_file,
        "messages_summarized": len(messages_to_summarize),
        "messages_kept": len(kept_messages),
        "truncated": truncate_result
    }


def cleanup_stale_sessions(agent_id: str = "main", max_age_hours: int = 24) -> dict:
    """
    Delete stale/terminated session files older than max_age_hours.
    """
    import glob
    import time
    
    sessions_dir = f"/data/data/com.termux/files/home/.openclaw/agents/{agent_id}/sessions"
    pattern = f"{sessions_dir}/*.jsonl"
    
    cutoff_time = time.time() - (max_age_hours * 3600)
    
    deleted = []
    errors = []
    
    for filepath in glob.glob(pattern):
        try:
            mtime = os.path.getmtime(filepath)
            if mtime < cutoff_time:
                # Also check if session is terminated (check meta if exists)
                meta_path = filepath + ".meta.json"
                if os.path.exists(meta_path):
                    with open(meta_path, 'r') as f:
                        meta = json.load(f)
                    # Check if it's a terminated session
                    if meta.get("endedAt") or meta.get("terminated"):
                        os.remove(filepath)
                        deleted.append(filepath)
                        # Remove meta too
                        if os.path.exists(meta_path):
                            os.remove(meta_path)
        except Exception as e:
            errors.append(f"{filepath}: {e}")
    
    return {
        "deleted": len(deleted),
        "files": deleted,
        "errors": errors
    }

# ============================================================
# Advanced Features: Pruning, Cost Tracking, Hierarchical Summaries
# ============================================================

# Token price per 1M tokens (approximate, USD)
TOKEN_PRICING = {
    "minimax-m2.5:cloud": {"input": 0.0, "output": 0.0},  # Local/Ollama - no API cost
    "phi4-mini:3.8b": {"input": 0.0, "output": 0.0},       # Local - no API cost
    "phi4": {"input": 0.0, "output": 0.0},                 # Local - no API cost
    "default": {"input": 0.40, "output": 1.20}             # Fallback estimate
}

def get_session_cost(input_tokens: int, output_tokens: int, model: str = "default") -> dict:
    """Calculate estimated cost for a session."""
    pricing = TOKEN_PRICING.get(model, TOKEN_PRICING["default"])
    
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "model": model,
        "input_cost_usd": round(input_cost, 6),
        "output_cost_usd": round(output_cost, 6),
        "total_cost_usd": round(input_cost + output_cost, 6)
    }

def score_message_value(message: dict) -> float:
    """
    Score a message by its information value (0-1).
    Higher scores = more valuable to keep.
    """
    content = message.get("content", "")
    role = message.get("role", "user")
    
    if not content:
        return 0.0
    
    content_lower = content.lower()
    score = 0.5  # Base score
    
    # Boost factors
    if len(content) > 100:
        score += 0.15  # Substantial content
    if len(content) > 500:
        score += 0.1   # Long content (likely important)
    
    # Role-based scoring
    if role == "system":
        score = 0.9  # System prompts are crucial
    elif role == "assistant":
        if any(kw in content_lower for kw in ["let me", "i'll", "i'll check", "analyzing"]):
            score += 0.1  # Action messages are valuable
    
    # Low-value patterns (reduce score)
    low_value_patterns = [
        "ok", "okay", "sure", "yes", "no", "got it", "thanks", "thank you",
        "cool", "nice", "great", "👍", "✅", "sounds good", "perfect",
        "that's all", "nothing else", "that's it", "hi", "hello", "hey"
    ]
    
    if content_lower in low_value_patterns or len(content_lower.strip()) < 5:
        score -= 0.4
    
    # Questions without substantial context
    if content.endswith("?") and len(content) < 50:
        score -= 0.2
    
    return max(0.0, min(1.0, score))

def prune_low_value_messages(agent_id: str = "main", min_value: float = 0.3, max_prune_ratio: float = 0.3) -> dict:
    """
    Remove low-value messages from session.
    
    Args:
        agent_id: Agent to prune
        min_value: Minimum score to keep (0-1)
        max_prune_ratio: Max % of messages to prune (0-1)
    
    Returns: {"success": bool, "pruned_count": int, "tokens_freed": int, "file": str}
    """
    import datetime
    
    session_path = get_current_session_path(agent_id)
    if not session_path:
        return {"success": False, "error": "No active session found"}
    
    all_messages = read_session_messages(session_path)
    
    if len(all_messages) < 10:
        return {"success": False, "error": "Too few messages to prune"}
    
    # Score all messages
    scored = [(i, msg, score_message_value(msg)) for i, msg in enumerate(all_messages)]
    
    # Don't prune the last 5 messages (recent context is important)
    prunable = [(i, msg, s) for i, msg, s in scored[:-5] if s < min_value]
    
    # Limit prune ratio
    max_to_prune = int(len(all_messages) * max_prune_ratio)
    prunable = prunable[:max_to_prune]
    
    if not prunable:
        return {"success": True, "pruned_count": 0, "tokens_freed": 0, "message": "No low-value messages to prune"}
    
    # Get indices to keep
    prune_indices = set(i for i, _, _ in prunable)
    kept_messages = [msg for i, msg in enumerate(all_messages) if i not in prune_indices]
    
    # Calculate tokens freed
    tokens_freed = sum(estimate_message_tokens(msg) for i, msg, _ in prunable)
    
    # Save pruned messages to file before removing
    date_str = datetime.datetime.now().strftime("%d-%m-%Y")
    prune_file = f"{MEMORY_DIR}/pruned/{date_str}_{agent_id}.json"
    os.makedirs(f"{MEMORY_DIR}/pruned", exist_ok=True)
    
    pruned_data = {
        "date": date_str,
        "agent": agent_id,
        "pruned_messages": [{"role": msg["role"], "content": msg["content"][:200], "score": s} for i, msg, s in prunable],
        "tokens_freed": tokens_freed,
        "count": len(prunable)
    }
    
    with open(prune_file, 'w') as f:
        json.dump(pruned_data, f, indent=2)
    
    # Rewrite session file with kept messages
    truncate_session_file(session_path, kept_messages)
    
    return {
        "success": True,
        "pruned_count": len(prunable),
        "tokens_freed": tokens_freed,
        "prune_file": prune_file,
        "kept_count": len(kept_messages)
    }

def hierarchical_summarize(agent_id: str = "main", levels: int = 2) -> dict:
    """
    Multi-level summarization:
    - Level 1: Summarize old messages to conversation summary
    - Level 2: Summarize conversation to topic overview
    
    Returns: {"success": bool, "summaries": list, "tokens_freed": int}
    """
    import datetime
    
    session_path = get_current_session_path(agent_id)
    if not session_path:
        return {"success": False, "error": "No active session found"}
    
    all_messages = read_session_messages(session_path)
    
    if len(all_messages) < 20:
        return {"success": False, "error": "Not enough messages for hierarchical summarization"}
    
    date_str = datetime.datetime.now().strftime("%d-%m-%Y")
    summaries = []
    tokens_freed = 0
    
    # Level 1: Summarize oldest 50% -> single summary
    mid = len(all_messages) // 2
    old_messages = all_messages[:mid]
    recent_messages = all_messages[mid:]
    
    content_old = "\n\n".join([
        f"[{m['role']}]: {m['content'][:300]}{'...' if len(m['content']) > 300 else ''}"
        for m in old_messages[:25]
    ])
    
    prompt_level1 = f"""Summarize this conversation segment concisely (2-3 sentences):
{content_old}

Focus on: topics, decisions, key info."""
    
    summary_l1 = call_llm(prompt_level1)
    tokens_freed += sum(estimate_message_tokens(msg) for msg in old_messages)
    
    summaries.append({
        "level": 1,
        "summary": summary_l1,
        "message_count": len(old_messages)
    })
    
    if levels >= 2 and recent_messages:
        # Level 2: Summarize recent + L1 summary as topic overview
        content_recent = "\n\n".join([
            f"[{m['role']}]: {m['content'][:300]}{'...' if len(m['content']) > 300 else ''}"
            for m in recent_messages[-20:]
        ])
        
        prompt_level2 = f"""Create a topic overview combining this recent conversation and earlier summary:

EARLIER SUMMARY:
{summary_l1}

RECENT CONVERSATION:
{content_recent}

Provide a high-level topic summary (1-2 sentences):"""
        
        summary_l2 = call_llm(prompt_level2)
        
        summaries.append({
            "level": 2,
            "summary": summary_l2,
            "message_count": len(recent_messages)
        })
    
    # Save to file
    hier_file = f"{SUMMARIZED_DIR}/hierarchical_{date_str}.json"
    os.makedirs(SUMMARIZED_DIR, exist_ok=True)
    
    hier_data = {
        "date": date_str,
        "agent": agent_id,
        "levels": levels,
        "summaries": summaries,
        "tokens_freed": tokens_freed
    }
    
    with open(hier_file, 'w') as f:
        json.dump(hier_data, f, indent=2)
    
    return {
        "success": True,
        "summaries": summaries,
        "tokens_freed": tokens_freed,
        "file": hier_file
    }


# ============================================================
# Main CLI
# ============================================================

def main():
    if len(sys.argv) < 2:
        print("Usage: context_optimizer.py <command>")
        print("Commands:")
        print("  status              - Check context usage")
        print("  check               - Check and auto-compact if needed")
        print("  check-optimize      - Hybrid optimization (warn at 50%, act at 60%)")
        print("  detect-topic [agent] - Detect topic shift (default: main)")
        print("  compact <level>    - Run compaction (1-3)")
        print("  summarize [agent]  - Summarize old messages, keep last 50")
        print("  prune [agent]      - Remove low-value messages")
        print("  hierarchical [agent] - Multi-level summarization")
        print("  cost [agent]       - Show session cost estimate")
        print("  archive [agent]    - Archive session to backup")
        print("  truncate [agent]   - Force truncate session to ~30K tokens")
        print("  cleanup            - Clean up stale sessions")
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
        
    elif cmd == "truncate":
        # Force truncate
        result = summarize_and_truncate(agent_id, target_tokens=30000)
        print(json.dumps(result, indent=2))
        
    elif cmd == "cleanup":
        result = cleanup_stale_sessions(agent_id)
        print(json.dumps(result, indent=2))
        
    elif cmd == "summarize":
        # Manual summarize old messages
        result = summarize_old_messages(agent_id, keep_last=50)
        print(json.dumps(result, indent=2))
        
    elif cmd == "prune":
        # Remove low-value messages
        result = prune_low_value_messages(agent_id)
        print(json.dumps(result, indent=2))
        
    elif cmd == "hierarchical":
        # Multi-level summarization
        result = hierarchical_summarize(agent_id, levels=2)
        print(json.dumps(result, indent=2))
        
    elif cmd == "cost":
        # Show session cost estimate
        input_tokens, context_limit = get_current_session_tokens(agent_id)
        # Estimate output as 30% of input (rough guess)
        output_tokens = int(input_tokens * 0.3)
        result = get_session_cost(input_tokens, output_tokens)
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
