import os
import re

import pandas as pd
import streamlit as st

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

# 구분별 색상 매핑
CATEGORY_COLORS = {
    "환자취급범위": "#e3f2fd",  # 파랑
    "교과내용": "#e8f5e9",  # 초록
    "학술회의참석": "#fffde7",  # 노랑
    "논문제출": "#fff3e0",  # 주황
    "타과파견": "#f3e5f5",  # 보라
    "기타요건": "#f5f5f5",  # 회색
}


def normalize_category(raw: str) -> str:
    """공백 제거하여 구분 값 정규화 (예: '교 과 내 용' -> '교과내용')"""
    return raw.replace(" ", "").strip()


def get_category_color(raw: str) -> str:
    return CATEGORY_COLORS.get(normalize_category(raw), "#ffffff")


def parse_md_table(text: str) -> pd.DataFrame | None:
    """마크다운 텍스트에서 테이블을 파싱하여 DataFrame으로 반환"""
    lines = [l for l in text.strip().splitlines() if l.startswith("|")]
    if len(lines) < 3:
        return None
    header = [c.strip() for c in lines[0].split("|")[1:-1]]
    rows = []
    for line in lines[2:]:  # separator 건너뜀
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) == len(header):
            rows.append(cells)
    return pd.DataFrame(rows, columns=header)


def load_chapters():
    """output/ 디렉토리에서 장 목록 로딩"""
    chapters = {}
    for name in sorted(os.listdir(OUTPUT_DIR)):
        path = os.path.join(OUTPUT_DIR, name)
        if os.path.isdir(path):
            chapters[name] = path
    return chapters


def load_specialties():
    """제3장 하위 전공 목록 로딩"""
    ch3_dir = os.path.join(OUTPUT_DIR, "제3장_레지던트_연차별_수련_교과과정")
    if not os.path.isdir(ch3_dir):
        return {}
    specs = {}
    for name in sorted(os.listdir(ch3_dir), key=lambda x: int(re.match(r"(\d+)", x).group(1)) if re.match(r"(\d+)", x) else 999):
        path = os.path.join(ch3_dir, name, "main")
        if os.path.isdir(path):
            specs[name] = path
    return specs


