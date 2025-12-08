import streamlit as st
import json
import os
from openai import OpenAI

# ----------------------------
# 기본 설정
# ----------------------------
st.set_page_config(page_title="TIPS 선정평가 종합의견 도우미(평가간사용)", layout="wide")

# OpenAI 클라이언트
api_key = os.environ.get("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY")
if not api_key:
    st.error("❌ OPENAI_API_KEY가 설정되어 있지 않습니다. Streamlit Secrets에 키를 등록해 주세요.")
    st.stop()

client = OpenAI(api_key=api_key)


# ----------------------------
# 유틸 함수
# ----------------------------
def build_system_prompt() -> str:
    """
    고도화된 종합의견 + 상이의견 탐지용 시스템 프롬프트
    """
    return """
당신은 한국 정부 R&D(TIPS) 평가에서 '종합의견'을 작성하는 베테랑 간사입니다.

입력으로 여러 평가위원의 의견이 주어집니다.
각 의견은 기술성, 사업성, 협약 시 보완사항, 연구개발비 조정의견, 기타의견이 섞여 있을 수 있습니다.

당신의 역할:

1. 모든 위원 의견을 꼼꼼하게 읽고, **중요한 내용은 절대 버리지 말고** 최대한 유지합니다.
   - 구체적인 지적사항, 수치, 조건, 권고사항, 금액, 일정 등은 그대로 살립니다.
   - 의미가 겹치는 문장은 하나로 묶되, 핵심 내용이 빠지지 않도록 합니다.

2. 내용을 아래 5개 항목으로 재분류하여 통합합니다.
   (1) 기술성 종합의견
   (2) 사업성 종합의견
   (3) 협약시 보완사항
   (4) 연구개발비 조정의견
   (5) 기타의견

3. 새로운 주장이나 근거를 만들어내지 않고, 위원 의견 안에서만 종합합니다.

4. 전체 분량은 한글 2500~3500자(A4 1~1.5장) 정도.
   — 중요한 내용은 절대 삭제하지 말 것.
   — 과도한 요약 금지.

5. 추가로, 각 위원 의견을 서로 비교하여 **눈에 띄게 상이한 평가**를 한 위원을 찾아,
   아래 형식으로 "disagreements" 항목에 정리합니다.
   - 예: 어떤 위원은 기술성을 "매우 높음"으로 평가했는데, 다른 대부분 위원은 "낮음/보통"이라고 한 경우
   - 예: 어떤 위원이 특정 협약시 보완사항을 강하게 요구하지만, 다른 위원들은 언급하지 않은 경우 등

   "disagreements": [
     {
       "reviewer_index": 2,
       "reason": "기술성을 낮다고 평가하였으나, 다른 위원들은 대체로 높게 평가함"
     },
     ...
   ]

   * reviewer_index는 1부터 시작하는 정수입니다.
   * 상이한 의견이 뚜렷이 보이지 않으면 빈 배열([])로 둡니다.

6. 반드시 JSON 형식으로만 응답:

{
  "technical": "",
  "business": "",
  "cooperation": "",
  "rd_budget": "",
  "other": "",
  "disagreements": []
}
    """.strip()


def call_openai_summary(reviewer_texts, reviewer_names):
    """OpenAI Responses API 호출 (종합의견 + 상이의견 분석)"""
    system_prompt = build_system_prompt()

    user_content = "다음은 각 평가위원이 작성한 평가 의견입니다.\n각 위원은 reviewer_index로 구분됩니다.\n\n"
    for idx, (name, txt) in enumerate(zip(reviewer_names, reviewer_texts), start=1):
        text_clean = txt.strip() or "(의견 없음)"
        user_content += f"[reviewer_index: {idx}, 이름: {name}]\n{text_clean}\n\n"

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
    )

    raw_text = response.output[0].content[0].text
    data = json.loads(raw_text)

    # 기본 키 보정
    for key in ["technical", "business", "cooperation", "rd_budget", "other"]:
        data.setdefault(key, "")

    # 상이의견 필드 보정
    disagreements = data.get("disagreements", [])
    if not isinstance(disagreements, list):
        disagreements = []
    data["disagreements"] = disagreements

    return data


def build_formatted_summary(data):
    """JSON → 최종 출력용 텍스트"""
    parts = []

    if data.get("technical", "").strip():
        parts.append("1. 기술성 종합의견\n" + data["technical"].strip())
    if data.get("business", "").strip():
        parts.append("2. 사업성 종합의견\n" + data["business"].strip())
    if data.get("cooperation", "").strip():
        parts.append("3. 협약시 보완사항\n" + data["cooperation"].strip())
    if data.get("rd_budget", "").strip():
        parts.append("4. 연구개발비 조정의견\n" + data["rd_budget"].strip())
    if data.get("other", "").strip():
        parts.append("5. 기타의견\n" + data["other"].strip())

    return "\n\n".join(parts).strip()


def byte_length(text: str) -> int:
    return len(text.encode("utf-8"))


# ----------------------------
# UI 시작
# ----------------------------

st.title("TIPS 선정평가 종합의견 도우미(평가간사용)")
st.write(
    "각 위원의 **혼합된 전체 의견**을 한 칸에 붙여넣으세요. "
    "(기술성/사업성/연구개발비 조정/기타사항이 섞여 있어도 됩니다.) "
    "`종합의견 생성`을 누르면 5개 항목으로 자동 분류·취합됩니다."
)

