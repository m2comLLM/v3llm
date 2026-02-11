import os
import pickle
import re

from rank_bm25 import BM25Okapi

from .config import BM25_PERSIST_PATH


def _tokenize(text: str) -> list[str]:
    """한국어 + 영숫자 토큰화 (공백/구두점 기준 분리)"""
    return re.findall(r"\w+", text.lower())


def _match_filter(metadata: dict, where_filter: dict) -> bool:
    """ChromaDB where 필터 형식으로 메타데이터 매칭 확인.

    지원 형식:
      - 단일 필드: {"field": "value"}
      - 복합 $and: {"$and": [{"field1": "val1"}, {"field2": "val2"}]}
    """
    if "$and" in where_filter:
        return all(_match_filter(metadata, cond) for cond in where_filter["$and"])

    for key, value in where_filter.items():
        if key.startswith("$"):
            continue
        if metadata.get(key) != value:
            return False
    return True


class BM25Index:
    """BM25 키워드 검색 인덱스 (pickle 기반 영속화)"""

    def __init__(self, persist_path: str):
        self.persist_path = persist_path
        self.bm25: BM25Okapi | None = None
        self.doc_ids: list[str] = []
        self.doc_texts: list[str] = []
        self.doc_metadatas: list[dict] = []
        self.tokenized_corpus: list[list[str]] = []

    def build(self, chunks: list[dict]) -> None:
        self.doc_ids = [c["id"] for c in chunks]
        self.doc_texts = [c["text"] for c in chunks]
        self.doc_metadatas = [c["metadata"] for c in chunks]
        self.tokenized_corpus = [_tokenize(c["text"]) for c in chunks]
        self.bm25 = BM25Okapi(self.tokenized_corpus)

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.persist_path) or ".", exist_ok=True)
        data = {
            "doc_ids": self.doc_ids,
            "doc_texts": self.doc_texts,
            "doc_metadatas": self.doc_metadatas,
            "tokenized_corpus": self.tokenized_corpus,
        }
        with open(self.persist_path, "wb") as f:
            pickle.dump(data, f)

    def load(self) -> bool:
        if not os.path.exists(self.persist_path):
            return False
        with open(self.persist_path, "rb") as f:
            data = pickle.load(f)
        self.doc_ids = data["doc_ids"]
        self.doc_texts = data["doc_texts"]
        self.doc_metadatas = data["doc_metadatas"]
        self.tokenized_corpus = data["tokenized_corpus"]
        self.bm25 = BM25Okapi(self.tokenized_corpus)
        return True

    def is_built(self) -> bool:
        return os.path.exists(self.persist_path)

    def query(
        self, question: str, top_k: int, where_filter: dict | None = None
    ) -> list[dict]:
        if self.bm25 is None:
            return []

        tokenized_query = _tokenize(question)
        if not tokenized_query:
            return []

        scores = self.bm25.get_scores(tokenized_query)

        candidates = []
        for idx, score in enumerate(scores):
            if score <= 0:
                continue
            if where_filter and not _match_filter(
                self.doc_metadatas[idx], where_filter
            ):
                continue
            candidates.append((idx, score))

        candidates.sort(key=lambda x: x[1], reverse=True)

        return [
            {
                "id": self.doc_ids[idx],
                "text": self.doc_texts[idx],
                "metadata": self.doc_metadatas[idx],
                "bm25_score": float(score),
            }
            for idx, score in candidates[:top_k]
        ]


# ── 모듈 레벨 싱글턴 ──

_bm25_instance: BM25Index | None = None


def get_bm25_index() -> BM25Index:
    global _bm25_instance
    if _bm25_instance is None:
        _bm25_instance = BM25Index(BM25_PERSIST_PATH)
        _bm25_instance.load()
    return _bm25_instance


def rebuild_bm25_index(chunks: list[dict]) -> None:
    global _bm25_instance
    _bm25_instance = BM25Index(BM25_PERSIST_PATH)
    _bm25_instance.build(chunks)
    _bm25_instance.save()
