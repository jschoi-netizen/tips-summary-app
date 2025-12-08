import json
import re
import io

import streamlit as st
from openai import OpenAI

# OpenAI 클라이언트 (OPENAI_API_KEY는 Streamlit Secrets에 있다고 가정)
client = OpenAI()

st.set_page_config(
    page_title="TIPS 선정평가 종합의견 도우미(평가간사용)",
    layout="wide",
)

# ==============================
#  공통 스타일 (CSS)
# ==============================
st.markdown(
    """
<style>
/* 전체 배경 & 폰트 */
html, body, [class*="css"]  {
    font-family: -apple-system, BlinkMacSystemFont, "Noto Sans KR", sans-serif;
}

/* 메인 영역 배경 */
.main {
    background-color: #f5f7fb;
}

/* 상단 타이틀 */
.app-title {
    font-size: 30px;
    font-weight: 800;
    letter-spacing: -0.03em;
    margin-bottom: 0.2rem;
}

.app-subtitle {
    font-size: 14px;
    color: #6b7280;
}

/* 카드 공통 */
.tips-card {
    padding: 1.2rem 1.4rem;
    border-radius: 0.9rem;
    background-color: #ffffff;
    box-shadow: 0 4px 12px rgba(15, 23, 42, 0.06);
    margin-bottom: 1.2rem;
}

/* 섹션 제목 */
.section-title {
    font-size: 18px;
    font-weight: 700;
    margin-bottom: 0.5rem;
}

/* 작은 뱃지 */
.badge {
    display: inline-block;
    padding: 0.15rem 0.55rem;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
    margin-right: 0.25rem;
}
.badge-red {
    background-color: #fee2e2;
    color: #b91c1c;
}
.badge-blue {
    background-color: #dbeafe;
    color: #1d4ed8;
}
.badge-green {
    background-color: #dcfce7;
    color: #15803d;
}

/* 메인 버튼 스타일 약간 강조 */
.stButton > button {
    border-radius: 999px;
    padding: 0.55rem 1.5rem;
    font-weight: 600;
}

/* 텍스트에어리어 살짝 둥글게 */
textarea {
    border-radius: 0.6rem !important;
}

/* 상이의견 에러 박스 여백 */
.block-container .element-container:has(.disagree-box) {
    margin-top: 0.3rem;
}

/* 다운로드 버튼 */
.stDownloadButton > button {
    border-radius: 999px;
}
</style>
""",
    unsafe_allow_html=True,
)

# ==============================
#  상단 제목 / 설명
# ==============================
st.markdown(
    """
<div class="app-title">TIPS 선정평가 종합의견 도우미(평가간사용)</div>
<div class="app-subtitle">
위험한 ‘창작’ 없이, 평가위원 의견을 그대로 정리·취합해서 종합의견 초안을 만드는 도구입니다.
</div>
""",
    unsafe_allow_html=True,
)

st.write("")
top_col1, top_col2 = st.columns([2.2, 1])