def read_md_file(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def df_to_colored_html(df: pd.DataFrame, year_filter: str = "전체") -> str:
    """DataFrame을 구분별 색상이 적용된 HTML 테이블로 변환"""
    # 연차 forward fill
    df = df.copy()
    col_year = df.columns[0]  # 연차
    col_cat = df.columns[1]  # 구분
    col_content = df.columns[2]  # 내용
    # 연차 forward fill 후, 구분은 같은 연차 그룹 내에서만 forward fill
    df[col_year] = df[col_year].replace("", pd.NA).ffill().fillna("")
    df[col_cat] = df[col_cat].replace("", pd.NA)
    df[col_cat] = df.groupby(col_year)[col_cat].ffill().fillna("")

    # 연차 필터링
    if year_filter != "전체":
        df = df[df[col_year] == year_filter]
        if df.empty:
            return "<p>해당 연차 데이터가 없습니다.</p>"

    html = """<table style="width:100%; border-collapse:collapse; font-size:14px;">
    <thead><tr style="background:#1a237e; color:white;">
        <th style="padding:8px; border:1px solid #ccc; width:8%;">연차</th>
        <th style="padding:8px; border:1px solid #ccc; width:14%;">구분</th>
        <th style="padding:8px; border:1px solid #ccc; width:78%;">내용</th>
    </tr></thead><tbody>"""

    prev_year = None
    prev_cat = None
    for _, row in df.iterrows():
        year_val = str(row[col_year]).strip()
        cat_val = str(row[col_cat]).strip()
        content_val = str(row[col_content]).strip()
        bg = get_category_color(cat_val)

        # 연차/구분이 이전과 같으면 빈칸 표시
        show_year = year_val if year_val != prev_year else ""
        show_cat = cat_val if (year_val != prev_year or cat_val != prev_cat) else ""
        prev_year = year_val
        prev_cat = cat_val

        # 내용의 줄바꿈 처리
        content_html = content_val.replace("\n", "<br>")

        html += f"""<tr style="background:{bg};">
            <td style="padding:6px 8px; border:1px solid #ddd; font-weight:bold; vertical-align:top;">{show_year}</td>
            <td style="padding:6px 8px; border:1px solid #ddd; vertical-align:top;">{show_cat}</td>
            <td style="padding:6px 8px; border:1px solid #ddd; white-space:pre-wrap;">{content_html}</td>
        </tr>"""

    html += "</tbody></table>"
    return html


def render_chapter_content(chapter_path: str):
    """부칙/총칙/인턴수련 장의 마크다운 콘텐츠 렌더링"""
    for fname in sorted(os.listdir(chapter_path)):
        if fname.endswith(".md"):
            content = read_md_file(os.path.join(chapter_path, fname))
            st.markdown(content)


def render_specialty(spec_path: str, spec_name: str):
    """전공 상세 페이지 렌더링"""
    display_name = re.sub(r"^\d+\.", "", spec_name)
    st.header(f"🏥 {display_name}")

    # 교육목표
    goal_path = os.path.join(spec_path, "교육목표.md")
    if os.path.exists(goal_path):
        goal_text = read_md_file(goal_path)
        # 제목 줄 제거하고 본문만 추출
        goal_body = re.sub(r"^#.*\n+", "", goal_text).strip()
        st.info(f"**교육목표**\n\n{goal_body}")

    # 연차별 교과과정
    table_path = os.path.join(spec_path, "연차별_교과과정.md")
    if os.path.exists(table_path):
        table_text = read_md_file(table_path)
        df = parse_md_table(table_text)
        if df is not None:
            st.subheader("📋 연차별 교과과정")

            # 연차 필터 탭
            years = df[df.columns[0]].replace("", pd.NA).ffill().fillna("").unique()
            year_options = ["전체"] + [y for y in years if y]
            selected_year = st.radio(
                "연차 선택", year_options, horizontal=True, key="year_filter"
            )

            # 색상 범례
            legend_html = "<div style='margin:8px 0 12px 0; display:flex; flex-wrap:wrap; gap:8px;'>"
            for cat, color in CATEGORY_COLORS.items():
                legend_html += f"<span style='background:{color}; padding:2px 10px; border:1px solid #ccc; border-radius:4px; font-size:12px;'>{cat}</span>"
            legend_html += "</div>"
            st.markdown(legend_html, unsafe_allow_html=True)

            # HTML 테이블 렌더링
            html = df_to_colored_html(df, selected_year)
            st.markdown(html, unsafe_allow_html=True)

    # 첨부 테이블 (table_2.md, table_3.md 등)
    extra_tables = sorted(
        f for f in os.listdir(spec_path) if re.match(r"table_\d+\.md", f)
    )
    for tfile in extra_tables:
        tpath = os.path.join(spec_path, tfile)
        tcontent = read_md_file(tpath)
        tdf = parse_md_table(tcontent)
        table_title = re.search(r"^# (.+)", tcontent)
        title = table_title.group(1) if table_title else tfile.replace(".md", "")
        st.subheader(f"📎 {title}")
        if tdf is not None:
            st.dataframe(tdf, use_container_width=True, hide_index=True)
        else:
            st.markdown(tcontent)


def render_browse_tab():
    """교과과정 열람 탭"""
    chapters = load_chapters()
    specialties = load_specialties()

    chapter_names = list(chapters.keys())
    chapter_labels = {
        "부칙": "부칙",
        "제1장_총칙": "제1장 총칙",
        "제2장_인턴수련_교과과정": "제2장 인턴수련 교과과정",
        "제3장_레지던트_연차별_수련_교과과정": "제3장 레지던트 수련 교과과정",
    }

    display_names = [chapter_labels.get(c, c) for c in chapter_names]
    selected_idx = st.sidebar.radio(
        "장 선택",
        range(len(chapter_names)),
        format_func=lambda i: display_names[i],
    )
    selected_chapter = chapter_names[selected_idx]

    if selected_chapter == "제3장_레지던트_연차별_수련_교과과정":
        st.sidebar.markdown("---")
        spec_names = list(specialties.keys())
        spec_labels = [re.sub(r"^\d+\.", "", s) for s in spec_names]
        selected_spec_idx = st.sidebar.selectbox(
            "전공 선택",
            range(len(spec_names)),
            format_func=lambda i: spec_labels[i],
        )
        selected_spec = spec_names[selected_spec_idx]
        render_specialty(specialties[selected_spec], selected_spec)
    else:
        title = chapter_labels.get(selected_chapter, selected_chapter)
        st.header(f"{title}")
        render_chapter_content(chapters[selected_chapter])


def render_chat_tab():
    """AI 질의응답 탭"""
    from rag.indexer import is_index_built
    from rag.llm import generate_stream
    from rag.retriever import format_context, retrieve

    st.header("AI 교과과정 질의응답")
    st.caption("전공의 수련 교과과정에 대해 질문해보세요. (예: 내과 2년차 교과내용은?)")

    # 인덱스 확인
    if not is_index_built():
        with st.spinner("인덱스를 구축하고 있습니다... (최초 1회)"):
            from rag.chunker import generate_all_chunks
            from rag.indexer import rebuild_index

            chunks = generate_all_chunks()
            rebuild_index(chunks)
        st.success(f"인덱스 구축 완료!")

    # 채팅 기록 초기화
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # 사이드바 - 대화 초기화
    with st.sidebar:
        st.markdown("---")
        if st.button("대화 초기화"):
            st.session_state.messages = []
            st.rerun()

    # 채팅 기록 표시
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                with st.expander("참고 자료"):
                    for s in msg["sources"]:
                        label = s.get("specialty") or s.get("doc_type", "")
                        if s.get("year"):
                            label += f" {s['year']}년차" if s["year"] not in ("총계", "비고") else f" {s['year']}"
                        if s.get("category") and s["category"] != "전체":
                            label += f" - {s['category']}"
                        st.markdown(f"- {label}")

    # 채팅 입력
    if prompt := st.chat_input("질문을 입력하세요"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            # 검색
            results = retrieve(prompt)
            context = format_context(results)

            # 스트리밍 답변
            response_placeholder = st.empty()
            full_response = ""
            try:
                for token in generate_stream(prompt, context):
                    full_response += token
                    response_placeholder.markdown(full_response + "▌")
                response_placeholder.markdown(full_response)
            except Exception as e:
                full_response = f"LLM 응답 오류: {e}"
                response_placeholder.error(full_response)

            # 출처 표시
            source_info = [r["metadata"] for r in results]
            if source_info:
                with st.expander("참고 자료"):
                    for s in source_info:
                        label = s.get("specialty") or s.get("doc_type", "")
                        if s.get("year"):
                            label += f" {s['year']}년차" if s["year"] not in ("총계", "비고") else f" {s['year']}"
                        if s.get("category") and s["category"] != "전체":
                            label += f" - {s['category']}"
                        st.markdown(f"- {label}")

        st.session_state.messages.append(
            {"role": "assistant", "content": full_response, "sources": source_info}
        )


def main():
    st.set_page_config(page_title="전공의 수련교과과정", page_icon="🩺", layout="wide")

    st.sidebar.title("전공의 수련교과과정")
    st.sidebar.markdown("---")

    tab_browse, tab_chat = st.tabs(["교과과정 열람", "AI 질의응답"])

    with tab_browse:
        render_browse_tab()

    with tab_chat:
        render_chat_tab()


if __name__ == "__main__":
    main()
