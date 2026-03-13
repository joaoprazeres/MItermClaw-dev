#!/usr/bin/env python3
"""
Internet Access System for OpenClaw
Priorities 1-3: Search, Fetch, Research Loop
"""

import json
import subprocess
import requests
from typing import List, Dict, Any, Optional
from urllib.parse import quote

# ============== Configuration ==============

# SearXNG instance
SEARXNG_URL = "https://searx.alienubserv.joaoprazeres.pt"

# Ollama Cloud API (requires OLLAMA_API_KEY from https://ollama.com/settings/keys)
OLLAMA_CLOUD_API_KEY = None  # Set your API key here or via env var
OLLAMA_WEB_SEARCH_URL = "https://ollama.com/api/web_search"
OLLAMA_WEB_FETCH_URL = "https://ollama.com/api/web_fetch"

# God Layer - Model providers with fallback
MODEL_PROVIDERS = [
    {
        "name": "ollama-local",
        "url": "http://127.0.0.1:11434/api/chat",
        "model": "minimax-m2.5:cloud",
        "timeout": 60
    },
    {
        "name": "remote",
        "url": "https://llama.alienubserv.joaoprazeres.pt/api/chat",
        "model": "phi4-mini:3.8b",
        "timeout": 60
    },
    {
        "name": "ollama-phi4",
        "url": "http://127.0.0.1:11434/api/chat",
        "model": "phi4",
        "timeout": 60
    }
]


# ============== Priority 1: Simple Search Wrapper ==============

