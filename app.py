import streamlit as st

st.title("TIPS 선정평가 종합의견 도우미 (MVP)")
st.write("이 앱은 평가위원별 의견을 취합하고 정리하여 간사님의 종합의견 작성 시간을 줄여줍니다.")

# ----------------------------
# 🔧 전처리 함수들
# ----------------------------

# 오타 및 표현 통일
def normalize_text(text):
    if not text:
        return ""
    replacements = {
        "우수힘": "우수함",
        "높지 않다": "낮다",
        "보기 어렵다": "판단하기 어렵다",
        "어려움": "판단하기 어렵다",
        "수준이 낮다": "낮다",
        "수준이 높지 않다": "낮다",
        "수준이 높다고 보기에는 어렵다": "판단하기 어렵다",
    }
    for wrong, correct in replacements.items():
        text = text.replace(wrong, correct)
    return text

# 중복 제거 (단어 순서 차이가 있어도 같은 의미로 판단)
def deduplicate(opinions):
    unique = []
    seen = set()
    for op in opinions:
        norm = " ".join(sorted(op.split()))  # 단어 정렬해서 순서 차이 보정
        if norm not in seen:
            seen.add(norm)
            unique.append(op)
    return unique

# 전처리 (오타 수정 + 중복 제거)
def preprocess_opinions(opinions):
    cleaned = [normalize_text(op.strip()) for op in opinions if op.strip()]
    return deduplicate(cleaned)


# ----------------------------
# 🔧 입력 UI
# ----------------------------
st.header("위원별 의견 입력")

num_reviewers = st.number_input("평가위원 수를 입력하세요", min_value=1, max_value=5, value=3)

tech_inputs, biz_inputs, budget_inputs, etc_inputs = [], [], [], []

for i in range(num_reviewers):
    st.subheader(f"위원 {i+1}")
    tech_inputs.append(st.text_area(f"기술성 의견 (위원 {i+1})"))
    biz_inputs.append(st.text_area(f"사업성 의견 (위원 {i+1})"))
    budget_inputs.append(st.text_area(f"연구개발비 조정 의견 (위원 {i+1})"))
    etc_inputs.append(st.text_area(f"기타사항 (위원 {i+1})"))

# ----------------------------
# 🔧 필수 문구 입력
# ----------------------------
st.header("필수 문구 입력 (간사가 반드시 작성해야 함)")
required_phrases = st.text_area("예: 평가단 승인사항, 협약 시 보완사항", "")


# ----------------------------
# 🔧 결과 생성 버튼
# ----------------------------
if st.button("종합의견 생성"):
    tech_opinions = preprocess_opinions(tech_inputs)
    biz_opinions = preprocess_opinions(biz_inputs)
    budget_opinions = preprocess_opinions(budget_inputs)
    etc_opinions = preprocess_opinions(etc_inputs)

    # 항목별 취합 결과 표시
    st.subheader("📌 항목별 취합 결과 (중복 제거 후)")
    st.write("**기술성**", tech_opinions)
    st.write("**사업성**", biz_opinions)
    st.write("**연구개발비 조정**", budget_opinions)
    st.write("**기타사항**", etc_opinions)

    # ----------------------------
    # 🔧 종합의견 초안 생성
    # ----------------------------
    summary = "✨ 종합의견(초안)\n\n"

    # 기술성
    if len(set(tech_opinions)) > 1:
        summary += "[기술성] ⚠️ 위원 간 의견이 상이합니다:\n"
        for op in tech_opinions:
            summary += f"- {op}\n"
    elif tech_opinions:
        summary += "[기술성] " + ", ".join(tech_opinions) + "\n"

    # 사업성
    if len(set(biz_opinions)) > 1:
        summary += "\n[사업성] ⚠️ 위원 간 의견이 상이합니다:\n"
        for op in biz_opinions:
            summary += f"- {op}\n"
    elif biz_opinions:
        summary += "\n[사업성] " + ", ".join(biz_opinions) + "\n"

    # 연구개발비 조정
    if budget_opinions:
        summary += "\n[연구개발비 조정] " + ", ".join(budget_opinions) + "\n"

    # 기타사항
    if etc_opinions:
        summary += "\n[기타사항] " + ", ".join(etc_opinions) + "\n"

    # 필수 문구 확인
    missing_phrases = []
    if required_phrases:
        for phrase in required_phrases.split(","):
            phrase = phrase.strip()
            if phrase and phrase not in summary:
                missing_phrases.append(phrase)

    if missing_phrases:
        summary += "\n❌ 누락된 필수 문구: " + ", ".join(missing_phrases)

    # ----------------------------
    # 🔧 글자수 계산
    # ----------------------------
    byte_count = len(summary.encode("utf-8"))
    summary += f"\n\n글자수(바이트): {byte_count}/4000"

    st.subheader("종합의견 초안")
    st.text_area("원본 종합의견", summary, height=300)

    # ----------------------------
    # 🔧 글자수 초과 처리
    # ----------------------------
    if byte_count > 4000:
        st.error("⚠️ 글자수가 4000byte를 초과했습니다. 아래 버튼을 눌러 요약을 진행하세요.")

        if st.button("✂️ 글자수 줄이기"):
            # 간단 요약: 문단별 첫 문장만 남기기
            shortened = "\n".join([line.split(".")[0] for line in summary.split("\n") if line.strip()])
            shortened_byte = len(shortened.encode("utf-8"))

            st.subheader("줄이기 전/후 비교")
            st.write("**줄이기 전 (원본):**")
            st.text_area("원본", summary, height=200)
            st.write("**줄인 후:**")
            st.text_area("줄인 결과", shortened + f"\n\n글자수(바이트): {shortened_byte}/4000", height=200)