with top_col1:
    st.markdown(
        """
<div class="tips-card">
  <div class="section-title">사용 방법</div>
  <ul style="font-size:13px; color:#4b5563; padding-left:1.1rem; margin-bottom:0.3rem;">
    <li>각 위원의 <b>혼합된 전체 의견</b>을 한 칸에 붙여넣어 주세요.<br/>
        (기술성/사업성/연구개발비 조정/기타사항이 섞여 있어도 됩니다.)</li>
    <li><span class="badge badge-red">🔴 종합의견 생성</span> 버튼을 누르면 아래 5개 항목으로 자동 분류·취합됩니다.</li>
  </ul>
  <div style="font-size:13px; color:#6b7280; margin-top:0.4rem;">
    1) 기술성 종합의견 · 2) 사업성 종합의견 · 3) 협약 시 보완사항 · 4) 연구개발비 조정의견 · 5) 기타 의견
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

with top_col2:
    st.markdown(
        """
<div class="tips-card">
  <div style="font-size:13px; font-weight:600; margin-bottom:0.3rem;">프롬프트 원칙</div>
  <ul style="font-size:12px; color:#4b5563; padding-left:1.1rem; margin-bottom:0.4rem;">
    <li>원문에 없는 내용은 <b>절대로</b> 만들지 않음</li>
    <li>중요한 bullet은 삭제하지 않고 그대로 유지</li>
    <li>동일 취지 bullet만 조심스럽게 병합</li>
  </ul>
  <div style="font-size:12px; color:#9ca3af;">
    ※ 종합의견은 간사가 최종 검토 후 사용해야 합니다.
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

# ==============================
#  위원 설정 (이름 + 의견 입력)
# ==============================
st.markdown('<div class="section-title" style="margin-top:0.3rem;">① 위원별 평가 의견 입력</div>', unsafe_allow_html=True)

input_card = st.container()
with input_card:
    st.markdown('<div class="tips-card">', unsafe_allow_html=True)

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

    st.markdown("</div>", unsafe_allow_html=True)

# ------------------------------
# 종합의견 생성 버튼
# ------------------------------
st.write("")
btn_col1, btn_col2 = st.columns([1, 3])
with btn_col1:
    generate = st.button("🔴 종합의견 생성", type="primary")
with btn_col2:
    st.caption("버튼 클릭 시 OpenAI API를 호출하여 종합의견 초안을 생성합니다.")

# 종합의견 결과 표시 영역
st.markdown('<div class="section-title" style="margin-top:0.6rem;">② 종합의견 초안</div>', unsafe_allow_html=True)
summary_card = st.container()
summary_area = summary_card.empty()

# 상이 의견 표시 영역
st.markdown('<div class="section-title" style="margin-top:0.6rem;">③ 상이 의견 알림</div>', unsafe_allow_html=True)
disagree_container = st.container()

# 세션에 마지막 종합의견 저장용
if "last_summary_text" not in st.session_state:
    st.session_state["last_summary_text"] = ""

# ==============================
#  GPT 호출 & JSON 파싱 함수
# ==============================
def call_openai_for_summary(names, opinions):
    """위원별 의견을 입력받아 OpenAI로 종합의견 JSON을 생성."""
    joined = [op for op in opinions if op]
    if not joined:
        return None

    # 위원별 원문 블록
    reviewers_block = ""
    for idx, (nm, op) in enumerate(zip(names, opinions), start=1):
        if not op:
            continue
        reviewers_block += f"[위원 {idx}: {nm}]\n{op}\n\n"

    system_prompt = """
당신은 한국의 TIPS R&D 선정평가 간사를 돕는 **아주 보수적인** 도우미입니다.
당신의 목표는 "창작"이 아니라, 위원들이 쓴 문장을 **거의 그대로 정리·분류**하는 것입니다.

아래 '위원별 의견'을 참고하여,
기술성 / 사업성 / 협약시 보완사항 / 연구개발비 조정의견 / 기타 의견을
bullet 형식으로 **정리만** 하세요.

### 0. 절대적인 원칙 (아주 중요)

- 원문에 **없는 문장을 새로 만들지 마십시오.**  
  - 예: 어떤 위원이 연구개발비에 대해 아무 말도 안 했으면,
    그 위원에 대해 연구개발비 관련 bullet을 쓰지 마십시오.
- 원문에 있는 중요한 bullet(삭제/불허, 조건부 허용, 성능지표 보완 등)을
  **삭제하거나 바꾸지 마십시오.**
- 오타 교정, 조사 수정, 문장 연결 정도의 가벼운 다듬기만 허용됩니다.
  문장의 의미는 절대 바꾸지 마십시오.
- 애매하면 "추가로 쓰지 않는다"를 선택하십시오.  
  (모르면 쓰지 말기)

---

### 1단계: 문장 분해 & 섹션 분류 (머릿속에서만)

각 위원별 텍스트를 다음처럼 머릿속에서 처리한다고 생각하십시오.

1. 문장을 잘라서 **한 가지 요지**만 담은 단위 bullet으로 나눕니다.
2. 각 bullet을 다음 섹션 중 하나에 분류합니다.
   - tech : 기술성 (성과지표, 기술적 파급효과, 개발 필요성, 기술적 리스크 등)
   - biz : 사업성 (시장성, 글로벌 진출 가능성, 경제적 파급효과, 일자리 창출 등)
   - improve : 협약 시 보완사항 (성과지표 보완, 추진체계·일정 보완 등)
   - budget : 연구개발비 조정의견 (허용/불허, 조정 필요 항목 등)
   - other : 기타 의견 (위탁연구개발기관, 특이사항 등)
3. 어느 섹션에도 명확히 안 맞으면 other에 넣습니다.
4. 어떤 위원의 텍스트 안에 '예산', '연구개발비', '장비', '인건비' 등
   **예산/비용 관련 표현이 전혀 없다면**, 그 위원은 budget 섹션에 아무 것도
   남기지 마십시오.

---

### 2단계: 중복 내용 정리 (요약 X, 병합 O)

- 여러 위원의 bullet이 **완전히 같은 취지**일 경우에만
  → 하나의 bullet로 합쳐도 됩니다.
- 이때도, 여러 bullet에 등장한 **핵심 명사, 수치, 조건, 핵심 표현**은
  모두 대표 bullet 안에 포함시켜야 합니다.
- 취지가 조금이라도 다르거나 강조점이 다르다면,  
  → **절대로 합치지 말고 각각 개별 bullet로 남겨두십시오.**
- 중요한 내용이 생략되는 요약은 허용되지 않습니다.

---

### 3단계: 상이 의견(disagreements) 판단

- 이 배열은 **선택 사항**이며, 매우 보수적으로 채워야 합니다.
- 다음 조건을 모두 만족할 때만 항목을 추가합니다.
  1) 같은 주제(예: 연구개발비, 사업성)에 대해  
     다수의 위원은 A 의견인데, 특정 위원 하나만 B 의견으로 **정반대**를 주장함.
  2) 그 내용이 텍스트에서 **명확하게** 드러남. 추측 금지.
- 단순히 "강조하는 정도" 차이, "추가 코멘트" 차이는 상이 의견이 아닙니다.
- 특히, 어떤 위원이 연구개발비에 대해 전혀 언급하지 않았다면  
  → 그 위원에 대해 "연구개발비 전면 불허 의견 제시" 같은
    상이 의견을 **절대로 쓰지 마십시오.**
- 확실하지 않으면 `disagreements: []` 로 두는 것이 정답입니다.

---

### 4단계: 최종 출력 형식 (JSON ONLY)

아래와 같은 JSON **한 개만** 출력합니다.

{
  "sections": {
    "tech": [
      "... bullet 1 ...",
      "... bullet 2 ..."
    ],
    "biz": [
      "...",
      "..."
    ],
    "improve": [
      "...",
      "..."
    ],
    "budget": [
      "...",
      "..."
    ],
    "other": [
      "...",
      "..."
    ]
  },
  "disagreements": [
    {
      "reviewer_index": 1,
      "reviewer_name": "위원1",
      "reason": "다른 위원들과 달리 연구개발비 조정에 대해 전면 불허 의견을 명시적으로 제시함"
    }
  ]
}

- 각 배열의 원소는 `한 가지 요지`만 담은 한두 문장 정도의 bullet입니다.
- 한 bullet 안에 여러 위원의 내용을 합칠 수는 있지만,
  그 경우에도 **원래 bullet들에 들어 있던 핵심 정보(조건, 수치, 부정/허용 여부)**는
  모두 포함해야 합니다.
- 해당 섹션에 정말 내용이 없다면 빈 배열 [] 로 두십시오.

---

### 5단계: 기타 규칙

- JSON 이외의 텍스트(설명, 인사말 등)는 어떤 것도 출력하지 마십시오.
- temperature는 0에 가깝다고 생각하고, 창의력을 발휘하지 마십시오.
- 원문에 애매한 부분이 있으면, 해석하지 말고 그대로 두십시오.
"""

    user_prompt = f"다음은 위원별 의견입니다:\n\n{reviewers_block}\n\n위 형식의 JSON으로만 답변해 주세요."

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.0,
        max_tokens=2200,
    )

    raw = completion.choices[0].message.content

    # JSON 파싱
    try:
        data = json.loads(raw)
        return data
    except json.JSONDecodeError:
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