def simple_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Search using SearXNG instance.
    
    Args:
        query: Search query string
        max_results: Maximum number of results to return (default: 5)
    
    Returns:
        List of dicts with keys: title, url, content, engine, score
    """
    try:
        # Use SearXNG search API
        search_url = f"{SEARXNG_URL}/search"
        params = {
            "q": query,
            "format": "json",
            "engines": "general",
            "categories": "general",
            "limit": max_results
        }
        
        response = requests.get(search_url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get("results", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
                "engine": item.get("engine", "unknown"),
                "score": item.get("score", 0.0)
            })
        
        return results
        
    except Exception as e:
        print(f"Search error: {e}")
        return []


# ============== Priority 2: URL Content Fetcher ==============

def fetch_content(urls: List[str], max_chars: int = 8000) -> Dict[str, str]:
    """
    Fetch and extract text content from URLs.
    
    Note: This uses the web_fetch tool from OpenClaw, which is called via subprocess.
    For direct HTTP fetching, we use requests as fallback.
    
    Args:
        urls: List of URLs to fetch
        max_chars: Maximum characters to extract per URL
    
    Returns:
        Dict mapping URL to extracted content
    """
    results = {}
    
    for url in urls:
        try:
            # Try using the OpenClaw web_fetch tool
            cmd = f"openclaw web-fetch --url \"{url}\" --max-chars {max_chars}"
            result = subprocess.run(
                cmd, 
                shell=True, 
                capture_output=True, 
                text=True, 
                timeout=30
            )
            
            if result.returncode == 0 and result.stdout.strip():
                results[url] = result.stdout.strip()
            else:
                # Fallback: use requests to fetch directly
                response = requests.get(url, timeout=15, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; OpenClaw/1.0)"
                })
                response.raise_for_status()
                
                # Simple HTML stripping (basic version)
                content = response.text
                # Remove script and style tags
                import re
                content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
                content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
                # Remove HTML tags
                content = re.sub(r'<[^>]+>', ' ', content)
                # Clean up whitespace
                content = ' '.join(content.split())
                # Truncate
                content = content[:max_chars]
                results[url] = content
                
        except Exception as e:
            print(f"Fetch error for {url}: {e}")
            results[url] = f"[Error fetching content: {e}]"
    
    return results


# ============== Compression Helpers ==============

def count_tokens(text: str) -> int:
    """Rough token estimation (~4 chars per token)."""
    return len(text) // 4


def summarize_iterations(iterations_data: list, keep_last: int = 1) -> str:
    """
    Compress old iterations into a summary.
    
    Args:
        iterations_data: List of iteration dicts
        keep_last: Number of recent iterations to keep fully
    
    Returns:
        Summary string of old iterations
    """
    if len(iterations_data) <= keep_last:
        return ""
    
    # Keep last N iterations fully
    recent = iterations_data[-keep_last:]
    old = iterations_data[:-keep_last]
    
    if not old:
        return ""
    
    # Summarize old iterations
    summary = "Previous Research Summary:\n"
    for iter_data in old:
        iter_num = iter_data.get("iteration", "?")
        query = iter_data.get("query", "")
        response = iter_data.get("llm_response", "No response")[:200]
        sources = [r.get("title", "") for r in iter_data.get("search_results", [])[:3]]
        
        summary += f"\n- Iteration {iter_num}: '{query}' → {response}..."
        if sources:
            summary += f" (Sources: {', '.join(sources[:2])})"
    
    return summary


def compress_context(context: str, max_tokens: int = 3000) -> str:
    """
    Compress context if it exceeds token limit.
    
    Args:
        context: Full context string
        max_tokens: Maximum tokens to keep
    
    Returns:
        Compressed context
    """
    tokens = count_tokens(context)
    
    if tokens <= max_tokens:
        return context
    
    # If too long, truncate but keep beginning and end (most important)
    # Keep ~60% from start, 40% from end
    chars_limit = max_tokens * 4
    
    if len(context) > chars_limit:
        start_portion = int(chars_limit * 0.6)
        end_portion = chars_limit - start_portion
        
        start = context[:start_portion]
        end = context[-end_portion:] if end_portion > 0 else ""
        
        return f"{start}\n\n[... content truncated ...]\n\n{end}"
    
    return context


# ============== OPTION 3: Session-Level Compression ==============

def compress_messages(messages: list, max_tokens: int = 3500) -> list:
    """
    Compress a list of chat messages for session continuity.
    
    Strategy:
    1. Keep system prompt
    2. Keep recent messages (last 4)
    3. Summarize older messages into a compact summary
    
    Args:
        messages: List of message dicts with 'role' and 'content'
        max_tokens: Target max tokens for compressed history
    
    Returns:
        Compressed messages list
    """
    if not messages:
        return messages
    
    # Find system message
    system_msg = None
    non_system = []
    
    for msg in messages:
        if msg.get("role") == "system":
            system_msg = msg
        else:
            non_system.append(msg)
    
    # Keep last 4 messages fully
    KEEP_RECENT = 4
    if len(non_system) <= KEEP_RECENT + 1:
        # Not too many messages, return as-is
        return messages
    
    recent = non_system[-KEEP_RECENT:]
    old = non_system[:-KEEP_RECENT]
    
    # Summarize old messages
    old_text = "\n".join([
        f"{m['role']}: {m['content'][:150]}..." if len(m.get('content', '')) > 150 else f"{m['role']}: {m['content']}"
        for m in old
    ])
    
    # Create summary of old messages
    summary_prompt = f"Compress this chat history into a brief summary:\n\n{old_text[:2000]}"
    summary = call_llm(summary_prompt, "Summarize briefly. Include key topics and any important conclusions.")
    
    # Build compressed messages
    compressed = []
    if system_msg:
        compressed.append(system_msg)
    
    compressed.append({
        "role": "system",
        "content": f"[Previous conversation summary: {summary[:300] if summary else 'Earlier chat'}]"
    })
    
    compressed.extend(recent)
    
    return compressed


def estimate_session_tokens(messages: list) -> int:
    """Estimate total tokens in a message session."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        total += count_tokens(content)
    return total


# ============== Helper: LLM Interaction ==============

