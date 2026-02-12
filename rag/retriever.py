import re
from concurrent.futures import ThreadPoolExecutor

from .bm25_index import get_bm25_index
from .config import (
    BM25_TOP_K_MULTIPLIER,
    BM25_WEIGHT,
    HYBRID_SEARCH_ENABLED,
    MULTI_QUERY_COUNT,
    MULTI_QUERY_ENABLED,
    RRF_K,
    SPECIALTIES,
    SPECIALTY_ALIASES,
    TOP_K,
    VECTOR_WEIGHT,
)
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

    # 전문의수련규정 감지 (일반 문서 감지보다 우선)
    _REGULATION_KEYWORDS = ("수련규정", "전문의수련규정", "전문의의 수련", "자격 인정")
    is_regulation = any(kw in question for kw in _REGULATION_KEYWORDS)
    # "제N조" 패턴이 있고 전공 필터가 없으면 규정 문서로 판단
    if not is_regulation and re.search(r"제\d+조", question) and not any("specialty" in f for f in filters):
        is_regulation = True
    # 전공 없이 "규정"만 언급된 경우
    if not is_regulation and "규정" in question and not any("specialty" in f for f in filters):
        is_regulation = True
    # "부칙 제N호" 패턴 (규정 부칙)
    if not is_regulation and re.search(r"부칙\s*제\d+호", question):
        is_regulation = True
    if is_regulation:
        filters.append({"doc_type": "전문의수련규정"})

    # 일반 문서 감지 (규정 필터가 있으면 건너뜀)
    has_regulation = any(f.get("doc_type") == "전문의수련규정" for f in filters)
    if not has_regulation and "부칙" in question:
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
                    "id": results["ids"][0][i] if results["ids"] else "",
                    "text": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0,
                }
            )
    return items


# Multi-Query: 도메인 특화 유의어 사전
_QUERY_SYNONYMS = {
    "교과내용": ["교육과정", "수련내용"],
    "교육과정": ["교과내용", "수련내용"],
    "수련내용": ["교과내용", "교육과정"],
    "환자취급범위": ["진료범위", "환자진료범위"],
    "환자취급": ["환자진료", "진료범위"],
    "학술회의참석": ["학술대회 참석", "학회 참석"],
    "학술회의": ["학술대회", "학회"],
    "논문제출": ["논문 발표", "학술논문"],
    "타과파견": ["타과 순환", "타과 로테이션"],
    "기타요건": ["추가요건", "기타 조건"],
    "교과과정": ["교육과정", "수련과정", "커리큘럼"],
    "수련": ["교육", "훈련"],
    "목표": ["교육목표", "교육 목표"],
    "년차": ["연차"],
    "연차": ["년차"],
    "수련규정": ["전문의수련규정", "수련 규정"],
    "전문의수련규정": ["수련규정", "전문의 수련규정"],
    "수련병원": ["수련기관", "지정병원"],
    "수련기관": ["수련병원"],
    "전공의": ["레지던트", "수련의"],
}

# Multi-Query: 구조 변환 패턴
_REFORMULATIONS = [
    ("알려줘", "관련 내용"),
    ("알려주세요", "관련 내용"),
    ("어떻게 되나요?", "관련 내용"),
    ("무엇인가요?", "관련 내용"),
    ("뭐야?", "관련 내용"),
    ("뭐야", "관련 내용"),
    ("은?", " 관련 내용"),
    ("는?", " 관련 내용"),
    ("이?", " 관련 내용"),
]


