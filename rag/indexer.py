import os

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from .bm25_index import rebuild_bm25_index
from .config import CHROMA_COLLECTION, CHROMA_PERSIST_DIR, EMBEDDING_MODEL


def _get_embedding_fn():
    return SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL,
        device="cuda",
    )


def _get_client():
    return chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)


def get_collection():
    client = _get_client()
    return client.get_or_create_collection(
        name=CHROMA_COLLECTION,
        embedding_function=_get_embedding_fn(),
        metadata={"hnsw:space": "cosine"},
    )


def is_index_built() -> bool:
    if not os.path.isdir(CHROMA_PERSIST_DIR):
        return False
    try:
        col = get_collection()
        return col.count() > 0
    except Exception:
        return False


def index_chunks(chunks: list[dict]) -> int:
    col = get_collection()
    batch_size = 50
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        col.upsert(
            ids=[c["id"] for c in batch],
            documents=[c["text"] for c in batch],
            metadatas=[c["metadata"] for c in batch],
        )
    rebuild_bm25_index(chunks)
    return col.count()


def rebuild_index(chunks: list[dict]) -> int:
    client = _get_client()
    try:
        client.delete_collection(CHROMA_COLLECTION)
    except Exception:
        pass
    count = index_chunks(chunks)
    return count
