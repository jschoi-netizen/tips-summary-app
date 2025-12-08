import json
import re
import streamlit as st
from openai import OpenAI

# OpenAI 클라이언트 (키는 Streamlit Secrets에서 자동으로 읽힘)
client = OpenAI()

st.set_page_config(
    page_title="TIPS 선정평가 종합의견 도우미(평가간사용)",
    layout="wide",
)

# ------------------------------
# 페이지 상단 제목 / 설명
# ------------------------------
st.title("TIPS 선정평가 종합의견 도우미(평가간사용)")

st.markdown(
    """
각 위원의 **혼합된 전체 의견**을 한 칸에 붙여넣어 주세요.  
(기술성/사업성/연구개발비 조정/기타사항이 섞여 있어도 됩니다.)  
**종합의견 생성** 버튼을 누르면 아래 5개 항목으로 자동 분류·취합됩니다.

1. 기술성 종합의견  
2. 사업성 종합의견  
3. 협약 시 보완사항  
4. 연구개발비 조정의견  
5. 기타 의견
"""
)

st.divider()

# ------------------------------
# 위원 설정 (이름 + 의견 입력)
# ------------------------------
NUM_REVIEWERS = 5

cols = st.columns(NUM_REVIEWERS)
reviewer_names = []
reviewer_texts = []

for i in range(NUM_REVIEWERS):
    with cols[i]:
        name = st.text_input(f"위원{i+1} 이름", value=f"위원{i+1}", key=f"name_{i}")
        reviewer_names.append(name)
        txt = st.text_area(
            f"{name} 의견 입력",
            height=260,
            key=f"text_{i}",
            placeholder="각 위원이 작성한 평가 의견 전체를 붙여넣어 주세요.",
        )
        reviewer_texts.append(txt.strip())

st.divider()

# ------------------------------
# 종합의견 생성 버튼
# ------------------------------
generate = st.button("🔴 종합의견 생성", type="primary")

# 종합의견 결과를 보여줄 자리
st.subheader("종합의견 초안")
summary_area = st.empty()  # 나중에 text_area로 채워넣음

# 상이 의견 표시용 컨테이너
disagree_container = st.container()

# ------------------------------
# GPT 호출 & JSON 파싱 함수
# ------------------------------


def call_openai_for_summary(names, opinions):
    """위원별 의견을 입력받아 OpenAI로 종합의견 JSON을 생성."""
    # 의견이 하나도 없으면 그냥 빈 결과 반환
    joined = [op for op in opinions if op]
    if not joined:
        return None

    # 프롬프트 구성: 위원 이름 + 의견
    reviewers_block = ""
    for idx, (nm, op) in enumerate(zip(names, opinions), start=1):
        if not op:
            continue
        reviewers_block += f"[위원 {idx}: {nm}]\n{op}\n\n"

    system_prompt = """
당신은 한국의 TIPS R&D 선정평가 간사를 돕는 도우미입니다.
아래 '위원별 의견'을 참고하여, 기술성 / 사업성 / 협약시 보완사항 / 연구개발비 조정의견 / 기타 의견을 종합해 주세요.

반드시 한국어로 작성하고, 아래 JSON 형식으로만 출력해야 합니다.

{
  "tech_summary": "...",          # 1. 기술성 종합의견 (중요 문장은 가능한 한 그대로 유지, 불필요한 반복만 줄이기)
  "biz_summary": "...",           # 2. 사업성 종합의견
  "improve_summary": "...",       # 3. 협약시 보완사항 (성과지표 수정, 추진체계/일정 보완 등)
  "budget_summary": "...",        # 4. 연구개발비 조정의견 (허용/불허, 조정 필요 항목 등)
  "other_summary": "...",         # 5. 기타 의견 (위탁연구개발기관 등 기타 중요사항)
  "disagreements": [
     {
       "reviewer_index": 1,
       "reviewer_name": "위원1",
       "reason": "다른 위원들과 달리 연구개발비 조정에 대해 전면 불허 의견을 제시함"
     }
  ]
}

규칙:
- 각 summary는 3~10문장 정도의 단락으로 작성하고, 내용이 없다면 "별도 기재된 사항 없음." 과 같이 간단히 적으세요.
- 중요한 평가 포인트(삭제/불허, 조건부 허용, 성능지표 보완 등)는 절대로 생략하지 말고, 가급적 원문 표현을 유지하세요.
- "disagreements"에는 다른 위원들과 뚜렷하게 충돌하거나 소수 의견으로 보이는 내용만 넣으세요.
- reviewer_index는 위원1=1, 위원2=2 ... 와 같이 1부터 시작하는 정수입니다.
"""

    user_prompt = f"다음은 위원별 의견입니다:\n\n{reviewers_block}\n\n위 형식의 JSON으로만 답변해 주세요."

    # chat.completions API 사용 (버전 상관없이 안정적)
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )

    raw = completion.choices[0].message.content

    # JSON 파싱 시도
    try:
        data = json.loads(raw)
        return data
    except json.JSONDecodeError:
        # ```json ... ``` 형태나 텍스트+JSON 혼합 대응
        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            st.error("GPT 응답을 JSON으로 파싱하지 못했습니다. 응답 내용:\n\n" + raw)
            return None
        try:
            data = json.loads(match.group(0))
            return data
        except json.JSONDecodeError:
            st.error("GPT 응답 JSON 파싱에 실패했습니다. 응답 내용:\n\n" + raw)
            return None


