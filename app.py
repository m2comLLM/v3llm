import glob
import os
import re

import pandas as pd
import pdfplumber


def extract_and_merge_tables(pdf_path):
    merged_tables = []
    previous_table_df = None

    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            # 페이지에서 가장 큰 표 추출 (여러 개면 로직 추가 필요)
            tables = page.extract_tables()

            if not tables:
                previous_table_df = None
                continue

            for table_data in tables:
                current_df = pd.DataFrame(table_data)

                # 첫 번째 행을 헤더로 가정
                if current_df.empty:
                    continue

                # --- 병합 로직 핵심 ---
                # 이전 테이블과 컬럼 수가 같고, 헤더(첫 행)가 동일하면 같은 테이블로 간주
                if (
                    previous_table_df is not None
                    and len(previous_table_df.columns) == len(current_df.columns)
                    and previous_table_df.iloc[0].equals(current_df.iloc[0])
                ):
                    # 반복된 헤더 제거 후 합치기
                    current_df = current_df.iloc[1:]
                    previous_table_df = pd.concat(
                        [previous_table_df, current_df], ignore_index=True
                    )
                    merged_tables[-1] = previous_table_df

                else:
                    # 새로운 표로 인식하고 추가
                    merged_tables.append(current_df)
                    previous_table_df = current_df

    return merged_tables


def process_table(df):
    """테이블 후처리: 헤더 설정, forward fill, 행 병합"""
    # 첫 행을 헤더로 설정
    new_header = df.iloc[0]
    df = df[1:]
    df.columns = new_header

    # 빈값/nan 정리
    df = df.fillna("").replace("nan", "")

    # 연차 컬럼: forward fill
    first_col = df.columns[0]
    df[first_col] = df[first_col].replace("", pd.NA).ffill().fillna("")

    # 연차+구분이 모두 빈 줄만 이전 행의 내용에 합치기
    merged_rows = []
    for _, row in df.iterrows():
        if (
            row[df.columns[0]].strip() == ""
            and row[df.columns[1]].strip() == ""
            and row[df.columns[2]].strip() != ""
        ):
            if merged_rows:
                merged_rows[-1][df.columns[2]] += "\n" + row[df.columns[2]]
        else:
            merged_rows.append(row.to_dict())

    return pd.DataFrame(merged_rows)


def extract_education_goal(pdf_path):
    """PDF 첫 페이지에서 교육목표 텍스트 추출"""
    with pdfplumber.open(pdf_path) as pdf:
        text = pdf.pages[0].extract_text() or ""

    # "교육목표" ~ "연차별 교과과정" 사이 텍스트 추출
    match = re.search(
        r"교육목표\s*[:：]\s*(.*?)(?=\d\)\s*연차별\s*교과과정)", text, re.DOTALL
    )
    if match:
        return match.group(1).strip()
    return None


def process_buchik(pdf_path, output_dir="output"):
    """부칙.pdf에서 부칙, 제1장 총칙, 제2장 인턴수련 교과과정을 분리 저장"""
    with pdfplumber.open(pdf_path) as pdf:
        full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)

    # 부칙: 처음 ~ <별첨> 직전
    buchik_match = re.search(
        r"(「전공의의 연차별 수련교과과정」.*?)(?=<별첨>)", full_text, re.DOTALL
    )
    if buchik_match:
        path = os.path.join(output_dir, "부칙")
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "부칙.md"), "w", encoding="utf-8") as f:
            f.write(f"# 부칙\n\n{buchik_match.group(1).strip()}\n")
        print(f"  -> {path}/부칙.md")

    # 제1장 총칙
    ch1_match = re.search(
        r"(제\s*1\s*장\s*총\s*칙.*?)(?=제\s*2\s*장)", full_text, re.DOTALL
    )
    if ch1_match:
        path = os.path.join(output_dir, "제1장_총칙")
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, "총칙.md"), "w", encoding="utf-8") as f:
            f.write(f"# 제1장 총칙\n\n{ch1_match.group(1).strip()}\n")
        print(f"  -> {path}/총칙.md")

    # 제2장 인턴수련 교과과정
    ch2_match = re.search(
        r"(제\s*2\s*장\s*인턴수련\s*교과과정.*?)(?=제\s*3\s*장)", full_text, re.DOTALL
    )
    if ch2_match:
        path = os.path.join(output_dir, "제2장_인턴수련_교과과정")
        os.makedirs(path, exist_ok=True)
        with open(
            os.path.join(path, "인턴수련_교과과정.md"), "w", encoding="utf-8"
        ) as f:
            f.write(f"# 제2장 인턴수련 교과과정\n\n{ch2_match.group(1).strip()}\n")
        print(f"  -> {path}/인턴수련_교과과정.md")


def convert_pdf_to_markdown(pdf_path, output_dir="output"):
    """PDF 파일 하나를 전공별 폴더에 테이블별 개별 md 파일로 저장"""
    pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
    tables = extract_and_merge_tables(pdf_path)

    if not tables:
        print("  테이블 없음, 건너뜀")
        return

    # 제3장 하위에 전공별 폴더 생성
    folder_path = os.path.join(
        output_dir, "제3장_레지던트_연차별_수련_교과과정", pdf_name, "main"
    )
    os.makedirs(folder_path, exist_ok=True)

    # 교육목표 추출 및 저장
    goal = extract_education_goal(pdf_path)
    if goal:
        goal_path = os.path.join(folder_path, "교육목표.md")
        with open(goal_path, "w", encoding="utf-8") as f:
            f.write(f"# {pdf_name} - 교육목표\n\n{goal}\n")

    for idx, df in enumerate(tables):
        df = process_table(df)
        md = df.to_markdown(index=False)
        file_name = "연차별_교과과정.md" if idx == 0 else f"table_{idx + 1}.md"
        file_path = os.path.join(folder_path, file_name)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"# {pdf_name} - {file_name.replace('.md', '')}\n\n{md}\n")

    goal_msg = " + 교육목표" if goal else ""
    print(f"  -> {folder_path}/ (테이블 {len(tables)}개{goal_msg})")


# 실행
pdf_files = sorted(glob.glob("./split/*.pdf"))

if not pdf_files:
    print("PDF 파일이 없습니다.")
else:
    print(f"PDF {len(pdf_files)}개 발견\n")
    for pdf_path in pdf_files:
        pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
        print(f"[처리중] {pdf_path}")
        if pdf_name == "0.부칙":
            process_buchik(pdf_path)
        else:
            convert_pdf_to_markdown(pdf_path)
    print(f"\n완료! output/ 폴더를 확인하세요.")