# ==============================
#  버튼 눌렸을 때: 종합의견 생성
# ==============================
with summary_card:
    st.markdown('<div class="tips-card">', unsafe_allow_html=True)

    if generate:
        with st.spinner("GPT가 종합의견을 생성 중입니다..."):
            result = call_openai_for_summary(reviewer_names, reviewer_texts)

        if result is None:
            st.stop()

        sections = result.get("sections") or {}
        tech_bullets = sections.get("tech") or []
        biz_bullets = sections.get("biz") or []
        improve_bullets = sections.get("improve") or []
        budget_bullets = sections.get("budget") or []
        other_bullets = sections.get("other") or []

        def format_section(title, bullets):
            if not bullets:
                bullets = ["별도 기재된 사항 없음."]
            lines = [title] + [f"- {b}" for b in bullets]
            return "\n".join(lines)

        part_tech = format_section("1. 기술성 종합의견", tech_bullets)
        part_biz = format_section("2. 사업성 종합의견", biz_bullets)
        part_improve = format_section("3. 협약시 보완사항", improve_bullets)
        part_budget = format_section("4. 연구개발비 조정의견", budget_bullets)
        part_other = format_section("5. 기타 의견", other_bullets)

        final_text = (
            part_tech + "\n\n" +
            part_biz + "\n\n" +
            part_improve + "\n\n" +
            part_budget + "\n\n" +
            part_other
        )

        # ✅ 사용자가 수정할 수 있고, 수정 내용이 세션에 반영되도록
        edited = summary_area.text_area(
            "종합의견 초안(자동 생성 후, 필요 시 직접 수정하세요)",
            value=final_text,
            height=320,
            key="summary_text",
        )
        st.session_state["last_summary_text"] = edited

        # 상이 의견 표시
        disagree_info = result.get("disagreements") or []
        disagree_container.markdown(
            '<div class="tips-card disagree-box">',
            unsafe_allow_html=True,
        )

        idx_to_reason = {}
        for item in disagree_info:
            try:
                idx = int(item.get("reviewer_index"))
            except (TypeError, ValueError):
                continue
            reason = (item.get("reason") or "").strip()
            if not reason:
                continue
            if 1 <= idx <= 5:
                name = item.get("reviewer_name") or reviewer_names[idx - 1]
            else:
                name = item.get("reviewer_name") or f"위원{idx}"
            idx_to_reason[idx] = (name, reason)

        if not idx_to_reason:
            disagree_container.success("상이 의견으로 표시된 내용이 없습니다.")
        else:
            for idx, (name, reason) in idx_to_reason.items():
                disagree_container.error(f"위원 {idx} ({name}) 상이 의견: {reason}")

        st.markdown("</div>", unsafe_allow_html=True)

    else:
        # 아직 버튼 안 눌렀을 때 또는 이미 생성된 후 다시 수정하는 경우
        existing = st.session_state.get("last_summary_text", "")
        edited = summary_area.text_area(
            "종합의견 초안(자동 생성 후, 필요 시 직접 수정하세요)",
            value=existing,
            height=320,
            key="summary_text",
        )
        st.session_state["last_summary_text"] = edited

    st.markdown("</div>", unsafe_allow_html=True)

# ==============================
#  TXT 다운로드 버튼
# ==============================
st.markdown('<div class="section-title" style="margin-top:0.6rem;">④ TXT로 내보내기</div>', unsafe_allow_html=True)
download_card = st.container()
with download_card:
    st.markdown('<div class="tips-card">', unsafe_allow_html=True)
    if st.session_state.get("last_summary_text"):
        st.download_button(
            label="📄 TXT 파일 다운로드",
            data=st.session_state["last_summary_text"],
            file_name="tips_summary.txt",
            mime="text/plain",
        )
        st.caption("※ IRIS 시스템 등에 붙여넣기 전에 한 번 더 눈으로 검토해 주세요.")
    else:
        st.info("먼저 위에서 **종합의견 생성**을 눌러 종합의견을 만든 뒤 다운로드할 수 있습니다.")
    st.markdown("</div>", unsafe_allow_html=True)

