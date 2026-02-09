"""
전공의 수련교과과정 데이터를 ChromaDB에 인덱싱합니다.

Usage:
    python index_data.py             # 인덱스 빌드 (이미 있으면 upsert)
    python index_data.py --rebuild   # 기존 인덱스 삭제 후 재빌드
"""

import sys
from collections import Counter

from rag.chunker import generate_all_chunks
from rag.indexer import index_chunks, rebuild_index


def main():
    rebuild = "--rebuild" in sys.argv

    print("청크 생성 중...")
    chunks = generate_all_chunks()
    print(f"총 {len(chunks)}개 청크 생성")

    # 통계
    by_type = Counter(c["metadata"]["doc_type"] for c in chunks)
    by_level = Counter(c["metadata"]["chunk_level"] for c in chunks)
    print(f"  doc_type: {dict(by_type)}")
    print(f"  chunk_level: {dict(by_level)}")

    print(f"\n{'인덱스 재빌드' if rebuild else '인덱스 빌드'} 중...")
    if rebuild:
        count = rebuild_index(chunks)
    else:
        count = index_chunks(chunks)

    print(f"완료! ChromaDB에 {count}개 문서 저장됨")


if __name__ == "__main__":
    main()
