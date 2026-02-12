import os

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from .bm25_index import rebuild_bm25_index
from .config import CHROMA_COLLECTION, CHROMA_PERSIST_DIR, EMBEDDING_MODEL

# ── 모듈 레벨 캐싱 (임베딩 모델·클라이언트·컬렉션을 한 번만 로드) ──
_embedding_fn = None
_client = None
_collection = None


def _get_embedding_fn():
    global _embedding_fn
    if _embedding_fn is None:
        _embedding_fn = SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL,
            device="cpu",
        )
    return _embedding_fn


def _get_client():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    return _client


def get_collection():
    global _collection
    if _collection is None:
        client = _get_client()
        _collection = client.get_or_create_collection(
            name=CHROMA_COLLECTION,
            embedding_function=_get_embedding_fn(),
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


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
    global _collection
    client = _get_client()
    try:
        client.delete_collection(CHROMA_COLLECTION)
    except Exception:
        pass
    _collection = None  # 캐시 무효화 (삭제 후 재생성 필요)
    count = index_chunks(chunks)
    return count
