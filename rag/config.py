import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
CHROMA_PERSIST_DIR = os.path.join(BASE_DIR, "chroma_db")

OLLAMA_BASE_URL = "http://localhost:11434"
EMBEDDING_MODEL = "nomic-embed-text"
LLM_MODEL = "qwen2.5:7b"

CHROMA_COLLECTION = "residency_curriculum"
TOP_K = 5

SYSTEM_PROMPT = """당신은 전공의 수련 교과과정 전문 도우미입니다.
제공된 교과과정 자료를 바탕으로 정확하게 답변해주세요.
자료에 없는 내용은 추측하지 말고, 자료에 근거하여 답변해주세요.
답변은 한국어로 해주세요."""

RAG_PROMPT_TEMPLATE = """다음은 전공의 수련 교과과정에서 관련된 내용입니다:

{context}

위 자료를 바탕으로 다음 질문에 답변해주세요:
{question}"""

# 26개 전공 목록 (키워드 매칭용)
SPECIALTIES = [
    "내과", "외과", "소아청소년과", "산부인과", "정신건강의학과",
    "정형외과", "신경외과", "흉부외과", "성형외과", "안과",
    "이비인후과", "피부과", "비뇨기과", "영상의학과", "방사선종양학과",
    "마취통증의학과", "신경과", "재활의학과", "결핵과", "진단검사의학과",
    "병리과", "예방의학과", "가정의학과", "직업환경의학과", "핵의학과",
    "응급의학과",
]
