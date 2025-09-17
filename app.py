import streamlit as st
import re
from collections import Counter
from io import BytesIO

st.set_page_config(page_title="TIPS 종합의견 도우미", layout="wide")

st.title("📝 TIPS 선정평가 종합의견 도우미")
st.write("위원별 의견을 취합하고 정리하여 간사님의 종합의견 작성 시간을 줄여줍니다.")

# ----------------------------
# 사이드바
# ----------------------------
with st.sidebar:
    st.header("⚙️ 설정")
    num_reviewers = st.number_input("평가위원 수", min_value=1, max_value=5, value=3)
    required_phrases = st.text_area("필수 문구 입력", "평가단 승인사항, 협약 시 보완사항")

    reviewer_names = []
    for i in range(num_reviewers):
        name = st.text_input(f"위원 {i+1} 이름", f"위원{i+1}")
        reviewer_names.append(name)

# ----------------------------
# 전처리 함수
# ----------------------------
def normalize_text(text):
    if not text:
        return ""
    replacements = {
        "우수힘": "우수함",
        "높지 않다": "낮다",
        "보기 어렵다": "판단하기 어렵다",
        "어려움": "판단하기 어렵다",
    }
    for wrong, correct in replacements.items():
        text = text.replace(wrong, correct)
    return text

def deduplicate(opinions):
    unique, seen = [], set()
    for op in opinions:
        norm = " ".join(sorted(op.split()))
        if norm not in seen:
            seen.add(norm)
            unique.append(op)
    return unique

def preprocess_opinions(opinions):
    cleaned = [normalize_text(op.strip()) for op in opinions if op.strip()]
    return deduplicate(cleaned)

def byte_len(s): 
    return len(s.encode("utf-8"))

def summarize_text(text, limit=3900):
    sentences = [s.strip() for s in re.split(r'[.!?]\s*', text) if s.strip()]
    words = re.findall(r'\w+', text)
    freq = Counter(words)
    scores = {s: sum(freq[w] for w in re.findall(r'\w+', s)) for s in sentences}
    ranked = sorted(scores, key=scores.get, reverse=True)

    summary, current = [], 0
    for s in ranked:
        if current + byte_len(s) > limit: break
        summary.append(s); current += byte_len(s)
    return " ".join(summary)

# ----------------------------
# 의견 입력 (탭 구조)
# ----------------------------
st.header("💬 위원별 의견 입력")

tab1, tab2, tab3, tab4 = st.tabs(["기술성", "사업성", "연구개발비 조정", "기타사항"])

tech_inputs, biz_inputs, budget_inputs, etc_inputs = [], [], [], []

with tab1:
    for i, name in enumerate(reviewer_names):
        tech_inputs.append(st.text_area(f"기술성 의견 ({name})"))

with tab2:
    for i, name in enumerate(reviewer_names):
        biz_inputs.append(st.text_area(f"사업성 의견 ({name})"))

with tab3:
    for i, name in enumerate(reviewer_names):
        budget_inputs.append(st.text_area(f"연구개발비 조정 의견 ({name})"))

with tab4:
    for i, name in enumerate(reviewer_names):
        etc_inputs.append(st.text_area(f"기타사항 ({name})"))

# ----------------------------
# 결과 생성
# ----------------------------
if st.button("🚀 종합의견 생성"):
    tech = preprocess_opinions(tech_inputs)
    biz = preprocess_opinions(biz_inputs)
    budget = preprocess_opinions(budget_inputs)
    etc = preprocess_opinions(etc_inputs)

    summary = "✨ 종합의견(초안)\n\n"

    if len(set(tech)) > 1:
        summary += "[기술성] ⚠️ 의견 상이:\n" + "\n".join([f"- {op}" for op in tech]) + "\n"
    elif tech:
        summary += "[기술성] " + ", ".join(tech) + "\n"

    if len(set(biz)) > 1:
        summary += "\n[사업성] ⚠️ 의견 상이:\n" + "\n".join([f"- {op}" for op in biz]) + "\n"
    elif biz:
        summary += "\n[사업성] " + ", ".join(biz) + "\n"

    if budget:
        summary += "\n[연구개발비 조정] " + ", ".join(budget) + "\n"
    if etc:
        summary += "\n[기타사항] " + ", ".join(etc) + "\n"

    # 필수 문구 체크
    missing = []
    for phrase in required_phrases.split(","):
        phrase = phrase.strip()
        if phrase and phrase not in summary:
            missing.append(phrase)
    if missing:
        summary += "\n❌ 누락된 필수 문구: " + ", ".join(missing)

    # 글자수
    byte_count = byte_len(summary)
    summary += f"\n\n글자수(바이트): {byte_count}/4000"

    # ----------------------------
    # UI 표시
    # ----------------------------
    st.header("📑 종합의견 결과")
    st.info(summary)

    # ----------------------------
    # 📥 TXT 다운로드 버튼만
    # ----------------------------
    st.download_button(
        label="📥 종합의견 TXT 다운로드",
        data=summary,
        file_name="종합의견.txt",
        mime="text/plain"
    )

    # 글자수 초과 처리
    if byte_count > 4000:
        st.error("⚠️ 4000byte 초과")
        if st.button("✂️ 글자수 줄이기"):
            short = summarize_text(summary)
            short_len = byte_len(short)
            st.success(f"✂️ 요약 완료 ({short_len}/4000)")
            st.text_area("줄인 결과", short, height=200)

