import os
import re

import pandas as pd

from .config import OUTPUT_DIR


def normalize_category(raw: str) -> str:
    return raw.replace(" ", "").strip()


def parse_md_table(text: str) -> pd.DataFrame | None:
    lines = [l for l in text.strip().splitlines() if l.startswith("|")]
    if len(lines) < 3:
        return None
    header = [c.strip() for c in lines[0].split("|")[1:-1]]
    rows = []
    for line in lines[2:]:
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) == len(header):
            rows.append(cells)
    return pd.DataFrame(rows, columns=header)


def _ffill_md_table(body: str) -> str:
    """마크다운 테이블의 빈 셀을 forward fill하여 반환 (테이블 없으면 원본 반환)"""
    df = parse_md_table(body)
    if df is None:
        return body
    if not (df == "").any().any():
        return body
    df = df.replace("", pd.NA).ffill().fillna("")
    header = "| " + " | ".join(df.columns) + " |"
    sep = "| " + " | ".join("---" for _ in df.columns) + " |"
    rows = []
    for _, row in df.iterrows():
        rows.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join([header, sep] + rows)


def _read_md(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def _extract_specialty_info(folder_name: str) -> tuple[str, int]:
    """'1.내과' -> ('내과', 1)"""
    m = re.match(r"(\d+)\.(.+)", folder_name)
    if m:
        return m.group(2), int(m.group(1))
    return folder_name, 0


def chunk_general_document(file_path: str, doc_type: str) -> list[dict]:
    text = _read_md(file_path)
    body = re.sub(r"^#.*\n+", "", text).strip()
    if not body:
        return []
    return [
        {
            "id": doc_type,
            "text": f"[{doc_type}]\n{body}",
            "metadata": {
                "doc_type": doc_type,
                "specialty": "",
                "specialty_id": 0,
                "year": "",
                "category": "",
                "chunk_level": "document",
                "source_file": os.path.relpath(file_path, OUTPUT_DIR),
            },
        }
    ]


def chunk_education_goal(
    file_path: str, specialty: str, specialty_id: int
) -> list[dict]:
    text = _read_md(file_path)
    body = re.sub(r"^#.*\n+", "", text).strip()
    if not body:
        return []
    return [
        {
            "id": f"{specialty}_교육목표",
            "text": f"[{specialty}] 교육목표:\n{body}",
            "metadata": {
                "doc_type": "교육목표",
                "specialty": specialty,
                "specialty_id": specialty_id,
                "year": "",
                "category": "",
                "chunk_level": "document",
                "source_file": os.path.relpath(file_path, OUTPUT_DIR),
            },
        }
    ]


def chunk_curriculum_table(
    file_path: str, specialty: str, specialty_id: int
) -> list[dict]:
    text = _read_md(file_path)
    df = parse_md_table(text)
    if df is None or df.empty:
        return []

    col_year, col_cat, col_content = df.columns[0], df.columns[1], df.columns[2]

    # forward fill: 연차는 항상, 구분은 같은 연차 그룹 내에서만
    df[col_year] = df[col_year].replace("", pd.NA).ffill().fillna("")
    df[col_cat] = df[col_cat].replace("", pd.NA)
    df[col_cat] = df.groupby(col_year)[col_cat].ffill().fillna("")

    chunks = []

    # (연차, 구분) 단위 청크
    for (year, cat_raw), group in df.groupby([col_year, col_cat], sort=False):
        cat = normalize_category(cat_raw)
        lines = [line for line in group[col_content].tolist() if line.strip()]
        content_parts = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            is_section_tag = stripped.startswith("<") and stripped.endswith(">")
            # 섹션 태그 앞에 빈 줄 추가 (첫 줄 제외)
            if is_section_tag and content_parts:
                content_parts.append("")
            content_parts.append(line)
            # 섹션 태그 뒤에도 빈 줄 추가 (마지막 줄 제외)
            if is_section_tag and i < len(lines) - 1:
                content_parts.append("")
        content = "\n".join(content_parts)
        if not content.strip():
            continue

        # "동일" 참조 해결은 나중에 한꺼번에 처리
        chunk_id = f"{specialty}_{year}_{cat}"
        if year in ("총계", "비고"):
            header = f"[{specialty}] {year} - {cat}:" if cat else f"[{specialty}] {year}:"
        else:
            header = f"[{specialty}] {year}년차 - {cat}:"
        chunks.append(
            {
                "id": chunk_id,
                "text": f"{header}\n{content}",
                "metadata": {
                    "doc_type": "연차별_교과과정",
                    "specialty": specialty,
                    "specialty_id": specialty_id,
                    "year": str(year),
                    "category": cat,
                    "chunk_level": "year_category",
                    "source_file": os.path.relpath(file_path, OUTPUT_DIR),
                },
            }
        )

    # 참조 해결: "2년차와 동일", "총계 참조" 등의 참조를 원본 내용으로 대체
    chunk_map = {c["id"]: c for c in chunks}
    for chunk in chunks:
        body = chunk["text"].split("\n", 1)[-1].strip()
        if len(body) > 30:
            continue
        header = chunk["text"].split("\n", 1)[0]

        # "N년차와 동일/공통" 참조
        m = re.search(r"(\d)년차와\s*(?:동일|공통)", body)
        if m:
            ref_id = f"{specialty}_{m.group(1)}_{chunk['metadata']['category']}"
            if ref_id in chunk_map:
                ref_text = chunk_map[ref_id]["text"].split("\n", 1)[-1]
                chunk["text"] = f"{header}\n{ref_text}"
            continue

        # "총계 참조" / "총계 항목 참조" 등
        if re.search(r"총계.*참조", body):
            ref_id = f"{specialty}_총계_{chunk['metadata']['category']}"
            if ref_id in chunk_map:
                ref_text = chunk_map[ref_id]["text"].split("\n", 1)[-1]
                chunk["text"] = f"{header}\n{ref_text}"

    # 연차별 요약 청크 (비고는 구분 없이 단일 청크이므로 요약 생략)
    for year, group in df.groupby(col_year, sort=False):
        if year == "비고":
            continue
        lines = []
        for _, row in group.iterrows():
            cat = normalize_category(str(row[col_cat]))
            content = str(row[col_content]).strip()
            if content:
                lines.append(f"[{cat}] {content}" if cat else content)
        if not lines:
            continue
        header = f"[{specialty}] {year}년차 전체:" if year not in ("총계",) else f"[{specialty}] {year} 전체:"
        chunks.append(
            {
                "id": f"{specialty}_{year}_전체",
                "text": f"{header}\n" + "\n".join(lines),
                "metadata": {
                    "doc_type": "연차별_교과과정",
                    "specialty": specialty,
                    "specialty_id": specialty_id,
                    "year": str(year),
                    "category": "전체",
                    "chunk_level": "year",
                    "source_file": os.path.relpath(file_path, OUTPUT_DIR),
                },
            }
        )

    return chunks


def generate_all_chunks() -> list[dict]:
    chunks = []

    # 부칙/총칙/인턴수련
    general_docs = {
        "부칙": os.path.join(OUTPUT_DIR, "부칙", "부칙.md"),
        "총칙": os.path.join(OUTPUT_DIR, "제1장_총칙", "총칙.md"),
        "인턴수련": os.path.join(
            OUTPUT_DIR, "제2장_인턴수련_교과과정", "인턴수련_교과과정.md"
        ),
    }
    for doc_type, path in general_docs.items():
        if os.path.exists(path):
            chunks.extend(chunk_general_document(path, doc_type))

    # 제3장 전공별
    ch3_dir = os.path.join(OUTPUT_DIR, "제3장_레지던트_연차별_수련_교과과정")
    if not os.path.isdir(ch3_dir):
        return chunks

    for folder in sorted(os.listdir(ch3_dir)):
        main_dir = os.path.join(ch3_dir, folder, "main")
        if not os.path.isdir(main_dir):
            continue

        specialty, spec_id = _extract_specialty_info(folder)

        # 교육목표
        goal_path = os.path.join(main_dir, "교육목표.md")
        if os.path.exists(goal_path):
            chunks.extend(chunk_education_goal(goal_path, specialty, spec_id))

        # 연차별 교과과정
        table_path = os.path.join(main_dir, "연차별_교과과정.md")
        if os.path.exists(table_path):
            chunks.extend(chunk_curriculum_table(table_path, specialty, spec_id))

        # 첨부 파일 (attachment/ 또는 attachments/ 폴더)
        spec_dir = os.path.join(ch3_dir, folder)
        for sub in os.listdir(spec_dir):
            sub_path = os.path.join(spec_dir, sub)
            if os.path.isdir(sub_path) and sub.startswith("attachment"):
                for fname in sorted(os.listdir(sub_path)):
                    if fname.endswith(".md"):
                        fpath = os.path.join(sub_path, fname)
                        text = _read_md(fpath)
                        body = re.sub(r"^#.*\n+", "", text).strip()
                        if "지부 집담회" in fname:
                            body = _ffill_md_table(body)
                        if body:
                            chunks.append(
                                {
                                    "id": f"{specialty}_첨부_{fname}",
                                    "text": f"[{specialty}] 별지(첨부자료) - {fname.replace('.md', '')}:\n{body}",
                                    "metadata": {
                                        "doc_type": "첨부",
                                        "specialty": specialty,
                                        "specialty_id": spec_id,
                                        "year": "",
                                        "category": "",
                                        "chunk_level": "document",
                                        "source_file": os.path.relpath(fpath, OUTPUT_DIR),
                                    },
                                }
                            )

    return chunks
