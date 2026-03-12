#!/usr/bin/env python3
"""
Memory Index - Simple vector-based memory storage using Ollama embeddings
Stores vectors in JSON, calculates cosine similarity manually
"""

import json
import os
import time
import subprocess
import math
from typing import List, Dict, Any, Optional

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Fix: point to actual workspace, not sibling directory
WORKSPACE = "/data/data/com.termux/files/home/.openclaw/workspace"
INDEX_DIR = os.path.join(WORKSPACE, "memory", ".index")
EMBEDDINGS_FILE = os.path.join(INDEX_DIR, "embeddings.json")
MANIFEST_FILE = os.path.join(INDEX_DIR, "manifest.json")
OLLAMA_MODEL = "nomic-embed-text"


def _run_ollama_embedding(text: str) -> List[float]:
    """Generate embedding using Ollama API"""
    import urllib.request
    import urllib.error
    
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": text
    }
    
    req = urllib.request.Request(
        "http://localhost:11434/api/embeddings",
        data=json.dumps(payload).encode('utf-8'),
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get("embedding", [])
    except urllib.error.URLError as e:
        print(f"Error connecting to Ollama: {e}")
        return []


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Calculate cosine similarity between two vectors manually"""
    if not a or not b or len(a) != len(b):
        return 0.0
    
    dot_product = sum(x * y for x, y in zip(a, b))
    magnitude_a = math.sqrt(sum(x * x for x in a))
    magnitude_b = math.sqrt(sum(x * x for x in b))
    
    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0
    
    return dot_product / (magnitude_a * magnitude_b)


def load_embeddings() -> Dict[str, Any]:
    """Load embeddings from JSON file"""
    if os.path.exists(EMBEDDINGS_FILE):
        with open(EMBEDDINGS_FILE, 'r') as f:
            return json.load(f)
    return {"version": "1.0", "embeddings": []}


def save_embeddings(data: Dict[str, Any]) -> None:
    """Save embeddings to JSON file"""
    with open(EMBEDDINGS_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def load_manifest() -> Dict[str, Any]:
    """Load manifest metadata"""
    if os.path.exists(MANIFEST_FILE):
        with open(MANIFEST_FILE, 'r') as f:
            return json.load(f)
    return {
        "version": "1.0",
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_memories": 0,
        "model": OLLAMA_MODEL
    }


def save_manifest(manifest: Dict[str, Any]) -> None:
    """Save manifest metadata"""
    manifest["last_updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest["total_memories"] = len(load_embeddings().get("embeddings", []))
    with open(MANIFEST_FILE, 'w') as f:
        json.dump(manifest, f, indent=2)


def add_memory(text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Add a memory with automatic embedding generation
    
    Args:
        text: The memory text to store
        metadata: Optional metadata (tags, source, etc.)
    
    Returns:
        Dict with success status and memory info
    """
    print(f"Generating embedding for: {text[:50]}...")
    embedding = _run_ollama_embedding(text)
    
    if not embedding:
        return {"success": False, "error": "Failed to generate embedding"}
    
    memory_entry = {
        "id": f"mem_{int(time.time() * 1000)}",
        "text": text,
        "embedding": embedding,
        "metadata": metadata or {},
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    
    data = load_embeddings()
    data["embeddings"].append(memory_entry)
    save_embeddings(data)
    
    manifest = load_manifest()
    save_manifest(manifest)
    
    return {
        "success": True,
        "memory_id": memory_entry["id"],
        "vector_dim": len(embedding)
    }


def search_memories(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Search memories using cosine similarity
    
    Args:
        query: Search query text
        top_k: Number of top results to return
    
    Returns:
        List of matching memories with similarity scores
    """
    print(f"Searching for: {query}")
    query_embedding = _run_ollama_embedding(query)
    
    if not query_embedding:
        return []
    
    data = load_embeddings()
    results = []
    
    for memory in data.get("embeddings", []):
        similarity = _cosine_similarity(query_embedding, memory.get("embedding", []))
        results.append({
            "id": memory.get("id"),
            "text": memory.get("text"),
            "similarity": similarity,
            "metadata": memory.get("metadata", {}),
            "created_at": memory.get("created_at")
        })
    
    # Sort by similarity (highest first) and return top_k
    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:top_k]


def get_all_memories() -> List[Dict[str, Any]]:
    """Get all stored memories"""
    data = load_embeddings()
    return data.get("embeddings", [])


def clear_memories() -> None:
    """Clear all memories (use with caution)"""
    save_embeddings({"version": "1.0", "embeddings": []})
    manifest = load_manifest()
    save_manifest(manifest)
    print("All memories cleared")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python memory_index.py add <text>")
        print("  python memory_index.py search <query>")
        print("  python memory_index.py list")
        print("  python memory_index.py clear")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "add":
        if len(sys.argv) < 3:
            print("Error: Please provide text to add")
            sys.exit(1)
        text = " ".join(sys.argv[2:])
        result = add_memory(text)
        print(json.dumps(result, indent=2))
    
    elif command == "search":
        if len(sys.argv) < 3:
            print("Error: Please provide search query")
            sys.exit(1)
        query = " ".join(sys.argv[2:])
        results = search_memories(query)
        print(json.dumps(results, indent=2))
    
    elif command == "list":
        memories = get_all_memories()
        print(f"Total memories: {len(memories)}")
        for m in memories:
            print(f"  - {m.get('id')}: {m.get('text')[:60]}...")
    
    elif command == "clear":
        confirm = input("Are you sure? This will delete all memories (y/N): ")
        if confirm.lower() == 'y':
            clear_memories()
        else:
            print("Cancelled")
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)