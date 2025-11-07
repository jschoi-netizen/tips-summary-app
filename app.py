# app.py — TIPS 선정평가 종합의견 도우미(평가간사용)
# - OpenAI API 연결(의미 요약/검증)
# - 라벨 다수결(긍/중/부) + "긍정+단서"는 긍정으로 분류
# - 상이의견: 다수 라벨과 다른 위원만 표시
# - 필수 기재 내용: 임베딩 기반 의미 포함 검사
# - 개별 입력 칸 아래 빨간 경고 표시
# - 4000바이트 안내 + "요약 더 줄이기" 버튼 + TXT 다운로드

import os
import math
import streamlit as st
from typing import List, Dict

# OpenAI SDK (v1)
from openai import OpenAI

# ======================================================
# 환경 / 클라이언트
# ======================================================
API_KEY = os.getenv("OPENAI_API_KEY", st.secrets.get("OPENAI_API_KEY", ""))
client = OpenAI(api_key=API_KEY)

CHAT_MODEL = "gpt-4o-mini"               # 요약/라벨링
EMBED_MODEL = "text-embedding-3-small"   # 의미 유사도(저렴/빠름)

# ======================================================
# 유틸
# ======================================================
def count_bytes(s: str) -> int:
    return len(s.encode("utf-8"))

def embed_text(text: str) -> List[float]:
    """임베딩 생성 (빈 문자열 방지)"""
    t = (text or "").strip()
    if not t:
        return [0.0]
    resp = client.embeddings.create(model=EMBED_MODEL, input=t)
    return resp.data[0].embedding

def cosine_sim(a: List[float], b: List[float]) -> float:
    """numpy 없이 코사인 유사도"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))

def semantic_contains(phrase: str, targets: List[str], threshold: float = 0.78) -> bool:
    """phrase(필수 항목)가 targets(의견들) 중 하나에 '의미적으로' 포함되는지"""
    base = (phrase or "").strip()
    if not base:
        return True
    e_phrase = embed_text(base)
    for t in targets:
        tt = (t or "").strip()
        if not tt:
            continue
        e_t = embed_text(tt)
        if cosine_sim(e_phrase, e_t) >= threshold:
            return True
    return False

def call_gpt_json(system_prompt: str, user_prompt: str, max_tokens: int = 900) -> dict:
    """JSON 강제 응답"""
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
    return json.loads(resp.choices[0].message.content)

# ======================================================
# 시스템 프롬프트 (라벨 다수결 + 단서 분리)
# ======================================================
SYSTEM_PROMPT = """
너는 정부지원사업 '평가 간사 보조' 요약도우미다.
각 섹션에 대해 위원별 의견을 입력받으면 아래 규칙으로 JSON만 반환한다.

[라벨 규칙]
- 각 위원 의견을 {긍정, 중립, 부정} 중 하나로 라벨링한다.
- "긍정 + 단서(예: 기간 오래 소요, 리스크 존재)"는 '긍정' 라벨로 분류하고, 단서는 concerns에 따로 수집한다.
- 상이의견은 '다수 라벨'과 '개별 라벨'이 다를 때만 해당 위원으로 표시한다.

[출력 스키마(JSON)]
{
  "section": "<섹션명>",
  "majority_label": "긍정|중립|부정",
  "reviewers": [
    {"name":"위원1", "label":"긍정|중립|부정", "concerns":["...","..."]},
    {"name":"위원2", "label":"긍정|중립|부정", "concerns":[]}
  ],
  "summary": "2~3문장. 행정 보고체(~함.)로, 다수결 판단을 명시하고 주요 단서를 반영.",
  "dissent_reviewers": ["라벨이 다수와 다른 위원명", ...],
  "concerns": ["기간 오래 소요", "리스크 ..."]
}