def _generate_query_variations(question: str, n: int = 2) -> list[str]:
    """질문에서 유의어 치환/구조 변환을 통해 n개의 변형 쿼리 생성"""
    variations = []

    # 변형 1: 유의어 치환 (긴 단어 우선 매칭)
    syn_variation = question
    for term in sorted(_QUERY_SYNONYMS, key=len, reverse=True):
        if term in syn_variation:
            syn_variation = syn_variation.replace(term, _QUERY_SYNONYMS[term][0], 1)
            break
    if syn_variation != question:
        variations.append(syn_variation)

    # 변형 2: 구조 변환 (질문형→서술형)
    reformulated = question
    for pattern, replacement in _REFORMULATIONS:
        if pattern in reformulated:
            reformulated = reformulated.replace(pattern, replacement).strip()
            break
    if reformulated != question and reformulated not in variations:
        variations.append(reformulated)

    # 부족하면 두 번째 유의어로 추가 변형
    if len(variations) < n:
        syn2 = question
        found_first = False
        for term in sorted(_QUERY_SYNONYMS, key=len, reverse=True):
            if term in syn2:
                if not found_first:
                    found_first = True
                    continue
                syn2 = syn2.replace(term, _QUERY_SYNONYMS[term][0], 1)
                break
        if syn2 != question and syn2 not in variations:
            variations.append(syn2)

    return variations[:n]


def _multi_query(
    col, question: str, top_k: int, where_filter: dict | None
) -> list[dict]:
    """Multi-query retrieval: 여러 쿼리 변형으로 검색 후 결과 병합"""
    if not MULTI_QUERY_ENABLED:
        return _query(col, question, top_k, where_filter)

    variations = _generate_query_variations(question, n=MULTI_QUERY_COUNT - 1)
    all_queries = [question] + variations

    def run_query(q):
        return _query(col, q, top_k, where_filter)

    with ThreadPoolExecutor(max_workers=len(all_queries)) as executor:
        all_results = list(executor.map(run_query, all_queries))

    # document ID 기준 중복 제거 (최소 distance 유지)
    best: dict[str, dict] = {}
    for result_set in all_results:
        for item in result_set:
            doc_id = item["id"]
            if doc_id not in best or item["distance"] < best[doc_id]["distance"]:
                best[doc_id] = item

    deduped = sorted(best.values(), key=lambda x: x["distance"])
    return deduped[:top_k]


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


def _reciprocal_rank_fusion(
    vector_results: list[dict],
    bm25_results: list[dict],
    top_k: int,
) -> list[dict]:
    """Reciprocal Rank Fusion: 벡터 검색과 BM25 검색 결과를 순위 기반으로 융합"""
    rrf_scores: dict[str, float] = {}
    doc_map: dict[str, dict] = {}

    for rank, item in enumerate(vector_results, start=1):
        doc_id = item["id"]
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + VECTOR_WEIGHT / (RRF_K + rank)
        if doc_id not in doc_map:
            doc_map[doc_id] = item

    for rank, item in enumerate(bm25_results, start=1):
        doc_id = item["id"]
        rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + BM25_WEIGHT / (RRF_K + rank)
        if doc_id not in doc_map:
            doc_map[doc_id] = item

    sorted_ids = sorted(rrf_scores, key=rrf_scores.get, reverse=True)

    fused = []
    for doc_id in sorted_ids[:top_k]:
        item = doc_map[doc_id].copy()
        item.pop("bm25_score", None)
        item.pop("distance", None)
        fused.append(item)

    return fused


def retrieve(question: str, top_k: int = TOP_K) -> list[dict]:
    col = get_collection()
    where_filter = extract_query_filters(question)

    fetch_k = top_k * BM25_TOP_K_MULTIPLIER

    # 1a: Multi-query 벡터 검색
    vector_items = _multi_query(col, question, fetch_k, where_filter)

    # 1b: BM25 키워드 검색 + RRF 융합
    if HYBRID_SEARCH_ENABLED:
        bm25_idx = get_bm25_index()
        bm25_items = bm25_idx.query(question, fetch_k, where_filter)
        items = _reciprocal_rank_fusion(vector_items, bm25_items, top_k)
    else:
        items = vector_items[:top_k]

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

    # 연차순 정렬 (규정 문서는 연차 정렬 불필요)
    has_regulation_results = any(
        r["metadata"].get("doc_type") == "전문의수련규정" for r in items
    )
    if not has_regulation_results:
        YEAR_ORDER = {"1": 0, "2": 1, "3": 2, "4": 3, "총계": 4, "비고": 5}
        items.sort(key=lambda x: YEAR_ORDER.get(x["metadata"].get("year", ""), 99))

    return items


def format_context(results: list[dict]) -> str:
    parts = []
    for r in results:
        parts.append(r["text"])
    return "\n\n".join(parts)
