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
        <img class="tips-logo" src="https://i.imgur.com/YNn7dYk.png">
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
            <li>중요한 문장은 삭제하지 않음</li>
            <li>동일 취지만 조심스럽게 병합</li>
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
#  GPT 처리 함수 (1) — 종합의견 생성
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
#  GPT 처리 함수 (2) — 위원별 오탈자·이상 의견 체크
#   👉 종합의견 로직과 완전히 분리, 참고용 리포트만 생성
# ============================================================

def check_typos_and_weird_points(names, opinions):
    """위원별 오탈자/이상 의견/누락 섹션을 점검하는 리포트용 함수."""

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

아래 위원별 원문을 보고, 각 위원에 대해 다음만 점검합니다:
1) 오탈자 의심 / 문장이 비문처럼 보이는 부분 (원문 일부 그대로 인용)
2) 같은 말을 과하게 반복하거나, 문단 구조가 이상한 부분
3) '기술성/사업성/협약 시 보완사항/연구개발비 조정의견/기타 의견' 중
   전혀 언급이 없는 영역이 있는지 여부 (있으면 어떤 영역이 비어 있는지)

⚠️ 매우 중요한 규칙
- 원문에 없는 내용을 새로 만들지 마세요.
- 특정 위원이 실제로 쓰지 않은 의견(예: 연구개발비 전면 불허 등)을 추측하면 안 됩니다.
- 확실하지 않으면 "모호하여 판단 어려움"이라고만 적으세요.
- 이 리포트는 참고용이며, 종합의견 내용에는 일절 영향을 주지 않습니다.

JSON ONLY 형식으로 출력하세요:

{
  "by_reviewer": [
    {
      "index": 1,
      "name": "위원1",
      "typos": [
        "예: '매칭의 정확도85%' → '매칭의 정확도 85%'"
      ],
      "weird_phrases": [
        "예: 문장이 너무 길어 의미 파악이 어려움: '...원문 일부...'"
      ],
      "missing_sections": [
        "연구개발비 조정의견 미언급",
        "협약 시 보완사항 미언급"
      ]
    }
  ]
}

각 배열은 필요 없으면 빈 배열 [] 로 두세요.
"""

    user_prompt = f"아래는 위원별 의견 원문입니다. 위 JSON 형식으로만 출력해 주세요.\n\n{reviewers_block}"

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.0,
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
                st.error("오탈자/이상 의견 JSON 파싱 실패\n" + raw)
                return None
        st.error("오탈자/이상 의견 JSON 분석 실패\n" + raw)
        return None


# ============================================================
#  세션 상태 초기화 (종합의견 텍스트)
# ============================================================

if "summary_editor" not in st.session_state:
    st.session_state["summary_editor"] = ""

# ============================================================
#  버튼 영역
# ============================================================

generate = st.button("🔴 종합의견 생성", type="primary")
check_btn = st.button("✏️ 위원별 오탈자·이상 의견 체크")

st.subheader("📌 종합의견 초안")
summary_area = st.empty()

# 오탈자/이상 의견 결과 표시용 컨테이너
check_container = st.container()

# ============================================================
#  버튼 클릭 시 GPT 요약 실행 (종합의견 생성)
# ============================================================

if generate:
    with st.spinner("종합의견 생성 중..."):
        result = call_openai_for_summary(reviewer_names, reviewer_texts)

    if result is None:
        st.stop()

    sections = result["sections"]

    def format_section(title, arr):
        if not arr:
            arr = ["별도 기재된 사항 없음."]
        bullets = "\n".join(f"- {x}" for x in arr)
        return f"{title}\n{bullets}"

    final_text = (
        format_section("1. 기술성 종합의견", sections.get("tech"))
        + "\n\n"
        + format_section("2. 사업성 종합의견", sections.get("biz"))
        + "\n\n"
        + format_section("3. 협약 시 보완사항", sections.get("improve"))
        + "\n\n"
        + format_section("4. 연구개발비 조정의견", sections.get("budget"))
        + "\n\n"
        + format_section("5. 기타 의견", sections.get("other"))
    )

    # 👉 새로 생성된 요약을 세션에 저장
    st.session_state["summary_editor"] = final_text

# 항상 현재 세션 상태(summary_editor)를 보여줌
summary_area.text_area(
    "종합의견 초안 (수정 가능)",
    key="summary_editor",
    height=350,
)

# ============================================================
#  버튼 클릭 시 오탈자/이상 의견 체크 (종합의견과 완전 분리)
# ============================================================

if check_btn:
    with st.spinner("위원별 오탈자·이상 의견을 점검 중입니다..."):
        report = check_typos_and_weird_points(reviewer_names, reviewer_texts)

    check_container.markdown("### ✏️ 위원별 오탈자·이상 의견 결과")

    if report is None:
        check_container.info("점검할 위원 의견이 없습니다. 먼저 위원 의견을 입력해 주세요.")
    else:
        by_rev = report.get("by_reviewer", [])
        any_issue = False

        for item in by_rev:
            idx = item.get("index")
            name = item.get("name") or (
                reviewer_names[idx - 1]
                if isinstance(idx, int) and 1 <= idx <= NUM_REVIEWERS
                else f"위원{idx}"
            )
            typos = item.get("typos") or []
            weirds = item.get("weird_phrases") or []
            miss = item.get("missing_sections") or []

            if not typos and not weirds and not miss:
                check_container.success(
                    f"위원 {idx} ({name}): 특별히 표시할 만한 오탈자·이상 의견이 감지되지 않았습니다."
                )
                continue

            any_issue = True
            check_container.markdown(f"**위원 {idx} ({name})**")

            if typos:
                check_container.markdown("- 오탈자 의심:")
                for t in typos:
                    check_container.markdown(f"  - {t}")

            if weirds:
                check_container.markdown("- 문장/표현이 어색하거나 과도하게 긴 부분:")
                for w in weirds:
                    check_container.markdown(f"  - {w}")

            if miss:
                check_container.markdown("- 언급이 없는 것으로 보이는 항목:")
                for m in miss:
                    check_container.markdown(f"  - {m}")

            check_container.markdown("---")

        if not any_issue:
            check_container.success("특별히 표시할 만한 오탈자·이상 의견이 감지되지 않았습니다.")

# ============================================================
#  TXT 다운로드 기능
# ============================================================

st.divider()
st.markdown("#### 📄 TXT 다운로드")

edited_text = st.session_state.get("summary_editor", "")

if edited_text.strip():
    st.download_button(
        label="TXT로 다운로드",
        data=edited_text,
        file_name="tips_summary.txt",
        mime="text/plain",
    )
else:
    st.info("먼저 종합의견을 생성하세요.")
