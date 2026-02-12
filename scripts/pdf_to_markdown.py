"""PDF 법령 문서를 조문별 마크다운 파일로 변환하는 스크립트.

PDF에서 텍스트를 추출하고, 본문(조문)과 부칙을 분리하여
각각 개별 .md 파일로 저장합니다.

사용법:
    python scripts/pdf_to_markdown.py <input.pdf> <output_dir>

예시:
    python scripts/pdf_to_markdown.py \
        data/전문의의수련및자격인정등에관한규정.pdf \
        output/전문의수련규정

결과 구조:
    output/전문의수련규정/
    ├── 본문/
    │   ├── 제1조_목적.md
    │   ├── 제2조_정의.md
    │   └── ...
    └── 부칙/
        ├── 부칙_제21108호.md
        └── ...
"""

import re
import sys
from pathlib import Path

import pdfplumber


# ──────────────────────────────────────────────
# 1. PDF 텍스트 추출
# ──────────────────────────────────────────────

def extract_text_from_pdf(pdf_path: str) -> str:
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n".join(pages)


# ──────────────────────────────────────────────
# 2. 텍스트 정리
# ──────────────────────────────────────────────

def clean_law_text(raw: str, doc_title: str) -> str:
    """PDF 페이지 헤더/푸터 등 노이즈 제거"""
    lines = raw.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append("")
            continue
        if re.match(r"^법제처\s+\d+\s+국가법령정보센터$", stripped):
            continue
        if stripped == doc_title:
            continue
        cleaned.append(stripped)
    return "\n".join(cleaned)


def normalize_body(body: str) -> str:
    """PDF 추출 시 깨진 줄바꿈을 정리"""
    lines = body.splitlines()
    result = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if result and result[-1] != "":
                result.append("")
            continue
        # 항 번호(①②③...), 호 번호(1. 2. 3...), 조문 시작은 새 줄
        if re.match(r"^[①②③④⑤⑥⑦⑧⑨]", stripped):
            result.append(stripped)
        elif re.match(r"^\d+\.\s", stripped):
            result.append(stripped)
        elif re.match(r"^제\d+조", stripped):
            result.append(stripped)
        elif result and result[-1] and not result[-1].endswith((".", "다.", "한다.")):
            result[-1] = result[-1] + " " + stripped
        else:
            result.append(stripped)
    return "\n".join(result)


# ──────────────────────────────────────────────
# 3. 조문/부칙 파싱 → 개별 파일 생성
# ──────────────────────────────────────────────

def parse_and_split(text: str, output_dir: Path) -> list[Path]:
    """정리된 텍스트를 파싱하여 본문/부칙 폴더에 개별 파일로 저장.
    생성된 파일 경로 목록을 반환."""
    body_dir = output_dir / "본문"
    addendum_dir = output_dir / "부칙"
    body_dir.mkdir(parents=True, exist_ok=True)
    addendum_dir.mkdir(parents=True, exist_ok=True)

    full_text = text

    # 조문 패턴: 제N조(제목) 본문...
    article_pattern = re.compile(
        r"(제\d+조\([^)]+\))\s*(.*?)(?=(?:제\d+조\(|부칙\s*<|$))",
        re.DOTALL,
    )
    # 부칙 패턴: 부칙 <제NNNNN호, YYYY. MM. DD.>
    addendum_pattern = re.compile(
        r"(부칙\s*<[^>]+>(?:\([^)]*\))?)\s*(.*?)(?=(?:부칙\s*<|$))",
        re.DOTALL,
    )

    created = []

    # 본문 조문 처리
    for m in article_pattern.finditer(full_text):
        title = m.group(1).strip()
        body = normalize_body(m.group(2).strip())
        if not body:
            continue

        # 파일명: 제1조_목적.md
        m_num = re.match(r"(제\d+조)\(([^)]+)\)", title)
        if not m_num:
            continue
        num, name = m_num.group(1), m_num.group(2)
        filename = f"{num}_{name.replace(' ', '_')}.md"

        out_path = body_dir / filename
        out_path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
        created.append(out_path)

    # 부칙 처리
    for m in addendum_pattern.finditer(full_text):
        title = m.group(1).strip()
        body = normalize_body(m.group(2).strip())
        if not body:
            continue

        # 파일명: 부칙_제21108호.md
        m_decree = re.search(r"제(\d+)호", title)
        decree_num = f"제{m_decree.group(1)}호" if m_decree else "unknown"
        filename = f"부칙_{decree_num}.md"

        out_path = addendum_dir / filename
        out_path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
        created.append(out_path)

    return created


# ──────────────────────────────────────────────
# 4. 메인
# ──────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print(f"사용법: python {sys.argv[0]} <input.pdf> <output_dir>")
        print(f"예시:   python {sys.argv[0]} data/규정.pdf output/전문의수련규정")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_dir = Path(sys.argv[2])

    if not Path(pdf_path).exists():
        print(f"오류: PDF 파일을 찾을 수 없습니다: {pdf_path}")
        sys.exit(1)

    # 문서 제목 (페이지 헤더 제거용) - 필요 시 인자로 받을 수 있음
    doc_title = "전문의의 수련 및 자격 인정 등에 관한 규정"

    print(f"PDF 읽는 중: {pdf_path}")
    raw_text = extract_text_from_pdf(pdf_path)

    print("텍스트 정리 중...")
    cleaned = clean_law_text(raw_text, doc_title)

    print(f"조문 분리 및 파일 생성 중: {output_dir}/")
    created = parse_and_split(cleaned, output_dir)

    print(f"\n완료! 총 {len(created)}개 파일 생성:")
    for p in created:
        rel = p.relative_to(output_dir)
        size = p.stat().st_size
        print(f"  {rel}  ({size:,} bytes)")


if __name__ == "__main__":
    main()
