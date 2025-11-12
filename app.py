import os
import re
from collections import defaultdict
import streamlit as st

# -----------------------------
# OpenAI 클라이언트(Optional)
# -----------------------------
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

st.set_page_config(page_title="TIPS 선정평가 종합의견 도우미(평가간사용)", layout="wide")

# =========================================
# 기본 상수/초기 상태
# =========================================
SECTIONS = ["기술성", "사업성", "연구개발비 조정", "기타사항"]
TITLE = "TIPS 선정평가 종합의견 도우미(평가간사용)"

API_KEY = st.secrets.get("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))
CHAT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

client = None
if API_KEY and OpenAI is not None:
    client = OpenAI(api_key=API_KEY)

# 결과·경고 세션키 초기화
st.session_state.setdefault("result_boxes", {})         # 섹션별 요약 텍스트
st.session_state.setdefault("warnings_dissent", [])     # 상이의견 경고(문장)
st.session_state.setdefault("missing_required", [])     # 필수문구 누락(문장)
st.session_state.setdefault("dissent_map", {s: set() for s in SECTIONS})  # 섹션별 상이의견 위원명 집합

# =========================================
# 사이드바
# =========================================
with st.sidebar:
    st.header("설정")
    DEBUG = st.checkbox("🔧 진단 모드(원인 로그 보기)", value=False)

    num_reviewers = st.number_input("평가위원 수", 1, 5, 5, 1)
    reviewer_names = []
    for i in range(num_reviewers):
        nm = st.text_input(f"위원{i+1} 이름", f"위원{i+1}")
        reviewer_names.append((nm or f"위원{i+1}").strip())

    st.markdown("---")
    st.subheader("필수 기재 내용")
    st.caption("한 줄에 하나, 의미적으로 포함되었는지 검토합니다.")
    required_raw = st.text_area("필수 기재 내용(한 줄에 하나)", value="평가단 승인사항\n협약 시 보완사항", height=110)
    required_lines = [ln.strip() for ln in required_raw.splitlines() if ln.strip()]

    st.markdown("---")
    if not API_KEY:
        st.warning("`OPENAI_API_KEY`가 Streamlit Secrets에 저장되어 있지 않습니다. (AI 요약 없이도 기본 화면은 동작합니다)")
    else:
        st.caption("🔒 OPENAI_API_KEY는 Streamlit Secrets로부터 안전하게 주입됩니다.")

# =========================================
# 타이틀
# =========================================
st.title(TITLE)
st.caption("위원별 의견을 입력하고 [종합의견 생성]을 누르면, 하단 ‘종합의견 초안’에 즉시 취합·요약 결과가 표시됩니다.")

# =========================================
# 입력 탭(UI)
# =========================================
tab_objs = st.tabs(SECTIONS)

# 사용자가 입력한 텍스트들
section_texts: dict[str, list[str]] = {s: [] for s in SECTIONS}

for tab, section in zip(tab_objs, SECTIONS):
    with tab:
        cols = st.columns(num_reviewers)
        ds_names = st.session_state.get("dissent_map", {}).get(section, set())
        for j, c in enumerate(cols):
            with c:
                txt = st.text_area(
                    f"{reviewer_names[j]} ({section})",
                    placeholder=f"{section} 의견을 입력하세요.",
                    key=f"{section}_{j}",
                    height=120
                )
                section_texts[section].append(txt or "")
                # 상이의견이면 빨간라벨
                if reviewer_names[j] in ds_names:
                    st.markdown(
                        "<div style='color:#d32f2f; font-weight:600; margin-top:4px;'>상이의견(검토 필요)</div>",
                        unsafe_allow_html=True
                    )

# =========================================
# GPT 프롬프트
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
# 함수
# =========================================
def call_gpt_json(system_prompt: str, user_prompt: str, max_tokens: int = 900) -> dict:
    """JSON object 포맷으로만 응답 받도록 호출"""
    try:
        if not client:
            raise RuntimeError("OpenAI Client 미설정(API Key 없음)")
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
            with st.expander("🧪 GPT Raw Response(JSON)"):
                st.code(content, language="json")
        return json.loads(content)
    except Exception as e:
        if DEBUG:
            st.error("❌ GPT 호출 오류")
            st.exception(e)
        # 실패 시 빈 결과 반환(화면은 계속 동작)
        return {
            "section": "",
            "majority_label": "중립",
            "reviewers": [],
            "summary": "",
            "dissent_reviewers": [],
            "concerns": []
        }

def semantic_contains(required_phrase: str, texts: list[str]) -> bool:
    """필수문구가 의미적으로 포함되었는지(유사 의미) GPT로 판별"""
    try:
        joined = "\n".join([t for t in texts if t])
        if not joined.strip():
            return False
        sys = "너는 의미 포함 여부만 판정하는 심사 보조원이다. 반드시 JSON {\"contains\": true|false} 로만 답하라."
        user = f"[요구문구]\n{required_phrase}\n\n[검토대상 텍스트]\n{joined}"
        data = call_gpt_json(sys, user, max_tokens=200)
        return bool(data.get("contains", False))
    except Exception:
        return False

def generate_all() -> tuple[dict, list, list, dict]:
    """
    각 섹션별로:
      - 위원별 의견 → GPT 요약/다수결 판단
      - 상이의견 위원명 도출
      - 필수 문구 의미 포함 여부 점검
    반환: (boxes, dissent_msgs, missing_msgs, dissent_map)
    """
    out_boxes: dict[str, str] = {}
    dissent_msgs: list[str] = []
    missing_msgs: list[str] = []
    dissent_map: dict[str, set] = {k: set() for k in SECTIONS}

    for section, opinions in section_texts.items():
        # 空 입력이면 스킵
        pairs = [(nm, (tx or "").strip()) for nm, tx in zip(reviewer_names, opinions) if (tx or "").strip()]
        if not pairs:
            out_boxes[section] = ""
            continue

        # GPT 호출
        joined = "\n".join([f"- {nm}: {tx}" for nm, tx in pairs])
        user = f"[섹션] {section}\n[위원별 의견]\n{joined}"
        data = call_gpt_json(SYSTEM_PROMPT, user, max_tokens=900)

        summary = (data.get("summary") or "").strip()
        out_boxes[section] = summary

        # 상이의견
        for nm in data.get("dissent_reviewers", []) or []:
            if nm:
                dissent_map[section].add(nm)
        if data.get("dissent_reviewers"):
            dissent_msgs.append(f"섹션 [{section}] 상이의견: {', '.join(data['dissent_reviewers'])}")

        # 필수문구 의미 포함 체크(섹션 텍스트 기준)
        flat_text = " ".join([tx for _, tx in pairs])
        miss = []
        for req in required_lines:
            if req and not semantic_contains(req, [flat_text]):
                miss.append(req)
        if miss:
            missing_msgs.append(f"섹션 [{section}] 필수 기재 누락: {', '.join(miss)}")

    return out_boxes, dissent_msgs, missing_msgs, dissent_map

# =========================================
# 버튼
# =========================================
left, mid, right = st.columns([2, 1, 1])
with left:
    gen_clicked = st.button("종합의견 생성", use_container_width=True, type="primary")
with mid:
    shrink_clicked = st.button("요약 더 줄이기", use_container_width=True)

# =========================================
# 버튼 동작
# =========================================
if gen_clicked:
    # GPT 없이도 기본 로직은 돌아가게 해두었지만, 요약·의미검증은 API가 있어야 정상 동작
    with st.spinner("의미 요약/검증 중..."):
        boxes, ds_msgs, miss_msgs, ds_map = generate_all()

    st.session_state["result_boxes"] = boxes
    st.session_state["warnings_dissent"] = ds_msgs
    st.session_state["missing_required"] = miss_msgs
    st.session_state["dissent_map"] = ds_map

    st.success("✅ 종합의견 생성이 완료되었습니다. (아래 초안 영역에 표시됨)")

if shrink_clicked and st.session_state.get("result_boxes"):
    try:
        # ‘요약 더 줄이기’는 결과가 있을 때만
        new_boxes = {}
        for section, text in st.session_state["result_boxes"].items():
            if not text.strip():
                new_boxes[section] = text
                continue
            sys = "너는 글을 간결하고 핵심만 남기되 문장 호응은 자연스럽게 유지하는 편집자다. 반드시 JSON {\"summary\": \"...\"}로 답하라."
            user = f"[섹션] {section}\n아래 문단을 더 짧고 명료하게 다듬어라:\n{text}"
            data = call_gpt_json(sys, user, max_tokens=300)
            new_boxes[section] = (data.get("summary") or "").strip() or text
        st.session_state["result_boxes"] = new_boxes
        st.success("✂️ 요약을 더 간결히 정리했습니다.")
    except Exception as e:
        st.error("요약 축약 중 오류 발생.")
        if DEBUG:
            st.exception(e)

# =========================================
# 결과 렌더링(하단 ‘종합의견 초안’)
# =========================================
st.markdown("### ✅ 종합의견 초안")
with st.container(border=True):
    for section in SECTIONS:
        st.markdown(f"**{section}**")
        st.text_area(
            label="출력",
            value=st.session_state.get("result_boxes", {}).get(section, ""),
            key=f"result_{section}",        # (편집 가능해도 제출에 영향 없음)
            height=120,
            label_visibility="collapsed"
        )

# 경고/누락 메시지
warn_cols = st.columns(2)
with warn_cols[0]:
    for msg in st.session_state.get("warnings_dissent", []):
        st.error(f"⚠️ {msg}")
with warn_cols[1]:
    for msg in st.session_state.get("missing_required", []):
        st.error(f"❗ {msg}")

# 상이의견 요약 표기(섹션별)
if any(st.session_state.get("dissent_map", {s: set() for s in SECTIONS}).values()):
    st.markdown("---")
    st.markdown("#### 🔴 상이의견(섹션별)")
    for section in SECTIONS:
        ds = st.session_state.get("dissent_map", {}).get(section, set())
        if ds:
            st.markdown(f"- **{section}**: {', '.join(ds)}")

# 전체 텍스트 다운로드
concat_text = "\n\n".join(
    [f"[{sec}]\n{st.session_state.get('result_boxes', {}).get(sec, '').strip()}" for sec in SECTIONS]
).strip()
byte_len = len(concat_text.encode("utf-8"))

r1, r2 = st.columns([1, 3])
with r1:
    st.caption(f"글자수(바이트): {byte_len} / 4000")
with r2:
    st.download_button(
        "TXT로 다운로드",
        data=concat_text or "결과가 없습니다.",
        file_name="종합의견_초안.txt",
        mime="text/plain",
        use_container_width=True
    )