[작성 규칙]
- 문체는 '~함.'으로 통일.
- 과도한 추정 금지, 입력 공백은 무시.
- JSON 외 텍스트 금지.
"""

# ======================================================
# 페이지 / 스타일
# ======================================================
st.set_page_config(page_title="TIPS 종합의견 도우미", layout="wide")
st.title("TIPS 선정평가 종합의견 도우미(평가간사용)")

st.markdown("""
<style>
.red-note { color:#b91c1c; font-size:12px; margin-top:6px; }
.gen-btn button {
  background-color:#ef4444 !important; color:white !important;
  font-weight:700 !important; width:100%; height:48px; border-radius:8px;
  box-shadow:0 1px 2px rgba(0,0,0,0.06);
}
.badge {display:inline-block; padding:4px 8px; border-radius:8px; font-size:0.85rem; font-weight:600;}
.badge-red{ background:#fde8e8; color:#9b1c1c; }
.badge-amber{ background:#fdf6b2; color:#92400e; }
.badge-green{ background:#def7ec; color:#03543f; }
</style>
""", unsafe_allow_html=True)

# ======================================================
# 사이드바 설정
# ======================================================
with st.sidebar:
    st.header("⚙️ 설정")
    n_reviewers = st.number_input("평가위원 수", value=5, min_value=1, max_value=7, step=1)
    st.caption("위원명 기재 시 입력 영역/경고/결과에 표기됩니다.")
    reviewer_names = []
    for i in range(n_reviewers):
        reviewer_names.append(st.text_input(f"위원{i+1} 이름", value=f"위원{i+1}"))

    st.markdown("---")
    st.subheader("필수 기재 내용")
    st.caption("한 줄에 하나씩. 의미적으로 포함되었는지 검사합니다.")
    required_lines = st.text_area("필수 기재 내용(한 줄에 하나)",
                                  value="평가단 승인사항\n협약 시 보완사항",
                                  height=100).strip().splitlines()
    st.markdown("---")
    st.caption("※ OPENAI_API_KEY는 Streamlit Secrets로 주입됩니다.")

# ======================================================
# 입력 영역
# ======================================================
st.markdown("### 📝 위원별 의견 입력")
tabs = st.tabs(["기술성", "사업성", "연구개발비 조정", "기타사항"])

section_texts: Dict[str, List[str]] = {
    "기술성": ["" for _ in range(n_reviewers)],
    "사업성": ["" for _ in range(n_reviewers)],
    "연구개발비 조정": ["" for _ in range(n_reviewers)],
    "기타사항": ["" for _ in range(n_reviewers)],
}

# 세션 상태
if "result_boxes" not in st.session_state:
    st.session_state.result_boxes = {k: "" for k in section_texts}
if "warnings_dissent" not in st.session_state:
    st.session_state.warnings_dissent = []
if "missing_required" not in st.session_state:
    st.session_state.missing_required = []
if "dissent_map" not in st.session_state:
    st.session_state.dissent_map = {k: set() for k in section_texts}

# 입력 폼 (개별 칸 경고 표시 포함)
for (tab, section) in zip(tabs, section_texts.keys()):
    with tab:
        cols = st.columns(n_reviewers)
        for i, c in enumerate(cols):
            with c:
                section_texts[section][i] = st.text_area(
                    f"{reviewer_names[i]}",
                    key=f"{section}_{i}",
                    height=120,
                    placeholder=f"{section} 의견을 입력하세요."
                )
                # 생성 이후: 해당 위원이 상이의견이면 빨간 안내
                dissent_set = st.session_state.dissent_map.get(section, set())
                if reviewer_names[i] in dissent_set:
                    st.markdown(
                        "<div class='red-note'>⚠️ 상이의견으로 분류됨 — 다수 의견과 의미적으로 상충합니다. 확인 필요</div>",
                        unsafe_allow_html=True
                    )

st.markdown("---")

# ======================================================
# 버튼
# ======================================================
gen_col1, gen_col2, gen_col3 = st.columns([4, 1.5, 1.5])
with gen_col1:
    gen = st.button("종합의견 생성", type="primary", use_container_width=True, key="gen",
                    help="의미 요약 + 상이의견/필수문구 검증")
with gen_col2:
    shorten_btn = st.button("요약 더 줄이기", help="바이트 초과 시 한 번 더 요약", use_container_width=True)
with gen_col3:
    txt_btn = st.button("TXT로 다운로드", use_container_width=True)

st.markdown("### ✅ 종합의견 초안")

# ======================================================
# 생성 로직
# ======================================================
def generate_all():
    """섹션별 의미 요약(JSON) + 상이의견 + 필수기재 의미검증 + 개별 칸 경고 맵 저장"""
    out_boxes = {}
    dissent_msgs = []
    missing_msgs = []
    dissent_map = {k: set() for k in section_texts}

    for section, opinions in section_texts.items():
        # 공백 제거 후 1개 이상 있을 때만 요약
        pairs = [(nm, (tx or "").strip()) for nm, tx in zip(reviewer_names, opinions) if (tx or "").strip()]
        if not pairs:
            out_boxes[section] = "(의견 입력 없음)"
            continue

        # 1) 라벨 다수결 + 요약(JSON)
        joined = "\n".join([f"- {nm}: {tx}" for nm, tx in pairs])
        user = f"[섹션] {section}\n[위원별 의견]\n{joined}"
        data = call_gpt_json(SYSTEM_PROMPT, user, max_tokens=900)

        out_boxes[section] = data.get("summary", "").strip() or "(요약 없음)"

        # 2) 상이의견 → 라벨이 다수와 다른 위원만
        for nm in data.get("dissent_reviewers", []):
            if nm:
                dissent_map[section].add(nm)
        if data.get("dissent_reviewers"):
            dissent_msgs.append(f"섹션 [{section}] 상이의견: {', '.join([n for n in data['dissent_reviewers'] if n])}")

        # 3) 필수 기재 '의미 포함' 검사 (섹션 내 모든 의견 기준)
        flat_text = " ".join([tx for _, tx in pairs])
        miss = []
        for req in required_lines:
            if not semantic_contains(req, [flat_text]):
                miss.append(req)
        if miss:
            missing_msgs.append(f"섹션 [{section}] 필수 기재 누락: {', '.join(miss)}")

    st.session_state.result_boxes = out_boxes
    st.session_state.warnings_dissent = dissent_msgs
    st.session_state.missing_required = missing_msgs
    st.session_state.dissent_map = dissent_map

def shorten_all():
    """섹션별 요약을 더 간결하게(4000바이트 대응용)"""
    for section, text in st.session_state.result_boxes.items():
        payload = (
            "아래 텍스트를 의미를 유지하며 더 간결하게 요약하라. "
            "불필요한 수식어/중복 제거. 문장 종결 '~함.' 유지.\n\n"
            f"---\n{text}\n---"
        )
        resp = client.chat.completions.create(
            model=CHAT_MODEL,
            temperature=0.2,
            messages=[
                {"role": "system", "content": "간결 요약 보조"},
                {"role": "user", "content": payload},
            ],
            max_tokens=260,
        )
        st.session_state.result_boxes[section] = resp.choices[0].message.content.strip()

# 실행
if gen:
    if not API_KEY:
        st.error("OPENAI_API_KEY 가 설정되지 않았습니다. Streamlit Secrets에 추가해주세요.")
    else:
        with st.spinner("의미 요약/검증 중..."):
            generate_all()

if shorten_btn and st.session_state.result_boxes:
    with st.spinner("더 간결하게 요약 중..."):
        shorten_all()

# ======================================================
# 출력
# ======================================================
total_text = ""
for section in ["기술성", "사업성", "연구개발비 조정", "기타사항"]:
    st.markdown(f"**{section}**")
    box_val = st.session_state.result_boxes.get(section, "")
    st.text_area("", value=box_val, height=120, key=f"out_{section}")
    total_text += f"[{section}]\n{box_val}\n\n"

# 경고 모음
if st.session_state.warnings_dissent:
    st.error("🔴 상이의견 검출됨\n- " + "\n- ".join(st.session_state.warnings_dissent))
if st.session_state.missing_required:
    st.warning("🟠 필수 기재 누락\n- " + "\n- ".join(st.session_state.missing_required))

# 바이트 안내 + 초과 경고
total_bytes = count_bytes(total_text)
st.caption(f"글자수(바이트): {total_bytes} / 4000")
if total_bytes > 4000:
    st.warning("현재 4000바이트를 초과했습니다. [요약 더 줄이기] 버튼을 눌러 압축해 주세요.")

# TXT 다운로드
if txt_btn and total_text.strip():
    st.download_button("TXT 다운로드", data=total_text, file_name="종합의견.txt", mime="text/plain")
