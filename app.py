import os
from collections import defaultdict
import streamlit as st

# ============== OpenAI (Optional) ==============
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

API_KEY = st.secrets.get("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))
CHAT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
client = None
if API_KEY and OpenAI is not None:
    client = OpenAI(api_key=API_KEY)

# ============== Constants / State ==============
SECTIONS = ["기술성", "사업성", "연구개발비 조정", "기타사항"]
TITLE = "TIPS 선정평가 종합의견 도우미(평가간사용)"

st.set_page_config(page_title=TITLE, layout="wide")
st.session_state.setdefault("result_boxes", {s: "" for s in SECTIONS})
st.session_state.setdefault("result_combined", "")
st.session_state.setdefault("dissent_map", {s: set() for s in SECTIONS})
st.session_state.setdefault("warnings_dissent", [])
st.session_state.setdefault("missing_required", [])

# ============== Sidebar ==============
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
    required_raw = st.text_area("필수 기재 내용(한 줄에 하나)", "평가단 승인사항\n협약 시 보완사항", height=100)
    REQUIRED_LINES = [ln.strip() for ln in required_raw.splitlines() if ln.strip()]

    st.markdown("---")
    if not API_KEY:
        st.warning("`OPENAI_API_KEY`가 Secrets에 설정되지 않았습니다. (AI 분류/요약 없이 기본 화면만 동작)")
    else:
        st.caption("🔒 OPENAI_API_KEY는 Streamlit Secrets를 통해 안전하게 주입됩니다.")

# ============== Title & 설명 ==============
st.title(TITLE)
st.caption("각 위원의 ‘혼합된 전체 의견’을 한 칸에 붙여넣으세요. (기술성/사업성/연구개발비 조정/기타사항이 섞여 있어도 됩니다.) "
           "‘종합의견 생성’을 누르면 자동으로 4개 항목으로 분리·취합합니다.")

# ============== 입력(위원별 한 칸) ==============
st.markdown("### 위원별 평가 의견 입력")
cols = st.columns(len(reviewer_names))
reviewer_texts = []
for j, c in enumerate(cols):
    with c:
        txt = st.text_area(
            f"{reviewer_names[j]}",
            placeholder="한 칸에 해당 위원의 전체 평가의견을 붙여넣으세요.\n(기술성/사업성/연구개발비 조정/기타사항이 섞여 있어도 됩니다.)",
            key=f"mixed_{j}",
            height=220
        )
        reviewer_texts.append(txt or "")

# ============== GPT 유틸 ==============
SYSTEM_JSON = """너는 정부 R&D 사업 선정평가 간사 보조원이다.
입력되는 '위원별 전체 의견'을 읽고 아래 JSON만 출력한다.

JSON 스키마:
{
  "sections": {
    "기술성": {
      "summary": "<합의 기반 3~5문장 요약(문어체, 자연스러운 호응)>",
      "majority_label": "긍정|부정|중립",
      "dissent_reviewers": ["상이의견 위원명", ...]
    },
    "사업성": { ... 동형식 ... },
    "연구개발비 조정": { ... 동형식 ... },  // 없으면 summary는 빈 문자열 ""
    "기타사항": { ... 동형식 ... }           // 없으면 summary는 빈 문자열 ""
  }
}

규칙:
- 다수의견을 기준으로 majority_label을 판단하되, 소수·상이 의견은 dissent_reviewers에 이름만 담는다.
- summary는 합의·공통된 내용을 중심으로 간결하게(3~5문장). 상이의견은 본문에 넣지 않는다.
- 특정 항목에 정보가 없으면 summary는 ""로 둔다.
- 반드시 JSON object 하나만 출력한다.
"""

def call_gpt_json(system_prompt: str, user_prompt: str, max_tokens=1200) -> dict:
    """response_format=json_object 를 사용해 JSON으로만 응답"""
    try:
        if not client:
            raise RuntimeError("OpenAI client not configured")
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
            with st.expander("🧪 GPT Raw Response"):
                st.code(content, language="json")
        return json.loads(content)
    except Exception as e:
        if DEBUG:
            st.error("❌ GPT 호출 실패")
            st.exception(e)
        # 실패 시 빈 구조 반환
        return {
            "sections": {s: {"summary": "", "majority_label": "중립", "dissent_reviewers": []} for s in SECTIONS}
        }

def semantic_contains(required_phrase: str, texts: list[str]) -> bool:
    """필수 문구가 의미적으로 포함되는지 GPT로 판정"""
    try:
        joined = "\n".join([t for t in texts if t])
        if not joined.strip():
            return False
        sys = "너는 의미 포함 여부만 판정한다. 반드시 JSON {\"contains\": true|false} 로만 답하라."
        user = f"[요구문구]\n{required_phrase}\n\n[검토대상 텍스트]\n{joined}"
        data = call_gpt_json(sys, user, max_tokens=200)
        return bool(data.get("contains", False))
    except Exception:
        return False

# ============== 생성/축약 버튼 ==============
left, mid, right = st.columns([2, 1, 1])
with left:
    gen_clicked = st.button("종합의견 생성", type="primary", use_container_width=True)
with mid:
    shrink_clicked = st.button("요약 더 줄이기", use_container_width=True)

# ============== 생성 로직 ==============
def generate():
    # 사용자 프롬프트: 위원 이름과 전체 의견을 줄로 전달
    lines = [f"- {nm}: {tx}" for nm, tx in zip(reviewer_names, reviewer_texts) if (tx or "").strip()]
    if not lines:
        st.warning("입력된 위원 의견이 없습니다.")
        return

    user_prompt = "[위원별 전체 의견]\n" + "\n".join(lines)
    data = call_gpt_json(SYSTEM_JSON, user_prompt, max_tokens=1400)

    # 섹션별 결과 채우기
    boxes = {s: "" for s in SECTIONS}
    dissent_map = {s: set() for s in SECTIONS}
    warnings = []
    sections_json = (data or {}).get("sections", {}) or {}

    for s in SECTIONS:
        entry = sections_json.get(s, {}) or {}
        boxes[s] = (entry.get("summary") or "").strip()
        for nm in entry.get("dissent_reviewers", []) or []:
            if nm:
                dissent_map[s].add(nm)
        if entry.get("dissent_reviewers"):
            warnings.append(f"[{s}] 상이의견: {', '.join(entry.get('dissent_reviewers', []))}")

    # 필수 문구 의미 포함 여부 (전체 텍스트 기반)
    missing_msgs = []
    all_text = "\n".join(reviewer_texts)
    for req in REQUIRED_LINES:
        if req and not semantic_contains(req, [all_text]):
            missing_msgs.append(f"필수 기재 누락: {req}")

    # 합본 텍스트(요청 형식)
    combined = (
        f"ㅇ 기술성\n{boxes['기술성']}\n\n"
        f"ㅇ 사업성\n{boxes['사업성']}\n\n"
        f"ㅇ 연구개발비 조정의견\n{boxes['연구개발비 조정']}\n\n"
        f"ㅇ 기타사항\n{boxes['기타사항']}"
    ).strip()

    st.session_state["result_boxes"] = boxes
    st.session_state["result_combined"] = combined
    st.session_state["dissent_map"] = dissent_map
    st.session_state["warnings_dissent"] = warnings
    st.session_state["missing_required"] = missing_msgs

    st.success("✅ 종합의견 생성이 완료되었습니다. (아래 초안 영역에 표시됨)")

def shrink_result():
    """합본 텍스트와 섹션 요약을 더 간결하게"""
    if not st.session_state.get("result_combined"):
        st.warning("축약할 결과가 없습니다. 먼저 종합의견을 생성하세요.")
        return
    new_boxes = {}
    for s, text in st.session_state.get("result_boxes", {}).items():
        if not text.strip():
            new_boxes[s] = text
            continue
        sys = "너는 글을 간결·명료하게 다듬는 편집자다. 반드시 JSON {\"summary\": \"...\"} 형식으로만 답하라."
        user = f"[섹션] {s}\n아래 문단을 더 짧고 명료하게 다듬어라:\n{text}"
        data = call_gpt_json(sys, user, max_tokens=300)
        new_boxes[s] = (data.get("summary") or "").strip() or text

    combined = (
        f"ㅇ 기술성\n{new_boxes['기술성']}\n\n"
        f"ㅇ 사업성\n{new_boxes['사업성']}\n\n"
        f"ㅇ 연구개발비 조정의견\n{new_boxes['연구개발비 조정']}\n\n"
        f"ㅇ 기타사항\n{new_boxes['기타사항']}"
    ).strip()

    st.session_state["result_boxes"] = new_boxes
    st.session_state["result_combined"] = combined
    st.success("✂️ 요약을 더 간결히 정리했습니다.")

if gen_clicked:
    with st.spinner("의견 분류/요약 중..."):
        generate()

if shrink_clicked:
    with st.spinner("축약 중..."):
        shrink_result()

# ============== 입력칸 하단 ‘상이의견 라벨’ ==============
if any(st.session_state.get("dissent_map", {s: set() for s in SECTIONS}).values()):
    st.markdown("---")
    st.markdown("#### 🔴 상이의견(위원별 안내)")
    # 위원별 어떤 섹션에서 상이인지 정리
    reverse_map = defaultdict(list)
    for sec, names in st.session_state.get("dissent_map", {}).items():
        for nm in names:
            reverse_map[nm].append(sec)
    for nm in reviewer_names:
        secs = reverse_map.get(nm, [])
        if secs:
            st.error(f"- **{nm}**: 상이의견 섹션 → {', '.join(secs)}")

# ============== 종합의견 초안(요청 형식) ==============
st.markdown("### ✅ 종합의견 초안")
st.text_area(
    "draft",
    value=st.session_state.get("result_combined", ""),
    key="combined_out",
    height=320,
    label_visibility="collapsed"
)

# ============== 섹션별 원문 박스(유지) ==============
with st.expander("섹션별 요약 보기"):
    for s in SECTIONS:
        st.markdown(f"**{s}**")
        st.text_area(
            f"{s}_out",
            value=st.session_state.get("result_boxes", {}).get(s, ""),
            key=f"result_{s}",
            height=150
        )

# ============== 경고(상이/필수누락) ==============
warn_cols = st.columns(2)
with warn_cols[0]:
    for msg in st.session_state.get("warnings_dissent", []):
        st.error(f"⚠️ {msg}")
with warn_cols[1]:
    for msg in st.session_state.get("missing_required", []):
        st.error(f"❗ {msg}")

# ============== 다운로드 & 바이트 수 ==============
combined_text = st.session_state.get("result_combined", "") or ""
byte_len = len(combined_text.encode("utf-8"))

c1, c2 = st.columns([1, 3])
with c1:
    st.caption(f"글자수(바이트): {byte_len} / 4000")
with c2:
    st.download_button(
        "TXT로 다운로드",
        data=combined_text or "결과가 없습니다.",
        file_name="종합의견_초안.txt",
        mime="text/plain",
        use_container_width=True
    )
