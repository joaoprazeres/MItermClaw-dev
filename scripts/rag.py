#!/usr/bin/env python3
"""
RAG System for OpenClaw
Priorities 1-4: File Walker, Chunker, Embed & Store, Query Function
"""

import os
import json
import math
from pathlib import Path
from typing import List, Dict, Any, Optional
import subprocess

# Configuration
SUPPORTED_EXTENSIONS = {'.md', '.txt', '.py', '.js', '.json', '.yaml', '.yml'}
MAX_FILE_SIZE = 1 * 1024 * 1024  # 1MB
CHUNK_SIZE_TOKENS = 512
CHUNK_OVERLAP_TOKENS = 50
EMBED_MODEL = "nomic-embed-text"
INDEX_DIR = ".index"
EMBEDDINGS_FILE = "embeddings.json"
MANIFEST_FILE = "manifest.json"


def is_binary(file_path: Path) -> bool:
    """Check if a file is binary by reading first few bytes."""
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(1024)
            # Check for null bytes or other binary indicators
            return b'\x00' in chunk
    except Exception:
        return True


def count_tokens(text: str) -> int:
    """Estimate token count (rough approximation: ~4 chars per token)."""
    return len(text) // 4


# Priority 1: File Walker
def walk_files(project_path: str) -> List[str]:
    """
    Find all supported files in the project.
    Skip binary files, hidden files, and files > 1MB.
    """
    project_path = Path(project_path)
    supported_files = []
    
    for root, dirs, files in os.walk(project_path):
        # Skip hidden directories and index directory
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != INDEX_DIR]
        
        for filename in files:
            file_path = Path(root) / filename
            
            # Skip hidden files
            if filename.startswith('.'):
                continue
            
            # Check extension
            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            
            # Skip files > 1MB
            try:
                if file_path.stat().st_size > MAX_FILE_SIZE:
                    print(f"  Skipping (too large): {file_path}")
                    continue
            except Exception:
                continue
            
            # Skip binary files
            if is_binary(file_path):
                print(f"  Skipping (binary): {file_path}")
                continue
            
            supported_files.append(str(file_path))
    
    return supported_files