# ----------------------------
# 🔧 평가위원 수 + 위원 이름 입력
# ----------------------------
st.sidebar.header("설정")
num_reviewers = st.sidebar.number_input("평가위원 수", min_value=1, max_value=5, value=4, step=1)

reviewer_names = []
for i in range(num_reviewers):
    name = st.sidebar.text_input(f"위원{i+1} 이름", value=f"위원{i+1}")
    reviewer_names.append(name)

# 이름을 세션에 저장 (상이의견 요약에서 사용)
st.session_state["reviewer_names"] = reviewer_names

# ----------------------------
# 위원별 의견 입력
# ----------------------------
st.markdown("### 위원별 평가 의견 입력")

cols = st.columns(num_reviewers)
reviewer_texts = []

for i in range(num_reviewers):
    with cols[i]:
        txt = st.text_area(
            f"{reviewer_names[i]} 의견 입력",
            value="",
            height=220,
            placeholder="위원 전체 의견을 그대로 붙여넣으세요.",
        )
        reviewer_texts.append(txt)

# (나중에 빨간 표시를 위해 미리 상이의견 정보 준비)
disagree_info = {}
if "last_sections" in st.session_state and st.session_state["last_sections"]:
    for item in st.session_state["last_sections"].get("disagreements", []):
        idx = item.get("reviewer_index")
        if not isinstance(idx, int):
            continue
        reason = item.get("reason", "").strip()
        if not reason:
            continue
        disagree_info.setdefault(idx, []).append(reason)

# 위원별 상이의견 빨간 표시 (의견 입력칸 바로 아래)
for i in range(num_reviewers):
    if disagree_info.get(i + 1):
        with cols[i]:
            reasons_joined = "; ".join(disagree_info[i + 1])
            st.markdown(
                f"<span style='color:red; font-weight:bold;'>⚠ 상이의견 감지: {reasons_joined}</span>",
                unsafe_allow_html=True,
            )

st.write("")
generate = st.button("🔴 종합의견 생성", type="primary")


# ----------------------------
# 세션 상태 초기화
# ----------------------------
if "summary_text" not in st.session_state:
    st.session_state["summary_text"] = ""
if "last_sections" not in st.session_state:
    st.session_state["last_sections"] = None


# ----------------------------
# 종합의견 생성
# ----------------------------
if generate:
    if not any(t.strip() for t in reviewer_texts):
        st.warning("⚠ 최소 1명 이상의 의견을 입력해야 합니다.")
    else:
        with st.spinner("종합의견 생성 중..."):
            try:
                sections = call_openai_summary(reviewer_texts, reviewer_names)
                formatted = build_formatted_summary(sections)

                st.session_state["summary_text"] = formatted
                st.session_state["last_sections"] = sections

                st.success("✅ 종합의견 생성이 완료되었습니다!")
            except Exception as e:
                st.error(f"❌ 오류 발생: {e}")


# ----------------------------
# 종합의견 출력
# ----------------------------
st.markdown("### 종합의견 초안")

summary_text = st.text_area(
    "종합의견 초안",
    value=st.session_state.get("summary_text", ""),
    height=350,
)

st.caption(f"글자수(바이트): {byte_length(summary_text)} / 4000")

# ----------------------------
# 섹션별 상세 보기
# ----------------------------
if st.session_state.get("last_sections"):
    sections = st.session_state["last_sections"]
    with st.expander("▸ 섹션별 내용 자세히 보기"):
        st.markdown("#### 1. 기술성 종합의견")
        st.write(sections.get("technical", "").strip() or "-")
        st.markdown("#### 2. 사업성 종합의견")
        st.write(sections.get("business", "").strip() or "-")
        st.markdown("#### 3. 협약시 보완사항")
        st.write(sections.get("cooperation", "").strip() or "-")
        st.markdown("#### 4. 연구개발비 조정의견")
        st.write(sections.get("rd_budget", "").strip() or "-")
        st.markdown("#### 5. 기타의견")
        st.write(sections.get("other", "").strip() or "-")

# ----------------------------
# ⚠ 상이의견 요약 섹션 (종합의견 아래)
# ----------------------------
if st.session_state.get("last_sections"):
    disagreements = st.session_state["last_sections"].get("disagreements", [])
    reviewer_names_saved = st.session_state.get("reviewer_names", [])
    if disagreements:
        st.markdown("#### ⚠ 상이의견 요약")
        for item in disagreements:
            idx = item.get("reviewer_index")
            reason = item.get("reason", "").strip()
            if not isinstance(idx, int) or not reason:
                continue
            name = (
                reviewer_names_saved[idx - 1]
                if 0 < idx <= len(reviewer_names_saved)
                else f"위원{idx}"
            )
            st.markdown(
                f"- **{name}** (위원{idx}): <span style='color:red;'>{reason}</span>",
                unsafe_allow_html=True,
            )

# ----------------------------
# TXT 다운로드
# ----------------------------
if summary_text.strip():
    st.download_button(
        label="📄 TXT로 다운로드",
        data=summary_text.encode("utf-8"),
        file_name="tips_summary.txt",
        mime="text/plain",
    )
