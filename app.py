import streamlit as st
from typing import List
import re

# 페이지 기본 설정
st.set_page_config(page_title="TIPS 선정평가 종합의견 도우미", layout="wide")
st.title("TIPS 선정평가 종합의견 도우미 (MVP)")
st.caption("위원 5명의 의견을 항목별로 입력 → 중복 제거/취합 → 종합의견 초안 생성")

CATS = ["기술성", "사업성", "연구개발비 조정", "기타사항"]

def normalize(s: str) -> str:
    """간단한 정규화: 공백 정리/일부 특수문자 제거 → 중복 판단에 사용"""
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    # 핵심 구두점은 남기고 특수문자 과다 제거
    s = re.sub(r"[^\w\s가-힣.,()/\-%:+]", "", s)
    return s

def dedupe(lines: List[str]) -> List[str]:
    """정규화 기반 중복 제거"""
    seen = set()
    out = []
    for line in lines:
        if not line:
            continue
        n = normalize(line)
        if n and n not in seen:
            out.append(line.strip())
            seen.add(n)
    return out

def byte_len(s: str) -> int:
    return len(s.encode("utf-8"))

# 5명의 위원 입력 탭
tabs = st.tabs([f"위원 {i}" for i in range(1, 6)])
inputs = []
for i, tab in enumerate(tabs, start=1):
    with tab:
        st.subheader(f"위원 {i}")
        person = {}
        for c in CATS:
            person[c] = st.text_area(f"{c} 의견", height=120, key=f"{c}_{i}")
        inputs.append(person)

# 취합 버튼
if st.button("의견 취합하기"):
    st.success("항목별 의견을 취합했습니다.")
    # 1) 위원별 입력 → 항목별 묶기
    by_cat = {c: [] for c in CATS}
    for person in inputs:
        for c in CATS:
            text = person[c].strip()
            if text:
                by_cat[c].append(text)

    # 2) 여러 줄을 불릿 단위로 분할 + 중복 제거
    for c in CATS:
        expanded = []
        for t in by_cat[c]:
            parts = [p.strip("•-·* ").strip() for p in t.split("\n") if p.strip()]
            expanded.extend(parts)
        by_cat[c] = dedupe(expanded)

    # 3) 화면 표시
    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("### 항목별 취합 결과 (중복 제거 후)")
        for c in CATS:
            st.markdown(f"**{c}**")
            if by_cat[c]:
                st.markdown("\n".join([f"- {pt}" for pt in by_cat[c]]))
            else:
                st.markdown("- (의견 없음)")
            st.divider()

    # 4) 종합의견 초안 생성
    def build_summary(by_cat):
        parts = []
        parts.append("📌 종합의견(초안)\n")
        for c in CATS:
            parts.append(f"[{c}]")
            if by_cat[c]:
                parts.extend([f"- {pt}" for pt in by_cat[c]])
            else:
                parts.append("- 해당 없음")
            parts.append("")  # 줄바꿈
        parts.append("※ 평가단 승인사항 등 필수 항목은 협약 시점에 확인 바랍니다.")
        return "\n".join(parts)

    summary = build_summary(by_cat)

    with col2:
        st.markdown("### 종합의견 초안")
        st.text_area("자동 생성된 초안", summary, height=420, key="summary_area")
        limit = 4000
        length = byte_len(summary)
        st.write(f"글자수(바이트): **{length} / {limit}**")
        st.progress(min(length / limit, 1.0))
        st.download_button(
            "TXT로 다운로드",
            data=summary,
            file_name="종합의견_초안.txt",
            mime="text/plain"
        )
