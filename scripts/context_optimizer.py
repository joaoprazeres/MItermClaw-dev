#!/usr/bin/env python3
"""
Context Optimizer for OpenClaw

Implements smart topic-based context compaction:
- Detects topic shifts via semantic similarity
- Triggers aggressive compaction when needed
- Supports multiple levels: summarize, aggressive, purge

Usage:
    python3 context_optimizer.py --session <session-id> --check
    python3 context_optimizer.py --session <session-id> --compact --level 2
"""

import json
import os
import sys
import argparse
from pathlib import Path
from typing import List, Dict, Any, Tuple
import re

# Configuration
AGENTS_DIR = Path.home() / ".openclaw" / "agents"
MAX_TOKENS_DEFAULT = 100000  # Leave some buffer below 128K
TOPIC_SHIFT_THRESHOLD = 0.35  # Similarity below this = topic shift
EMBEDDING_MODEL = "nomic-embed-text:latest"

def count_tokens(text: str) -> int:
    """Rough token estimation (chars/4 is a common heuristic)."""
    return len(text) // 4

def load_session(session_id: str, agent_id: str = "main") -> List[Dict]:
    """Load session messages from JSONL file."""
    session_file = AGENTS_DIR / agent_id / "sessions" / f"{session_id}.jsonl"
    if not session_file.exists():
        print(f"Session not found: {session_file}")
        return []
    
    messages = []
    with open(session_file, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                messages.append(entry)
            except json.JSONDecodeError:
                continue
    return messages

def extract_messages(messages: List[Dict]) -> List[Dict]:
    """Extract user/assistant messages from session."""
    extracted = []
    for msg in messages:
        if msg.get("type") == "message":
            msg_data = msg.get("message", {})
            role = msg_data.get("role")
            content = msg_data.get("content", [])
            
            # Extract text from content blocks
            text_parts = []
            for block in content:
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
            
            if text_parts and role in ["user", "assistant"]:
                extracted.append({
                    "id": msg.get("id"),
                    "role": role,
                    "content": "\n".join(text_parts),
                    "timestamp": msg.get("timestamp")
                })
    return extracted

def get_context_size(messages: List[Dict]) -> int:
    """Calculate total context size in tokens."""
    total = 0
    for msg in messages:
        # Count the full message as JSON string, not just content
        total += count_tokens(json.dumps(msg))
    return total

def get_session_file_size(session_id: str, agent_id: str = "main") -> int:
    """Get actual session file size in bytes."""
    session_file = AGENTS_DIR / agent_id / "sessions" / f"{session_id}.jsonl"
    if session_file.exists():
        return session_file.stat().st_size
    return 0

def estimate_tokens_from_bytes(size_bytes: int) -> int:
    """Estimate tokens from file size (rough: ~4 chars/token for text)."""
    return size_bytes // 4

def detect_topic_shifts(messages: List[Dict]) -> List[int]:
    """
    Detect topic shifts by analyzing message content.
    Returns list of indices where topic shifts occur.
    
    Uses multiple heuristics:
    1. Explicit topic shift markers (regex)
    2. Length-based patterns (short reply after long discussion)
    3. Question density changes
    4. Semantic indicators (code blocks, different formatting)
    """
    if len(messages) < 4:
        return []
    
    topic_shift_indices = []
    
    # Topic shift indicators - explicit markers
    shift_patterns = [
        r'^ok[,\s]',
        r'^okay[,\s]',
        r'^sure[,\s]',
        r'^yes[,\s]',
        r'^yeah[,\s]',
        r'^alright[,\s]',
        r'^now[,\s]',
        r'^moving on',
        r'^changing subject',
        r'^by the way',
        r'^btw',
        r'^new topic',
        r'^question:',
        r'^quick question',
        r'^actually[,\s]',
        r'^wait[,\s]',
        r'^hold on[,\s]',
        r'^before that',
        r'^forgot to mention',
        r'^different topic',
    ]
    
    # New topic starters after assistant response (user initiating)
    user_shift_patterns = [
        r'^.+:\s*$',  # Role mention like "User:" or "DevClaw:"
        r'^(hi|hello|hey|sup)',  # Greetings
    ]
    
    for i in range(1, len(messages)):
        prev_msg = messages[i-1].get("content", "").lower()
        curr_msg = messages[i].get("content", "").lower()
        curr_role = messages[i].get("role", "")
        
        # Check 1: Explicit topic starters
        for pattern in shift_patterns:
            if re.match(pattern, curr_msg):
                topic_shift_indices.append(i)
                break
        
        # Check 2: User initiating new topic after assistant response
        if curr_role == "user":
            for pattern in user_shift_patterns:
                if re.match(pattern, curr_msg):
                    topic_shift_indices.append(i)
                    break
        
        # Check 3: Short message after long discussion (likely topic change)
        prev_len = len(prev_msg)
        curr_len = len(curr_msg)
        
        # Very short reply after long response = potential topic change
        if curr_len < 30 and prev_len > 300:
            topic_shift_indices.append(i)
        
        # Check 4: Significant shift in message structure
        # Code blocks appearing/disappearing
        prev_has_code = '```' in messages[i-1].get("content", "")
        curr_has_code = '```' in curr_msg
        if prev_has_code != curr_has_code and curr_role == "user":
            topic_shift_indices.append(i)
        
        # Check 5: Question density shift
        # Many questions after explanatory response = new topic
        prev_question_density = prev_msg.count('?') / max(len(prev_msg), 1) * 100
        curr_question_density = curr_msg.count('?') / max(len(curr_msg), 1) * 100
        if curr_question_density > 2 and prev_question_density < 0.5:
            topic_shift_indices.append(i)
    
    return list(set(topic_shift_indices))

def create_summary(messages: List[Dict]) -> str:
    """Create a brief summary of a set of messages."""
    if not messages:
        return ""
    
    summary_parts = [f"[{len(messages)} messages summarized]"]
    
    # Extract key topics/actions
    user_msgs = [m for m in messages if m.get("role") == "user"]
    assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
    
    if user_msgs:
        # Get first and last user message topics
        first_topic = user_msgs[0].get("content", "")[:100]
        last_topic = user_msgs[-1].get("content", "")[:100]
        summary_parts.append(f"User discussed: {first_topic} ... {last_topic}")
    
    if assistant_msgs:
        summary_parts.append(f"Assistant responded {len(assistant_msgs)} times")
    
    return " | ".join(summary_parts)

def compact_session_level1(session_entries: List[Dict], keep_recent: int = 50) -> List[Dict]:
    """
    Level 1: Standard compaction - summarize older entries, keep recent.
    """
    if len(session_entries) <= keep_recent:
        return session_entries
    
    # Keep recent entries
    recent = session_entries[-keep_recent:]
    
    # Get older entries for summary
    older = session_entries[:-keep_recent]
    
    # Summarize older entries
    summary = create_summary_from_entries(older)
    
    # Add summary as a compaction event
    compacted = [{
        "type": "context_compaction",
        "id": "compaction_summary",
        "timestamp": recent[0].get("timestamp"),
        "compaction_level": 1,
        "original_entries": len(older),
        "summary": summary
    }]
    compacted.extend(recent)
    
    return compacted

def compact_session_level2(session_entries: List[Dict], keep_recent: int = 25) -> List[Dict]:
    """
    Level 2: Aggressive - keep fewer recent entries, summarize more.
    """
    if len(session_entries) <= keep_recent:
        return session_entries
    
    recent = session_entries[-keep_recent:]
    older = session_entries[:-keep_recent]
    
    # More aggressive summary
    summary = f"[{len(older)} earlier entries summarized]"
    
    compacted = [{
        "type": "context_compaction",
        "id": "compaction_aggressive",
        "timestamp": recent[0].get("timestamp"),
        "compaction_level": 2,
        "original_entries": len(older),
        "summary": summary
    }]
    compacted.extend(recent)
    
    return compacted

def compact_session_level3(session_entries: List[Dict], keep_recent: int = 10) -> List[Dict]:
    """
    Level 3: Complete purge - keep very few recent entries.
    """
    if len(session_entries) <= keep_recent:
        return session_entries
    
    recent = session_entries[-keep_recent:]
    
    compacted = [{
        "type": "context_compaction",
        "id": "compaction_purge",
        "timestamp": recent[0].get("timestamp"),
        "compaction_level": 3,
        "entries_removed": len(session_entries) - keep_recent
    }]
    compacted.extend(recent)
    
    return compacted

def create_summary_from_entries(entries: List[Dict]) -> str:
    """Create summary from session entries."""
    message_count = sum(1 for e in entries if e.get("type") == "message")
    tool_count = sum(1 for e in entries if e.get("type") in ["tool_call", "tool_result"])
    
    summary = f"{message_count} messages, {tool_count} tool interactions"
    
    # Try to get first/last topics
    messages = [e for e in entries if e.get("type") == "message" and e.get("message", {}).get("role") == "user"]
    if messages:
        first = messages[0].get("message", {}).get("content", [{}])[0].get("text", "")[:50]
        if len(messages) > 1:
            last = messages[-1].get("message", {}).get("content", [{}])[0].get("text", "")[:50]
            summary += f" | Started: {first}... Ended: {last}"
    
    return summary

def save_compacted_session(session_id: str, compacted_messages: List[Dict], agent_id: str = "main"):
    """Save compacted messages back to session - actually truncates the file."""
    session_file = AGENTS_DIR / agent_id / "sessions" / f"{session_id}.jsonl"
    
    # Create backup
    backup_file = session_file.with_suffix('.jsonl.compact.backup')
    if session_file.exists():
        import shutil
        shutil.copy(session_file, backup_file)
        print(f"Backup created: {backup_file}")
    
    # Rewrite session file with compacted messages only
    with open(session_file, 'w') as f:
        for msg in compacted_messages:
            f.write(json.dumps(msg) + "\n")
    
    print(f"Compaction applied. Session rewritten with {len(compacted_messages)} entries.")

def analyze_session(session_id: str, agent_id: str = "main"):
    """Analyze session and report its state."""
    messages = load_session(session_id, agent_id)
    user_messages = extract_messages(messages)
    
    if not user_messages:
        print("No messages found in session")
        return
    
    # Get actual file size for more accurate estimate
    file_size = get_session_file_size(session_id, agent_id)
    file_tokens = estimate_tokens_from_bytes(file_size)
    
    # Also count message content
    content_tokens = get_context_size(user_messages)
    context_size = max(file_tokens, content_tokens)
    
    topic_shifts = detect_topic_shifts(user_messages)
    
    print(f"=== Session Analysis ===")
    print(f"Session ID: {session_id}")
    print(f"Total entries: {len(messages)}")
    print(f"User/assistant messages: {len(user_messages)}")
    print(f"File size: {file_size:,} bytes (~{file_tokens:,} tokens)")
    print(f"Content tokens: ~{content_tokens:,}")
    print(f"Estimated total: ~{context_size:,} tokens")
    print(f"Context usage: {context_size/MAX_TOKENS_DEFAULT*100:.1f}%")
    print(f"Topic shift points: {len(topic_shifts)} detected")
    
    # Show where topic shifts occurred
    if topic_shifts:
        print(f"\n📍 Topic shift locations:")
        for idx in topic_shifts[:5]:  # Show first 5
            if idx < len(user_messages):
                msg_preview = user_messages[idx].get("content", "")[:60].replace('\n', ' ')
                role = user_messages[idx].get("role", "?")
                print(f"   [{idx}] {role}: {msg_preview}...")
    
    if context_size > MAX_TOKENS_DEFAULT * 0.8:
        print(f"\n⚠️  WARNING: Context at {context_size/MAX_TOKENS_DEFAULT*100:.1f}% - COMPACTION NEEDED!")
    elif context_size > MAX_TOKENS_DEFAULT * 0.6:
        print(f"\n⚡ Notice: Context at {context_size/MAX_TOKENS_DEFAULT*100:.1f}% - consider compaction soon")

def main():
    parser = argparse.ArgumentParser(description="OpenClaw Context Optimizer")
    parser.add_argument("--session", help="Session ID")
    parser.add_argument("--agent", default="main", help="Agent ID (default: main)")
    parser.add_argument("--check", action="store_true", help="Analyze session")
    parser.add_argument("--compact", action="store_true", help="Compact session")
    parser.add_argument("--level", type=int, choices=[1, 2, 3], default=1, help="Compaction level (1=summarize, 2=aggressive, 3=purge)")
    parser.add_argument("--keep", type=int, default=0, help="Number of recent messages to keep (0=default)")
    
    args = parser.parse_args()
    
    if args.check and args.session:
        analyze_session(args.session, args.agent)
    elif args.compact and args.session:
        # Load FULL session entries (not just messages)
        session_entries = load_session(args.session, args.agent)
        
        keep_count = args.keep if args.keep > 0 else 25
        
        print(f"Compacting {len(session_entries)} session entries, keeping {keep_count} recent...")
        
        if args.level == 1:
            compacted = compact_session_level1(session_entries, keep_recent=keep_count)
            print(f"Applied Level 1 compaction (summarize)")
        elif args.level == 2:
            compacted = compact_session_level2(session_entries, keep_recent=keep_count)
            print(f"Applied Level 2 compaction (aggressive)")
        else:
            compacted = compact_session_level3(session_entries, keep_recent=keep_count)
            print(f"Applied Level 3 compaction (purge)")
        
        # Save
        save_compacted_session(args.session, compacted, args.agent)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()