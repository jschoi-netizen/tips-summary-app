import os
import re
from collections import defaultdict
import streamlit as st

# -----------------------------
# OpenAI 클라이언트
# -----------------------------
try:
    from openai import OpenAI
except Exception:
    # Streamlit Cloud에서 패키지 설치 전 초기 로드 대비
    OpenAI = None

st.set_page_config(page_title="TIPS 선정평가 종합의견 도우미(평가간사용)", layout="wide")

# =========================================
# 설정 / 상수
# =========================================
SECTIONS = ["기술성", "사업성", "연구개발비 조정", "기타사항"]
TITLE = "TIPS 선정평가 종합의견 도우미(평가간사용)"

API_KEY = st.secrets.get("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))

# 모델은 최신이 있으면 그걸 쓰고, 없으면 gpt-4o-mini를 권장
CHAT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# OpenAI Client 준비
client = None
if API_KEY and OpenAI is not None:
    client = OpenAI(api_key=API_KEY)

# =========================================
# 사이드바 - 설정
# =========================================
with st.sidebar:
    st.header("설정")
    DEBUG = st.checkbox("🔧 진단 모드(원인 로그 보기)", value=False)

    num_reviewers = st.number_input("평가위원 수", 1, 5, 5, 1)
    reviewer_names = []
    for i in range(num_reviewers):
        nm = st.text_input(f"위원{i+1} 이름", f"위원{i+1}")
        reviewer_names.append(nm.strip() or f"위원{i+1}")

    st.markdown("---")
    st.subheader("필수 기재 내용")
    st.caption("한 줄에 하나, 의미적으로 포함되었는지 검토합니다.")
    required_raw = st.text_area("필수 기재 내용(한 줄에 하나)", value="평가단 승인사항\n협약 시 보완사항", height=120)
    required_lines = [ln.strip() for ln in required_raw.splitlines() if ln.strip()]

    st.markdown("---")
    if not API_KEY:
        st.warning("`OPENAI_API_KEY`가 Streamlit Secrets에 저장되어 있지 않습니다.")
    else:
        st.caption("🔒 OPENAI_API_KEY는 Streamlit Secrets로부터 안전하게 주입됩니다.")

# =========================================
# 타이틀
# =========================================
st.title(TITLE)
st.caption("위원별 의견을 입력하고, [종합의견 생성]을 눌러 취합/검토 결과를 확인하세요.")

# =========================================
# 입력 폼 - 탭별/위원별
# =========================================
tab_objs = st.tabs(SECTIONS)

# 섹션별, 위원별 텍스트 입력을 담는 dict
section_texts = {s: [] for s in SECTIONS}

for tab, section in zip(tab_objs, SECTIONS):
    with tab:
        cols = st.columns(num_reviewers)
        for j, c in enumerate(cols):
            with c:
                txt = st.text_area(
                    f"{reviewer_names[j]} ({section})",
                    placeholder=f"{section} 의견을 입력하세요.",
                    key=f"{section}_{j}",
                    height=120
                )
                section_texts[section].append(txt or "")

# =========================================
# 요약 / 검증에 사용하는 System Prompt
# =========================================
SYSTEM_PROMPT = """당신은 정부 R&D 사업 선정평가의 간사 보조원입니다.
입력되는 '위원별 의견'을 보고 아래 JSON 형식으로만 답하세요.

출력 형식(JSON):
{
  "section": "<섹션명>",
  "majority_label": "긍정|부정|중립",
  "reviewers": [{"name": "<이름>", "label": "긍정|부정|중립"}],
  "summary": "<간사에게 바로 붙여넣기 좋게, 문장형으로 정리>",
  "dissent_reviewers": ["상이의견 위원명", ...],
  "concerns": ["필수내용/유의사항이 발견되면 bullet로", ...]
}

label 규칙:
- '긍정'은 호의적 평가, '부정'은 부정적 평가, '중립'은 판단곤란/혼재 등
- 다수결로 majority_label을 정하되, 소수의견은 dissent_reviewers로 분리

요약 규칙:
- 위원 간 합의된 내용 중심으로 3~5문장, 간결/명료/문어체
- 조사/어미 일관성 유지, 문장 호응 자연스럽게
- 명시적 상이의견은 요약 본문에 넣지 않고, dissent_reviewers로만 표기
"""

# =========================================
# GPT JSON 호출 + 예외 표시
# =========================================
def call_gpt_json(system_prompt: str, user_prompt: str, max_tokens: int = 900) -> dict:
    """JSON 강제 / 예외 표시 / 폴백 반환"""
    try:
        if not client:
            raise RuntimeError("OpenAI Client 가 초기화되지 않았습니다. (API_KEY 미설정)")

        resp = client.chat.completions.create(
            model=CHAT_MODEL,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
        )

        import json
        content = resp.choices[0].message.content
        if DEBUG:
            with st.expander("🧪 GPT Raw Response(JSON 문자열)"):
                st.code(content, language="json")
        return json.loads(content)
    except Exception as e:
        st.error("❌ GPT 호출 중 오류가 발생했습니다. 상세를 아래에서 확인하세요.")
        st.exception(e)
        return {
            "section": "",
            "majority_label": "중립",
            "reviewers": [],
            "summary": "(오류로 인해 요약 생성 실패 — 입력 원문을 확인하세요.)",
            "dissent_reviewers": [],
            "concerns": []
        }

# =========================================
# 의미 포함 여부 검사 (필수 문구)
# =========================================
def semantic_contains(required_phrase: str, texts: list[str]) -> bool:
    """
    요구문구가 의미적으로 들어있는지 GPT로 간단히 판정.
    여러 텍스트를 합쳐 한 번에 판정해 비용/속도를 줄임.
    """
    try:
        joined = "\n".join([t for t in texts if t])
        if not joined.strip():
            return False

        sys = "너는 의미 포함 여부만 판정하는 심사 보조원이다. 반드시 JSON {\"contains\": true|false} 로만 답하라."
        user = f"""[요구문구]
{required_phrase}

[검토대상 텍스트]
{joined}

위 요구문구가 의미적으로 포함되어 있으면 true, 아니면 false. 동의어·말바꿈 포함."""
        data = call_gpt_json(sys, user, max_tokens=200)
        return bool(data.get("contains", False))
    except Exception:
        return False

# =========================================
# 종합 생성 로직 (강건성/예외내성)
# =========================================
def generate_all():
    """
    섹션별 의미 요약(JSON) + 상이의견 + 필수기재 의미검증 + 개별 칸 경고 맵 저장
    ▶ 오류가 있어도 섹션별로 최대한 결과를 채워 넣도록 폴백 처리
    """
    out_boxes = {}
    dissent_msgs = []
    missing_msgs = []
    dissent_map = {k: set() for k in SECTIONS}

    for section, opinions in section_texts.items():
        try:
            pairs = [(nm, (tx or "").strip()) for nm, tx in zip(reviewer_names, opinions) if (tx or "").strip()]
            if not pairs:
                out_boxes[section] = "(의견 입력 없음)"
                continue

            joined = "\n".join([f"- {nm}: {tx}" for nm, tx in pairs])
            user = f"[섹션] {section}\n[위원별 의견]\n{joined}"

            data = call_gpt_json(SYSTEM_PROMPT, user, max_tokens=900)

            summary = (data.get("summary") or "").strip()
            if not summary:
                summary = f"{section} 의견 요약 실패 — 주요 의견:\n" + "\n".join(
                    [f"- {nm}: {tx}" for nm, tx in pairs[:3]]
                )
            out_boxes[section] = summary

            # 상이의견 매핑
            for nm in data.get("dissent_reviewers", []):
                if nm:
                    dissent_map[section].add(nm)
            if data.get("dissent_reviewers"):
                dissent_msgs.append(
                    f"섹션 [{section}] 상이의견: {', '.join([n for n in data['dissent_reviewers'] if n])}"
                )

            # 필수 기재 의미 포함 검사 (섹션 단위)
            flat_text = " ".join([tx for _, tx in pairs])
            miss = []
            for req in required_lines:
                if req.strip() and not semantic_contains(req, [flat_text]):
                    miss.append(req.strip())
            if miss:
                missing_msgs.append(f"섹션 [{section}] 필수 기재 누락: {', '.join(miss)}")

        except Exception as e:
            out_boxes[section] = f"(섹션 처리 중 오류) {e}"
            if DEBUG:
                st.exception(e)

    # 세션 저장
    st.session_state.result_boxes = out_boxes
    st.session_state.warnings_dissent = dissent_msgs
    st.session_state.missing_required = missing_msgs
    st.session_state.dissent_map = dissent_map

# =========================================
# 버튼 영역
# =========================================
left, mid, right = st.columns([2, 1, 1])
with left:
    gen = st.button("종합의견 생성", use_container_width=True, type="primary")
with mid:
    shrink = st.button("요약 더 줄이기", use_container_width=True, disabled=False)
with right:
    # TXT 다운로드 버튼은 아래 결과 박스가 채워진 뒤 표시
    pass

# =========================================
# 버튼 동작
# =========================================
if gen:
    if not API_KEY:
        st.error("OPENAI_API_KEY 가 설정되지 않았습니다. Streamlit Secrets에 추가하고 저장 후 새로고침 해주세요.")
    else:
        with st.spinner("의미 요약/검증 중..."):
            generate_all()
        st.success("✅ 종합의견 생성이 완료되었습니다.")

if shrink and st.session_state.get("result_boxes"):
    # 간단 축약: 각 섹션 요약을 '좀 더 간결히'로 재요청
    try:
        new_boxes = {}
        for section, text in st.session_state["result_boxes"].items():
            if not text or text.startswith("("):
                new_boxes[section] = text
                continue
            sys = "너는 글을 간결하고 핵심만 남기되 문장 호응은 자연스럽게 유지하는 편집자다."
            user = f"[섹션] {section}\n아래 문단을 더 짧고 명료하게 다듬어라:\n{text}"
            data = call_gpt_json(sys, user, max_tokens=400)
            # 편의상 data['summary'] 대신 content 전체를 요약으로 취급
            new_boxes[section] = data.get("summary") or data.get("content") or text
        st.session_state.result_boxes = new_boxes
        st.success("✂️ 요약을 더 간결히 정리했습니다.")
    except Exception as e:
        st.error("요약 축약 중 오류가 발생했습니다.")
        if DEBUG:
            st.exception(e)

# =========================================
# 결과 렌더 (종합의견 초안)
# =========================================
st.markdown("### ✅ 종합의견 초안")
result_boxes = st.session_state.get("result_boxes", {s: "" for s in SECTIONS})

with st.container(border=True):
    for section in SECTIONS:
        st.markdown(f"**{section}**")
        st.text_area(
            f"{section}-out",
            value=result_boxes.get(section, ""),
            height=120,
            label_visibility="collapsed",
            key=f"out_{section}"
        )

# 경고/알림
warn_cols = st.columns(2)
with warn_cols[0]:
    # 상이의견
    dissent_msgs = st.session_state.get("warnings_dissent", [])
    if dissent_msgs:
        for msg in dissent_msgs:
            st.error(f"⚠️ {msg}")
with warn_cols[1]:
    # 필수 누락
    missing_msgs = st.session_state.get("missing_required", [])
    if missing_msgs:
        for msg in missing_msgs:
            st.error(f"❗ {msg}")

# 개별 칸 옆 빨간 표시 (상이의견)
dissent_map = st.session_state.get("dissent_map", {s: set() for s in SECTIONS})
if any(dissent_map.values()):
    st.markdown("---")
    st.markdown("#### 🔴 상이의견 표시")
    for section in SECTIONS:
        ds = dissent_map.get(section, set())
        if ds:
            st.markdown(f"- **{section}**: {', '.join(ds)}")

# 바이트 수 / TXT 다운로드
concat_text = "\n\n".join([f"[{sec}]\n{result_boxes.get(sec, '')}" for sec in SECTIONS]).strip()
byte_len = len(concat_text.encode("utf-8"))
row1, row2 = st.columns([1, 3])
with row1:
    st.caption(f"글자수(바이트): {byte_len} / 4000")
with row2:
    st.download_button(
        "TXT로 다운로드",
        data=concat_text or "결과가 없습니다.",
        file_name="종합의견_초안.txt",
        mime="text/plain",
        use_container_width=True
    )

