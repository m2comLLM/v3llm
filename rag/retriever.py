import re

from .config import SPECIALTIES, TOP_K
from .indexer import get_collection


def extract_query_filters(question: str) -> dict | None:
    """질문에서 전공명/연차를 감지하여 ChromaDB where 필터 생성"""
    filters = []

    # 전공명 감지
    for spec in SPECIALTIES:
        if spec in question:
            filters.append({"specialty": spec})
            break

    # 연차 감지
    m = re.search(r"(\d)\s*년\s*차", question)
    if m:
        filters.append({"year": m.group(1)})

    # 총계/비고
    if "총계" in question:
        filters.append({"year": "총계"})
    if "비고" in question:
        filters.append({"year": "비고"})

    # 구분 감지
    cat_keywords = {
        "환자취급": "환자취급범위",
        "교과내용": "교과내용",
        "교과 내용": "교과내용",
        "학술회의": "학술회의참석",
        "논문": "논문제출",
        "타과파견": "타과파견",
        "타과 파견": "타과파견",
        "기타": "기타요건",
    }
    for keyword, cat in cat_keywords.items():
        if keyword in question:
            filters.append({"category": cat})
            break

    # 일반 문서 감지
    if "부칙" in question:
        filters.append({"doc_type": "부칙"})
    elif "총칙" in question:
        filters.append({"doc_type": "총칙"})
    elif "인턴" in question:
        filters.append({"doc_type": "인턴수련"})
    elif "교육목표" in question:
        filters.append({"doc_type": "교육목표"})

    if not filters:
        return None
    if len(filters) == 1:
        return filters[0]
    return {"$and": filters}


def retrieve(question: str, top_k: int = TOP_K) -> list[dict]:
    col = get_collection()
    where_filter = extract_query_filters(question)

    query_params = {
        "query_texts": [question],
        "n_results": top_k,
    }
    if where_filter:
        query_params["where"] = where_filter

    try:
        results = col.query(**query_params)
    except Exception:
        # 필터가 결과 없으면 필터 없이 재시도
        results = col.query(query_texts=[question], n_results=top_k)

    items = []
    if results and results["documents"]:
        for i, doc in enumerate(results["documents"][0]):
            items.append(
                {
                    "text": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0,
                }
            )
    return items


def format_context(results: list[dict]) -> str:
    parts = []
    for i, r in enumerate(results, 1):
        parts.append(f"--- 참고자료 {i} ---\n{r['text']}")
    return "\n\n".join(parts)
