# ============================================================
#   TIPS 선정평가 종합의견 도우미(평가간사용) — FULL VERSION
#   전체 초기화 후 통째로 복붙하면 바로 동작하는 완성본
# ============================================================

import json
import re
import streamlit as st
from openai import OpenAI

# ---------------------------
# OpenAI Client
# ---------------------------
client = OpenAI()

# ---------------------------
# Streamlit 기본 설정
# ---------------------------
st.set_page_config(
    page_title="TIPS 선정평가 종합의견 도우미(평가간사용)",
    layout="wide",
)

# ---------------------------
# 상단 UI 스타일 넣기
# ---------------------------
st.markdown(
    """
    <style>
        .title-wrapper {
            display: flex;
            align-items: center;
            gap: 18px;
            margin-top: 4px;
        }

        .tips-logo {
            width: 60px;
            height: auto;
        }

        .main-title {
            font-size: 38px;
            font-weight: 800;
            color: #1a1a1a;
            line-height: 1.15;
            margin-bottom: 6px;
        }

        .subtitle-text {
            font-size: 15px;
            color: #555;
        }

        .divider-bar {
            width: 100%;
            height: 6px;
            background-color: #E5E5E5;
            border-radius: 3px;
            margin-top: 14px;
            margin-bottom: 18px;
        }

        .info-box {
            background: #F8F9FA;
            border: 1px solid #E2E2E2;
            padding: 16px 20px;
            border-radius: 8px;
            margin-bottom: 18px;
        }

        .info-title {
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 12px;
            color: #333;
        }

        ul {
            margin-top: 4px;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# ---------------------------
# 상단 로고 + 제목
# ---------------------------
st.markdown(
    """
    <div class="title-wrapper">
        <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/0/0a/TIPS_Program_Logo.png/512px-TIPS_Program_Logo.png" class="tips-logo">
        <div>
            <div class="main-title">TIPS 선정평가 종합의견 도우미(평가간사용)</div>
            <div class="subtitle-text">
                팁스 선정평가 시 평가위원 의견을 자동 분류·취합하여 종합의견 초안을 생성하는 간사 전용 도구입니다.
            </div>
        </div>
    </div>

    <div class="divider-bar"></div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------
# 사용 방법 안내
# ---------------------------
st.markdown(
    """
    <div class="info-box">
        <div class="info-title">사용 방법</div>
        <ul>
            <li>각 위원의 <b>전체 평가 의견</b>을 한 칸에 붙여넣어 주세요.</li>
            <li>(기술성/사업성/보완사항/연구개발비/기타가 섞여 있어도 됩니다.)</li>
            <li><b style="color:#d9534f;">🔴 ‘종합의견 생성’</b>을 누르면 5개 항목으로 자동 분류됩니다.</li>
        </ul>
        기술성 · 사업성 · 협약 시 보완사항 · 연구개발비 조정의견 · 기타 의견
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------
# 프롬프트 정책 안내
# ---------------------------
st.markdown(
    """
    <div class="info-box">
        <div class="info-title">프롬프트 원칙</div>
        <ul>
            <li>원문에 없는 내용을 절대 생성하지 않음</li>
            <li>중요 문장은 삭제하지 않음</li>
            <li>동일 취지의 문장만 조심스럽게 병합</li>
            <li>최종 검토는 반드시 간사가 진행</li>
        </ul>
    </div>
    """,
    unsafe_allow_html=True,
)

# ============================================================
#   본 기능 — 위원 이름 입력 + 의견 입력
# ============================================================

NUM_REVIEWERS = 5
cols = st.columns(NUM_REVIEWERS)

reviewer_names = []
reviewer_texts = []

for i in range(NUM_REVIEWERS):
    with cols[i]:
        name = st.text_input(f"위원 {i+1} 이름", value=f"위원{i+1}", key=f"name_{i}")
        reviewer_names.append(name)

        txt = st.text_area(
            f"{name} 의견 입력",
            key=f"text_{i}",
            height=260,
            placeholder="위원의 전체 의견을 복붙해 주세요.",
        )
        reviewer_texts.append(txt.strip())


# ============================================================
#  GPT 처리 함수
# ============================================================

def call_openai_for_summary(names, opinions):
    """GPT에 종합의견 생성을 요청하고 JSON 반환."""

    joined = [o for o in opinions if o]
    if not joined:
        return None

    reviewers_block = ""
    for idx, (nm, txt) in enumerate(zip(names, opinions), start=1):
        if not txt:
            continue
        reviewers_block += f"[위원 {idx}: {nm}]\n{txt}\n\n"

    system_prompt = """
당신은 한국 TIPS 평가 간사를 돕는 AI입니다.
위원들의 원문을 기반으로 다음 5개 항목으로 정리하세요:

1) 기술성 종합의견
2) 사업성 종합의견
3) 협약 시 보완사항
4) 연구개발비 조정의견
5) 기타 의견

※ 지켜야 할 규칙
- 원문 bullet은 가능한 그대로 유지
- 중요한 지적·보완 요청은 절대 삭제 금지
- 비슷한 취지는 병합 가능
- 원문에 없는 내용 / 새로운 사실 생성 금지
- 상이 의견은 실제 존재할 때만 기록

출력은 MUST JSON ONLY:

{
 "sections":{
    "tech": ["...", "..."],
    "biz": ["...", "..."],
    "improve": ["..."],
    "budget": ["..."],
    "other": ["..."]
 },
 "disagreements":[
    {"reviewer_index":3,"reviewer_name":"위원3","reason":"..."}
 ]
}
"""

    user_prompt = f"아래는 위원들의 의견입니다:\n\n{reviewers_block}\n\n위 JSON 형식으로만 출력하세요."

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.15,
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt},
        ],
    )

    raw = completion.choices[0].message.content

    try:
        return json.loads(raw)
    except:
        match = re.search(r"\{.*\}", raw, re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except:
                st.error("JSON 파싱 실패\n" + raw)
                return None
        st.error("JSON 분석 실패\n" + raw)
        return None


# ============================================================
#  종합의견 생성 버튼
# ==============================을 생성하세요.")
