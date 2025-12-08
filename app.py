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
    여러 위원의 평가 의견을 받아,
    기술성/사업성/협약 시 보완사항/연구개발비 조정의견/기타의견
    5개 항목으로 통합 종합의견을 만드는 역할을 정의한 프롬프트
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
       - 성과지표, 기술적 파급효과, 개발 필요성, 기술 구현 가능성, 안정성 등
   (2) 사업성 종합의견
       - 시장성, 글로벌 진출 가능성, 경제적 파급효과, 일자리 창출 등
   (3) 협약시 보완사항
       - 협약 체결 전·후에 반드시 보완해야 할 사항(성과지표 보완, 추진체계 보완 등)
   (4) 연구개발비 조정의견
       - 허용/불허, 삭감·전용 필요, 세목별 조정 의견 등
   (5) 기타의견
       - 위탁연구개발기관 관련, 제도적 사항, 평가 절차 관련 코멘트 등

3. 각 항목은 **위원 의견을 근거로 한 종합의견**이어야 하며,
   새로운 주장이나 근거를 임의로 만들어 내지 않습니다.

4. 분량:
   - 전체 종합의견은 한글 기준 약 2,500~3,500자 정도(A4 1~1.5장)를 목표로 합니다.
   - 다만 중요한 내용 때문에 조금 더 길어지는 것은 허용됩니다.
   - 과도하게 짧게 요약하지 마세요. 위원 의견이 가진 뉘앙스와 구체성을 유지해야 합니다.

5. 문체:
   - 실제 정부 R&D 평가 종합의견처럼, 존칭 없이 서술형·보고서 형식으로 작성합니다.
   - 각 항목 안에서는 여러 문단(또는 여러 문장)으로 자연스럽게 서술합니다.

반드시 아래 JSON 형식으로만 응답하세요. 설명이나 여분의 텍스트를 붙이지 마세요.

{
  "technical": "여기에 기술성 종합의견을 한국어로 작성",
  "business": "여기에 사업성 종합의견을 한국어로 작성",
  "cooperation": "여기에 협약시 보완사항을 한국어로 작성 (없으면 빈 문자열 \"\")",
  "rd_budget": "여기에 연구개발비 조정의견을 한국어로 작성 (없으면 빈 문자열 \"\")",
  "other": "여기에 기타의견을 한국어로 작성 (없으면 빈 문자열 \"\")"
}
    """.strip()


def call_openai_summary(reviewer_texts):
    """OpenAI Responses API를 호출하여 JSON 형식 종합의견을 받는다."""
    system_prompt = build_system_prompt()

    # 사용자 입력 구성
    user_content = "다음은 각 평가위원이 작성한 평가 의견입니다.\n\n"
    for idx, txt in enumerate(reviewer_texts, start=1):
        user_content += f"[위원 {idx} 의견]\n{txt.strip()}\n\n"

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
    )

    # responses API 구조에 맞게 텍스트 추출
    raw_text = response.output[0].content[0].text

    data = json.loads(raw_text)

    # 비어있을 수 있는 필드를 기본값으로 보정
    for key in ["technical", "business", "cooperation", "rd_budget", "other"]:
        data.setdefault(key, "")

    return data


def build_formatted_summary(data):
    """JSON 데이터로부터 최종 출력용 텍스트를 조합"""
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

    # 항목 중 일부가 비어 있을 수 있으니 join
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

# 평가위원 수 (최대 5명 정도 가정)
num_reviewers = st.number_input("평가위원 수", min_value=1, max_value=5, value=4, step=1)

st.markdown("### 위원별 평가 의견 입력")

cols = st.columns(num_reviewers)
reviewer_texts = []
for i in range(num_reviewers):
    with cols[i]:
        txt = st.text_area(
            f"위원{i+1}",
            value="",
            height=220,
            placeholder="위원 전체 의견을 그대로 붙여넣으세요.",
        )
        reviewer_texts.append(txt)

st.write("")
generate = st.button("🔴 종합의견 생성", type="primary")

# 세션 상태 초기화
if "summary_text" not in st.session_state:
    st.session_state["summary_text"] = ""
if "last_sections" not in st.session_state:
    st.session_state["last_sections"] = None

if generate:
    # 유효한(빈칸이 아닌) 의견만 사용
    valid_texts = [t for t in reviewer_texts if t.strip()]
    if not valid_texts:
        st.warning("⚠️ 입력된 위원 의견이 없습니다. 최소 1명 이상의 의견을 넣어주세요.")
    else:
        with st.spinner("종합의견을 생성하는 중입니다... (수 초 소요)"):
            try:
                sections = call_openai_summary(valid_texts)
                formatted = build_formatted_summary(sections)

                st.session_state["summary_text"] = formatted
                st.session_state["last_sections"] = sections

                st.success("✅ 종합의견 생성이 완료되었습니다.")
            except Exception as e:
                st.error(f"❌ OpenAI 호출 중 오류가 발생했습니다: {e}")

st.markdown("### 종합의견 초안")

summary_text = st.session_state.get("summary_text", "")
summary_text = st.text_area(
    "종합의견 초안",
    value=summary_text,
    height=350,
)

# 바이트 수 표시
st.caption(f"글자수(바이트 기준): {byte_length(summary_text)} / 4000")

# 섹션별 요약 보기
if st.session_state.get("last_sections"):
    with st.expander("▸ 섹션별 내용 자세히 보기"):
        sec = st.session_state["last_sections"]
        st.markdown("#### 1. 기술성 종합의견")
        st.write(sec.get("technical", "").strip() or "-")

        st.markdown("#### 2. 사업성 종합의견")
        st.write(sec.get("business", "").strip() or "-")

        st.markdown("#### 3. 협약시 보완사항")
        st.write(sec.get("cooperation", "").strip() or "-")

        st.markdown("#### 4. 연구개발비 조정의견")
        st.write(sec.get("rd_budget", "").strip() or "-")

        st.markdown("#### 5. 기타의견")
        st.write(sec.get("other", "").strip() or "-")


st.write("")
# TXT 다운로드 버튼
if summary_text.strip():
    st.download_button(
        label="📄 TXT로 다운로드",
        data=summary_text.encode("utf-8"),
        file_name="tips_summary.txt",
        mime="text/plain",
    )