def call_llm(prompt: str, system_prompt: str = "You are a helpful assistant.") -> Optional[str]:
    """
    Call LLM with fallback through providers.
    
    Args:
        prompt: User prompt
        system_prompt: System prompt
    
    Returns:
        LLM response string or None if all providers fail
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt[:4000]}  # Truncate prompt to avoid context overflow
    ]
    
    for provider in MODEL_PROVIDERS:
        try:
            payload = {
                "model": provider["model"],
                "messages": messages,
                "stream": False,
                "options": {
                    "num_ctx": 4096,
                    "num_predict": 512
                }
            }
            
            response = requests.post(
                provider["url"], 
                json=payload, 
                timeout=provider["timeout"]
            )
            response.raise_for_status()
            
            data = response.json()
            return data.get("message", {}).get("content", "")
            
        except Exception as e:
            print(f"Provider {provider['name']} failed: {e}")
            continue
    
    return None


# ============== Priority 3: Research Loop ==============

def research_loop(query: str, max_iterations: int = 3) -> Dict[str, Any]:
    """
    Research loop: search → fetch → LLM analyze → refine → repeat.
    
    Args:
        query: Research question
        max_iterations: Maximum loops (default: 3)
    
    Returns:
        Dict with keys: answer, sources, iterations
    """
    iterations_data = []
    current_query = query
    final_answer = None
    
    for i in range(max_iterations):
        print(f"\n--- Iteration {i + 1}/{max_iterations} ---")
        
        # Step 1: Search
        print(f"Searching: {current_query}")
        search_results = simple_search(current_query, max_results=5)
        
        if not search_results:
            iterations_data.append({
                "iteration": i + 1,
                "query": current_query,
                "search_results": [],
                "error": "No search results found"
            })
            break
        
        # Step 2: Fetch content from top results
        urls = [r["url"] for r in search_results[:3]]  # Top 3
        print(f"Fetching: {urls}")
        content_map = fetch_content(urls)
        
        # OPTION 2: Compress previous iterations for this research loop
        research_summary = ""
        if i > 0:
            # Summarize old iterations, keep last one fully
            research_summary = summarize_iterations(iterations_data, keep_last=1)
        
        # Prepare context for LLM
        context = f"Research Query: {current_query}\n\n"
        
        # Add compressed summary from previous iterations
        if research_summary:
            context += f"{research_summary}\n\n"
            context += "---\n\n"
        
        context += "Current Search Results:\n"
        for idx, result in enumerate(search_results):
            context += f"\n[{idx+1}] {result['title']}\n"
            context += f"URL: {result['url']}\n"
            context += f"Content: {result['content']}\n"
        
        context += "\n\nFetched Content:\n"
        for url, content in content_map.items():
            context += f"\n--- {url} ---\n{content[:800]}\n"
        
        # Compress context if too long
        context = compress_context(context, max_tokens=3000)
        
        # Step 3: LLM Analyze
        analysis_prompt = f"""You are researching: {query}

Based on the search results and fetched content, provide a comprehensive answer.
If this is iteration 1, summarize what you found.
If this is iteration 2+, refine your answer based on new information.

Context:
{context}

Provide your answer:"""

        llm_response = call_llm(analysis_prompt, "You are a research assistant. Provide accurate, well-sourced answers.")
        
        iterations_data.append({
            "iteration": i + 1,
            "query": current_query,
            "search_results": search_results,
            "urls_fetched": urls,
            "llm_response": llm_response
        })
        
        if llm_response:
            final_answer = llm_response
            
            # Check if we need another iteration (refine query)
            if i < max_iterations - 1:
                # Generate refined query based on what's missing
                refine_prompt = f"""Based on this research so far:
                
Query: {query}
Current Answer: {llm_response}

What aspects need more research? Provide a refined search query (just the query, nothing else) to find missing information. 
If the answer seems complete, respond with just: DONE"""
                
                refined = call_llm(refine_prompt, "You are helping refine research queries.")
                
                if refined and "DONE" not in refined.upper():
                    current_query = refined.strip()
                    print(f"Refined query: {current_query}")
                else:
                    print("Research complete")
                    break
        else:
            iterations_data[-1]["error"] = "LLM call failed"
            break
    
    # Compile sources
    sources = []
    for iter_data in iterations_data:
        for result in iter_data.get("search_results", []):
            if result["url"] not in [s["url"] for s in sources]:
                sources.append({
                    "title": result["title"],
                    "url": result["url"],
                    "engine": result["engine"]
                })
    
    return {
        "answer": final_answer or "No answer generated",
        "sources": sources,
        "iterations": iterations_data
    }


# ============== CLI / Testing ==============

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python internet.py search <query>")
        print("  python internet.py fetch <url1> [url2] ...")
        print("  python internet.py research <query>")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "search":
        query = " ".join(sys.argv[2:])
        print(f"Searching for: {query}")
        results = simple_search(query)
        print(json.dumps(results, indent=2))
        
    elif command == "fetch":
        urls = sys.argv[2:]
        print(f"Fetching: {urls}")
        content = fetch_content(urls)
        for url, text in content.items():
            print(f"\n=== {url} ===")
            print(text[:500] + "..." if len(text) > 500 else text)
            
    elif command == "research":
        query = " ".join(sys.argv[2:])
        print(f"Researching: {query}")
        result = research_loop(query)
        print("\n=== ANSWER ===")
        print(result["answer"])
        print("\n=== SOURCES ===")
        for s in result["sources"]:
            print(f"- {s['title']}: {s['url']}")
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)