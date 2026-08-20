"""
RAG tools — stubbed out for cloud deployment.

ChromaDB and sentence-transformers are not available on free hosting tiers.
All agent nodes call these functions inside try/except blocks, so returning
empty results is safe — the pipeline continues normally without RAG context.
"""
from typing import List


def index_documents(texts: List[str], ids: List[str], collection_name: str) -> None:
    """No-op: RAG indexing disabled in cloud deployment."""
    pass


def query_collection(query: str, collection_name: str, n_results: int = 5) -> List[str]:
    """No-op: returns empty list — nodes fall back to LLM-only reasoning."""
    return []