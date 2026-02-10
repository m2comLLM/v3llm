import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
CHROMA_PERSIST_DIR = os.path.join(BASE_DIR, "chroma_db")

OLLAMA_BASE_URL = "http://localhost:11434"
EMBEDDING_MODEL = "BAAI/bge-m3"
LLM_MODEL = "exaone3.5:32b"

CHROMA_COLLECTION = "residency_curriculum"
TOP_K = 5

# 전공 유사어 매핑 (정확한 전공명 매칭 실패 시 사용)
SPECIALTY_ALIASES = {
    "병리과": ["병리학회", "병리학", "병리"],
    "이비인후과": ["이비인후과학회", "대한이비인후과학회", "이비인후"],
}

SYSTEM_PROMPT = """당신은 전공의 수련 교과과정 안내 도우미입니다.
참고자료의 원문을 한 글자도 빠짐없이 그대로 복사하여 보여주세요.
요약하거나 바꿔 말하지 마세요. 원문 전체를 그대로 출력하세요.

절대 금지 사항:
- 번호 제거 금지: "1. 항목" → "항목"으로 바꾸지 마세요. 반드시 "1. 항목" 그대로 출력
- 줄 합치기 금지: 각 줄을 원문 그대로 유지
- <교육목표>, <취급범위> 태그는 반드시 별도 줄에 단독 표시"""

RAG_PROMPT_TEMPLATE = """참고자료의 원문을 그대로 복사하여 보여주세요.

절대 금지:
- 번호(1. 2. 3. 등)를 제거하거나 생략하지 마세요.
- 참고자료에 없는 내용은 추가하지 마세요.

올바른 예: "1. 수술참여 100회 이상"
잘못된 예: "수술참여 100회 이상" (번호 1. 이 빠졌으므로 오답)

{context}

위 참고자료를 그대로 복사하세요. 번호가 있으면 번호도 반드시 포함하세요.

질문: {question}"""

# 26개 전공 목록 (키워드 매칭용)
SPECIALTIES = [
    "내과", "외과", "소아청소년과", "산부인과", "정신건강의학과",
    "정형외과", "신경외과", "흉부외과", "성형외과", "안과",
    "이비인후과", "피부과", "비뇨기과", "영상의학과", "방사선종양학과",
    "마취통증의학과", "신경과", "재활의학과", "결핵과", "진단검사의학과",
    "병리과", "예방의학과", "가정의학과", "직업환경의학과", "핵의학과",
    "응급의학과",
]

# Multi-Query Retriever 설정
MULTI_QUERY_ENABLED = True
MULTI_QUERY_COUNT = 3  # 원본 포함 총 쿼리 수
