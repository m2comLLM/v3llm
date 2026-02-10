import re

from .config import SPECIALTIES, SPECIALTY_ALIASES, TOP_K
from .indexer import get_collection

# 첨부 문서 참조를 암시하는 키워드
_ATTACHMENT_HINTS = ("점수", "기준", "별지", "별첨", "첨부", "연수교육", "학술대회 목록")


def extract_query_filters(question: str) -> dict | None:
    """질문에서 전공명/연차를 감지하여 ChromaDB where 필터 생성"""
    filters = []
    needs_attachment = any(kw in question for kw in _ATTACHMENT_HINTS)

    # 전공명 감지 (긴 이름부터 매칭하여 '외과' < '성형외과' 문제 방지)
    for spec in sorted(SPECIALTIES, key=len, reverse=True):
        if spec in question:
            filters.append({"specialty": spec})
            break

    # 유사어 매칭 (정확한 전공명 매칭 실패 시)
    if not any("specialty" in f for f in filters):
        for spec, aliases in SPECIALTY_ALIASES.items():
            for alias in sorted(aliases, key=len, reverse=True):
                if alias in question:
                    filters.append({"specialty": spec})
                    break
            if any("specialty" in f for f in filters):
                break

    # 첨부 문서가 필요한 경우: 구분/연차 필터 없이 전공 필터만 적용
    if needs_attachment:
        if not filters:
            return {"doc_type": "첨부"}
        return {"$and": filters + [{"doc_type": "첨부"}]}

    # 연차 감지
    m = re.search(r"(\d)\s*[년연]\s*차", question)
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


def _query(col, question: str, top_k: int, where_filter: dict | None) -> list[dict]:
    """공통 ChromaDB 쿼리 로직"""
    query_params = {
        "query_texts": [question],
        "n_results": top_k,
    }
    if where_filter:
        query_params["where"] = where_filter

    try:
        results = col.query(**query_params)
    except Exception:
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


def _is_attachment_filter(where_filter: dict) -> bool:
    """이미 첨부 필터가 적용된 쿼리인지 확인"""
    if where_filter.get("doc_type") == "첨부":
        return True
    for cond in where_filter.get("$and", []):
        if cond.get("doc_type") == "첨부":
            return True
    return False


def _extract_specialty_filter(where_filter: dict) -> dict | None:
    """where 필터에서 전공 조건만 추출"""
    if "specialty" in where_filter:
        return {"specialty": where_filter["specialty"]}
    for cond in where_filter.get("$and", []):
        if "specialty" in cond:
            return cond
    return None


def retrieve(question: str, top_k: int = TOP_K) -> list[dict]:
    col = get_collection()
    where_filter = extract_query_filters(question)

    # 1차 검색
    items = _query(col, question, top_k, where_filter)

    # 2단계: 1차 결과에 첨부 문서가 없고, 첨부 필터가 아닌 경우 첨부 보완 검색
    has_attachment = any(r["metadata"].get("doc_type") == "첨부" for r in items)
    if not has_attachment and where_filter and not _is_attachment_filter(where_filter):
        spec_filter = _extract_specialty_filter(where_filter)
        if spec_filter:
            att_filter = {"$and": [spec_filter, {"doc_type": "첨부"}]}
        else:
            att_filter = {"doc_type": "첨부"}
        att_items = _query(col, question, 2, att_filter)
        for item in att_items:
            if item["distance"] < 1.5:
                items.append(item)

    # 특정 연차 질문 시 총계/비고 제외
    has_year = where_filter and any(
        f.get("year") in ("1", "2", "3", "4")
        for f in (where_filter.get("$and", []) if "$and" in (where_filter or {}) else [where_filter or {}])
    )
    if has_year:
        items = [r for r in items if r["metadata"].get("year") not in ("총계", "비고")]

    # 연차순 정렬 (1→2→3→4→총계→비고)
    YEAR_ORDER = {"1": 0, "2": 1, "3": 2, "4": 3, "총계": 4, "비고": 5}
    items.sort(key=lambda x: YEAR_ORDER.get(x["metadata"].get("year", ""), 99))

    return items


def format_context(results: list[dict]) -> str:
    parts = []
    for i, r in enumerate(results, 1):
        parts.append(f"--- 참고자료 {i} ---\n{r['text']}")
    return "\n\n".join(parts)