# Priority 2: Chunker
def chunk_file(file_path: str, overlap: int = CHUNK_OVERLAP_TOKENS) -> List[Dict[str, Any]]:
    """
    Split file content into chunks.
    Each chunk gets: content, file_path, line_number
    """
    chunks = []
    file_path = Path(file_path)
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"  Error reading {file_path}: {e}")
        return chunks
    
    if not content.strip():
        return chunks
    
    # Split by paragraphs first (double newlines)
    paragraphs = content.split('\n\n')
    
    current_chunk = ""
    current_lines = 0
    start_line = 1
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        para_tokens = count_tokens(para)
        current_tokens = count_tokens(current_chunk)
        
        # If single paragraph exceeds chunk size, split it further
        if para_tokens > CHUNK_SIZE_TOKENS:
            # First, save current chunk if non-empty
            if current_chunk:
                chunks.append({
                    'content': current_chunk.strip(),
                    'file_path': str(file_path),
                    'line_number': start_line
                })
                current_chunk = ""
                current_lines = 0
            
            # Split long paragraph by sentences/lines
            lines = para.split('\n')
            temp_chunk = ""
            temp_lines = 0
            chunk_start = 0
            
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                
                temp_chunk += line + "\n"
                temp_lines += 1
                
                if count_tokens(temp_chunk) >= CHUNK_SIZE_TOKENS:
                    chunks.append({
                        'content': temp_chunk.strip(),
                        'file_path': str(file_path),
                        'line_number': chunk_start + 1
                    })
                    # Keep overlap
                    overlap_text = '\n'.join(lines[max(0, i-overlap//5):i])
                    temp_chunk = overlap_text + "\n" + line + "\n"
                    temp_lines = len(overlap_text.split('\n')) + 1
                    chunk_start = i
            
            if temp_chunk.strip():
                current_chunk = temp_chunk
                current_lines = temp_lines
                start_line = chunk_start + 1
        else:
            # Check if adding this paragraph would exceed limit
            if current_tokens + para_tokens > CHUNK_SIZE_TOKENS and current_chunk:
                chunks.append({
                    'content': current_chunk.strip(),
                    'file_path': str(file_path),
                    'line_number': start_line
                })
                
                # Keep overlap - last few paragraphs/sentences
                overlap_words = []
                word_count = 0
                for p in reversed(current_chunk.split('\n\n')):
                    overlap_words.append(p)
                    word_count += len(p.split())
                    if word_count * 4 > overlap * 4:  # ~4 chars per token
                        break
                current_chunk = '\n\n'.join(reversed(overlap_words))
                current_lines = len(overlap_words)
            
            current_chunk += para + "\n\n"
    
    # Don't forget the last chunk
    if current_chunk.strip():
        chunks.append({
            'content': current_chunk.strip(),
            'file_path': str(file_path),
            'line_number': start_line
        })
    
    return chunks


def get_embedding(text: str) -> List[float]:
    """Generate embedding using Ollama API with nomic-embed-text."""
    import urllib.request
    import urllib.error
    
    try:
        data = json.dumps({
            'model': EMBED_MODEL,
            'prompt': text
        }).encode('utf-8')
        
        req = urllib.request.Request(
            'http://localhost:11434/api/embeddings',
            data=data,
            headers={'Content-Type': 'application/json'}
        )
        
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('embedding', [])
            
    except urllib.error.HTTPError as e:
        print(f"    HTTP Error: {e.code} - {e.reason}")
        return []
    except Exception as e:
        print(f"    Embedding exception: {e}")
        return []


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    
    dot_product = sum(x * y for x, y in zip(a, b))
    magnitude_a = math.sqrt(sum(x * x for x in a))
    magnitude_b = math.sqrt(sum(x * x for x in b))
    
    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0
    
    return dot_product / (magnitude_a * magnitude_b)


# Priority 3: Embed & Store
def embed_and_store(project_path: str) -> Dict[str, Any]:
    """
    Index all supported files in the project.
    Generate embeddings and store in .index/embeddings.json
    """
    project_path = Path(project_path)
    index_dir = project_path / INDEX_DIR
    index_dir.mkdir(exist_ok=True)
    
    print(f"\n=== Priority 3: Embed & Store ===")
    
    # Priority 1: Find all files
    print(f"Scanning files in {project_path}...")
    files = walk_files(str(project_path))
    print(f"Found {len(files)} supported files")
    
    # Priority 2 & 3: Chunk and embed
    all_chunks = []
    embeddings = []
    stats = {
        'total_files': len(files),
        'total_chunks': 0,
        'failed_files': []
    }
    
    for i, file_path in enumerate(files):
        rel_path = Path(file_path).relative_to(project_path)
        print(f"  [{i+1}/{len(files)}] Processing: {rel_path}")
        
        # Chunk the file
        chunks = chunk_file(file_path)
        
        if not chunks:
            print(f"    No content to chunk")
            continue
        
        # Generate embeddings for each chunk
        for chunk in chunks:
            embedding = get_embedding(chunk['content'])
            
            if embedding:
                embeddings.append({
                    'embedding': embedding,
                    'content': chunk['content'],
                    'file_path': str(Path(file_path).relative_to(project_path)),
                    'line_number': chunk['line_number']
                })
            else:
                print(f"    Failed to embed chunk at line {chunk['line_number']}")
        
        if embeddings:
            stats['total_chunks'] = len(embeddings)
        else:
            stats['failed_files'].append(str(rel_path))
        
        # Progress indicator every 5 files
        if (i + 1) % 5 == 0:
            print(f"  Progress: {i+1}/{len(files)} files, {len(embeddings)} chunks")
    
    # Store embeddings
    embeddings_path = index_dir / EMBEDDINGS_FILE
    with open(embeddings_path, 'w') as f:
        json.dump(embeddings, f, indent=2)
    print(f"Stored {len(embeddings)} embeddings in {embeddings_path}")
    
    # Create manifest
    manifest = {
        'project_path': str(project_path),
        'indexed_at': str(Path(__file__).stat().st_mtime) if Path(__file__).exists() else 'unknown',
        'embed_model': EMBED_MODEL,
        'chunk_size_tokens': CHUNK_SIZE_TOKENS,
        'chunk_overlap_tokens': CHUNK_OVERLAP_TOKENS,
        'total_files': stats['total_files'],
        'total_chunks': stats['total_chunks'],
        'failed_files': stats['failed_files']
    }
    
    manifest_path = index_dir / MANIFEST_FILE
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    print(f"Created manifest at {manifest_path}")
    
    return manifest


# Priority 4: Query Function
def query_index(project_path: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """
    Search project index and return top_k results.
    Each result: file, chunk, score, line_num
    """
    project_path = Path(project_path)
    embeddings_path = project_path / INDEX_DIR / EMBEDDINGS_FILE
    
    if not embeddings_path.exists():
        print("Index not found. Run indexing first.")
        return []
    
    # Load embeddings
    with open(embeddings_path, 'r') as f:
        embeddings = json.load(f)
    
    if not embeddings:
        print("No embeddings found in index.")
        return []
    
    print(f"\n=== Query: \"{query}\" (top {top_k}) ===")
    
    # Generate query embedding
    query_embedding = get_embedding(query)
    
    if not query_embedding:
        print("Failed to generate query embedding.")
        return []
    
    # Calculate similarities
    results = []
    for item in embeddings:
        score = cosine_similarity(query_embedding, item['embedding'])
        results.append({
            'file': item['file_path'],
            'chunk': item['content'][:200] + '...' if len(item['content']) > 200 else item['content'],
            'score': round(score, 4),
            'line_num': item['line_number'],
            'full_content': item['content']
        })
    
    # Sort by score and return top_k
    results.sort(key=lambda x: x['score'], reverse=True)
    top_results = results[:top_k]
    
    for i, r in enumerate(top_results):
        print(f"\n--- Result {i+1} ---")
        print(f"File: {r['file']}")
        print(f"Line: {r['line_num']}")
        print(f"Score: {r['score']}")
        print(f"Content: {r['chunk'][:150]}...")
    
    return top_results


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='RAG System for OpenClaw')
    parser.add_argument('command', choices=['index', 'query'], help='Command to run')
    parser.add_argument('project', nargs='?', default='.', help='Project path')
    parser.add_argument('--query', '-q', help='Query string (for query command)')
    parser.add_argument('--top-k', '-k', type=int, default=5, help='Number of results')
    
    args = parser.parse_args()
    
    if args.command == 'index':
        print(f"=== Starting Indexing: {args.project} ===")
        manifest = embed_and_store(args.project)
        print(f"\n=== Indexing Complete ===")
        print(f"Files: {manifest['total_files']}")
        print(f"Chunks: {manifest['total_chunks']}")
    elif args.command == 'query':
        if not args.query:
            print("Error: --query required for query command")
            return
        results = query_index(args.project, args.query, args.top_k)
        print(f"\n=== Found {len(results)} results ===")


if __name__ == '__main__':
    main()