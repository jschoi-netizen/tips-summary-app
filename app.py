import streamlit as st
from difflib import SequenceMatcher
from spellchecker import SpellChecker

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(page_title="TIPS 선정평가 종합의견 도우미", layout="wide")
st.title("TIPS 선정평가 종합의견 도우미 (개선버전)")
st.caption("위원별 의견을 취합, 교정, 중복 제거 후 종합의견을 자동 생성합니다.")

spell = SpellChecker()

# -----------------------------
# 함수 정의
# -----------------------------
def correct_text(text):
    """맞춤법 교정"""
    words = text.split()
    corrected = [spell.correction(w) if spell.correction(w) else w for w in words]
    return " ".join(corrected)

def is_similar(a, b, threshold=0.8):
    """문장 유사도 비교"""
    return SequenceMatcher(None, a, b).ratio() > threshold

def merge_opinions(opinions):
    """중복/유사 문장 제거"""
    unique = []
    for op in opinions:
        op = op.strip()
        if not op:
            continue
        if not any(is_similar(op, u) for u in unique):
            unique.append(op)
    return unique

def byte_len(s: str) -> int:
    return len(s.encode("utf-8"))

# -----------------------------
# 필수 문구 입력 (간사)
# -----------------------------
st.sidebar.header("⚠️ 필수 문구 설정")
required_phrases = st.sidebar.text_area(
    "필수 문구를 입력하세요 (줄바꿈으로 구분)", 
    "평가단 승인사항\n협약 시 보완사항"
).split("\n")
required_phrases = [p.strip() for p in required_phrases if p.strip()]

# -----------------------------
# 위원별 의견 입력
# -----------------------------
num_reviewers = 5
categories = ["기술성", "사업성", "연구개발비 조정", "기타사항"]
inputs = {c: [] for c in categories}

st.header("위원별 의견 입력")
tabs = st.tabs([f"위원 {i+1}" for i in range(num_reviewers)])

for i, tab in enumerate(tabs):
    with tab:
        st.subheader(f"위원 {i+1}")
        for cat in categories:
            txt = st.text_area(f"{cat} 의견", key=f"{cat}_{i}", height=120)
            corrected_txt = correct_text(txt) if txt else ""
            if corrected_txt:
                inputs[cat].append(corrected_txt)

# -----------------------------
# 종합의견 생성
# -----------------------------
if st.button("종합의견 생성"):
    summary = "✨ 종합의견(초안)\n\n"
    over_limit = False

    for cat in categories:
        merged = merge_opinions(inputs[cat])

        if not merged:
            continue

        # 의견이 상이한 경우 표시
        if len(merged) > 1:
            summary += f"[{cat}] ⚠️ 위원 간 의견이 상이합니다:\n"
        else:
            summary += f"[{cat}]\n"

        for m in merged:
            summary += f"- {m}\n"
        summary += "\n"

    # 필수 문구 검증
    missing = [p for p in required_phrases if not any(p in s for s in summary.splitlines())]
    if missing:
        summary += f"\n❌ 누락된 필수 문구: {', '.join(missing)}\n"
    else:
        summary += "\n✅ 모든 필수 문구가 포함되어 있습니다.\n"

    # 글자수 카운트
    length = byte_len(summary)
    summary += f"\n글자수(바이트): {length}/4000\n"

    # 글자수 초과 시 자동 줄이기
    if length > 4000:
        over_limit = True
        st.warning("⚠️ 글자수가 4000byte를 초과했습니다. 자동으로 줄인 버전을 아래에 표시합니다.")

    st.markdown("### 종합의견 초안")
    st.text_area("원본 종합의견", summary, height=400)

    if over_limit:
        shortened = summary[:3900] + "...(이하 생략)"
        st.text_area("줄인 종합의견", shortened, height=300)
        st.success("✂️ 줄이기 완료 (원본과 비교 가능)")
