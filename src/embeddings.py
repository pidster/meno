"""Embedding generation for the meno memory graph.

Uses Ollama with nomic-embed-text for local embedding generation.
Falls back to a simple TF-IDF-like hash embedding for testing.
"""

import json
import math
import os
import urllib.request
from typing import List, Optional
from surrealdb import RecordID


OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
EMBED_DIM = 768  # nomic-embed-text dimension


def embed(text: str) -> Optional[List[float]]:
    """Generate an embedding vector for the given text.

    Uses Ollama API. Returns None if Ollama is unavailable.
    """
    try:
        return _ollama_embed(text)
    except Exception:
        return None


def _ollama_embed(text: str) -> List[float]:
    """Call Ollama embedding API."""
    payload = json.dumps({"model": EMBED_MODEL, "input": text}).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/embed",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    embeddings = data.get("embeddings", [[]])
    if embeddings and len(embeddings[0]) > 0:
        return embeddings[0]
    raise ValueError("Empty embedding returned")


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b) or len(a) == 0:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def embed_and_store(client, record_id: str, text: str) -> bool:
    """Generate embedding and store it on a node.

    Args:
        client: SurrealDB client
        record_id: Node ID as "table:id" string
        text: Text to embed

    Returns:
        True if embedding was stored, False if generation failed.
    """
    vec = embed(text)
    if vec is None:
        return False

    parts = record_id.split(":", 1)
    if len(parts) != 2:
        return False

    rid = RecordID(parts[0], parts[1])
    client.query(
        "UPDATE $node SET embedding = $vec;",
        {"node": rid, "vec": vec}
    )
    return True


def embed_seed_data(client):
    """Generate embeddings for all seed data nodes that lack them.

    Called once after seeding to backfill embeddings.
    """
    embedded = 0
    for table in ['experience', 'concept', 'reflection']:
        nodes = client.query(
            f"SELECT id, content, name, description, summary FROM {table} "
            f"WHERE embedding IS NONE;"
        )
        for node in nodes:
            node_id = str(node['id'])
            # Use the most descriptive text available
            text = (node.get('description')
                    or node.get('content')
                    or node.get('summary')
                    or node.get('name')
                    or '')
            if text and embed_and_store(client, node_id, text):
                embedded += 1

    return embedded
