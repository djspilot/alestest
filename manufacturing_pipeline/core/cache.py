"""
Cache management for manufacturing pipeline.
Handles file hashing, cache I/O, and result caching with invalidation.
"""

import os
import json
import hashlib
from datetime import datetime

# Cache file location
CACHE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "db",
    "pipeline_cache.json"
)


def get_file_hash(filepath):
    """Calculate MD5 hash of a file."""
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_cache():
    """Load cache from disk."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_cache(cache):
    """Save cache to disk."""
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)


def get_cached_result(filepath, cache):
    """Get cached result if file hasn't changed."""
    file_hash = get_file_hash(filepath)
    cache_key = os.path.abspath(filepath)
    
    if cache_key in cache:
        cached = cache[cache_key]
        if cached.get('hash') == file_hash:
            return cached.get('result')
    return None


def cache_result(filepath, result, cache):
    """Cache a result for a file."""
    file_hash = get_file_hash(filepath)
    cache_key = os.path.abspath(filepath)
    
    cache[cache_key] = {
        'hash': file_hash,
        'result': result,
        'cached_at': datetime.now().isoformat()
    }
    return cache