# ------------------------------
# 버튼 눌렸을 때: 종합의견 생성
# ------------------------------
if generate:
    with st.spinner("GPT가 종합의견을 생성 중입니다..."):
        result = call_openai_for_summary(reviewer_names, reviewer_texts)

    if result is None:
        st.stop()

    # 종합의견 텍스트 구성
    tech = result.get("tech_summary", "").strip() or "별도 기재된 사항 없음."
    biz = result.get("biz_summary", "").strip() or "별도 기재된 사항 없음."
    improve = result.get("improve_summary", "").strip() or "별도 기재된 사항 없음."
    budget = result.get("budget_summary", "").strip() or "별도 기재된 사항 없음."
    other = result.get("other_summary", "").strip() or "별도 기재된 사항 없음."

    final_text = (
        "1. 기술성 종합의견\n" + tech + "\n\n"
        "2. 사업성 종합의견\n" + biz + "\n\n"
        "3. 협약시 보완사항\n" + improve + "\n\n"
        "4. 연구개발비 조정의견\n" + budget + "\n\n"
        "5. 기타 의견\n" + other
    )

    # 화면에 종합의견 표시
    summary_area.text_area(
        "종합의견 초안(자동 생성)",
        value=final_text,
        height=320,
    )

    # 상이 의견 표시
    disagree_info = result.get("disagreements", []) or []
    disagree_container.markdown("### 상이 의견(위원별 확인 필요)")

    # 위원별 index → reason 매핑
    idx_to_reason = {}
    for item in disagree_info:
        try:
            idx = int(item.get("reviewer_index"))
        except (TypeError, ValueError):
            continue
        reason = item.get("reason", "").strip()
        name = item.get("reviewer_name") or (reviewer_names[idx - 1] if 1 <= idx <= NUM_REVIEWERS else f"위원{idx}")
        idx_to_reason[idx] = (name, reason)

    if not idx_to_reason:
        disagree_container.success("상이 의견으로 표시된 내용이 없습니다.")
    else:
        for idx, (name, reason) in idx_to_reason.items():
            disagree_container.error(f"위원 {idx} ({name}) 상이 의견: {reason}")

else:
    # 아직 버튼 안 눌렀으면 빈 textarea만 보여주기
    summary_area.text_area(
        "종합의견 초안(자동 생성)",
        value="",
        height=320,
    )

