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
        
        # Prepare context for LLM
        context = f"Research Query: {current_query}\n\n"
        context += "Search Results:\n"
        for idx, result in enumerate(search_results):
            context += f"\n[{idx+1}] {result['title']}\n"
            context += f"URL: {result['url']}\n"
            context += f"Content: {result['content']}\n"
        
        context += "\n\nFetched Content:\n"
        for url, content in content_map.items():
            context += f"\n--- {url} ---\n{content[:1000]}\n"
        
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