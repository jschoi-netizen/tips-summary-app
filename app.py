import os
import math
import tiktoken
import streamlit as st
from typing import List, Dict
from collections import defaultdict

# OpenAI SDK (v1 스타일)
from openai import OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", st.secrets.get("OPENAI_API_KEY", "")))

# ====== 모델 설정 ======
CHAT_MODEL = "gpt-4o-mini"               # 요약/판정용
EMBED_MODEL = "text-embedding-3-small"   # 의미 유사도 판정용(빠르고 저렴)

# ====== 유틸 ======
def count_bytes(s: str) -> int:
    return len(s.encode("utf-8"))

def embed_text(text: str) -> List[float]:
    if not text.strip():
        return [0.0]
    resp = client.embeddings.create(model=EMBED_MODEL, input=text)
    return resp.data[0].embedding

def cosine_sim(a: List[float], b: List[float]) -> float:
    import numpy as np
    a = np.array(a); b = np.array(b)
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)

def semantic_contains(phrase: str, targets: List[str], threshold: float = 0.78) -> bool:
    """phrase 가 targets 중 하나에 '의미적으로' 포함되는지(유사) 확인"""
    if not phrase.strip():
        return True
    e_phrase = embed_text(phrase)
    for t in targets:
        if not t.strip():
            continue
        e_t = embed_text(t)
        if cosine_sim(e_phrase, e_t) >= threshold:
            return True
    return False

def call_gpt(system_prompt: str, user_prompt: str, max_tokens: int = 600) -> str:
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role":"system","content":system_prompt},
            {"role":"user","content":user_prompt}
        ],
        temperature=0.2,
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content.strip()

# ====== 페이지/레이아웃 ======
st.set_page_config(page_title="TIPS 종합의견 도우미", layout="wide")

st.title("TIPS 선정평가 종합의견 도우미(평가간사용)")

# 빨간 경고 태그 스타일
st.markdown("""
<style>
.red-note {
  color:#b91c1c; 
  font-size:12px; 
  margin-top:6px; 
}
.gen-btn button {
  background-color:#ef4444 !important; 
  color:white !important; 
  font-weight:700 !important;
  width:100%; height:48px; border-radius:8px;
  box-shadow:0 1px 2px rgba(0,0,0,0.06);
}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ 설정")
    n_reviewers = st.number_input("평가위원 수",  value=5, min_value=1, max_value=7, step=1)
    st.caption("위원명 기재 시 입력 영역/결과에 표시됩니다.")
    reviewer_names = []
    for i in range(n_reviewers):
        name = st.text_input(f"위원{i+1} 이름", value=f"위원{i+1}")
        reviewer_names.append(name)

    st.markdown("---")
    st.subheader("필수 기재 내용")
    st.caption("한 줄에 하나씩. 의미적으로 들어갔는지 자동 검증합니다.")
    required_lines = st.text_area(
        "필수 기재 내용(한 줄에 하나)", 
        value="평가단 승인사항\n협약 시 보완사항",
        height=100
    ).strip().splitlines()

    st.markdown("---")
    st.caption("※ API 키는 Streamlit Secrets(OPENAI_API_KEY)로 주입됩니다.")

st.markdown("### 📝 위원별 의견 입력")
tabs = st.tabs(["기술성", "사업성", "연구개발비 조정", "기타사항"])

section_texts: Dict[str, List[str]] = {
    "기술성": ["" for _ in range(n_reviewers)],
    "사업성": ["" for _ in range(n_reviewers)],
    "연구개발비 조정": ["" for _ in range(n_reviewers)],
    "기타사항": ["" for _ in range(n_reviewers)],
}

# ====== 상태 초기화 ======
if "result_boxes" not in st.session_state:
    st.session_state.result_boxes = {k:"" for k in section_texts}
if "warnings_dissent" not in st.session_state:
    st.session_state.warnings_dissent = []
if "missing_required" not in st.session_state:
    st.session_state.missing_required = []
# ★ 섹션별 상이의견 위원 set 저장
if "dissent_map" not in st.session_state:
    st.session_state.dissent_map = {k:set() for k in section_texts}

# ====== 입력 폼 + (생성 후) 개별 칸 아래 경고 표시 ======
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
                # 생성이 돌고 난 뒤라면, 해당 위원이 상이의견 대상이면 경고 표시
                dissent_set = st.session_state.dissent_map.get(section, set())
                if reviewer_names[i] in dissent_set:
                    st.markdown(f"<div class='red-note'>⚠️ 상이의견으로 분류됨 — 다수 의견과 의미적으로 상충합니다. 확인 필요</div>", unsafe_allow_html=True)

st.markdown("---")

# ====== 종합의견 생성 버튼 ======
gen_col1, gen_col2, gen_col3 = st.columns([4,1.5,1.5])
with gen_col1:
    gen = st.button("종합의견 생성", type="primary", use_container_width=True, key="gen",
                    help="의미 요약 + 상이의견/필수문구 검증")
with gen_col2:
    shorten_btn = st.button("요약 더 줄이기", help="바이트 초과 시 한 번 더 요약", use_container_width=True)
with gen_col3:
    txt_btn = st.button("TXT로 다운로드", use_container_width=True)

st.markdown("### ✅ 종합의견 초안")

# ====== 생성 로직 ======
def generate_all():
    """GPT로 섹션별 종합의견 생성 + 상이의견/필수문구 검증 + (개별칸 경고 표시용) dissent_map 저장"""
    out_boxes = {}
    dissent_msgs = []
    missing_msgs = []
    dissent_map = {k:set() for k in section_texts}  # 섹션 -> {상이의견 위원명}

    for section, opinions in section_texts.items():
        # 1) 상이 의견/다수 의견/소수(반대) 감지 + 위원 명시 + 섹션 요약
        sys = (
            "너는 정부지원사업 평가 간사를 보조하는 요약도우미다. "
            "위원별 의견 목록을 입력받으면 다음을 수행하라: "
            "1) 의견을 의미적으로 통합하여 2~3문장 내로 요약(문체: '~함.'), "
            "2) 의견이 상이한 경우 다수 의견과 소수 의견을 구분하고, 소수 의견의 위원명 목록을 식별해라, "
            "3) 무성의하거나 빈 칸은 무시, 중의적 표현 금지, "
            "4) 신뢰 없는 추정 금지."
        )
        joined = "\n".join([f"- {name}: {op.strip() or '(입력없음)'}" for name, op in zip(reviewer_names, opinions)])
        user = (
            f"[섹션] {section}\n"
            f"[위원별 의견]\n{joined}\n\n"
            "출력 형식:\n"
            "요약: ...\n"
            "상이의견: (있으면) 위원명 콤마구분, 없으면 '없음'\n"
        )
        gpt_out = call_gpt(sys, user, max_tokens=380)

        # 2) 필수 기재 내용(의미 포함) 검증 (임베딩 기반)
        flat_text = " ".join([op for op in opinions if op.strip()])
        miss_list = []
        for req in required_lines:
            if not semantic_contains(req, [flat_text]):
                miss_list.append(req)

        out_boxes[section] = gpt_out
        # 상이의견 파싱 → dissent_map/경고 메시지 업데이트
        if "상이의견:" in gpt_out:
            line = [ln for ln in gpt_out.splitlines() if ln.strip().startswith("상이의견")][:1]
            if line:
                txt = line[0]
                if "없음" not in txt:
                    names_str = txt.split(":",1)[1].strip()
                    # 이름 분리
                    names = [nm.strip() for nm in names_str.split(",") if nm.strip()]
                    if names:
                        dissent_map[section] = set(names)
                        dissent_msgs.append(f"섹션 [{section}] 상이의견: {', '.join(names)}")

        if miss_list:
            missing_msgs.append(f"섹션 [{section}] 필수 기재 누락: {', '.join(miss_list)}")

    st.session_state.result_boxes = out_boxes
    st.session_state.warnings_dissent = dissent_msgs
    st.session_state.missing_required = missing_msgs
    st.session_state.dissent_map = dissent_map

def shorten_all():
    """전체 결과를 바이트 한도에 맞게 압축 요약"""
    for section, text in st.session_state.result_boxes.items():
        payload = (
            "아래 텍스트를 의미를 유지하며 더 간결하게 줄여줘. "
            "불필요한 수식어/중복 제거. 핵심만 남겨라. 문장 종결 '~함.' 유지.\n\n"
            f"---\n{text}\n---"
        )
        short = call_gpt("간결 요약 보조", payload, max_tokens=260)
        st.session_state.result_boxes[section] = short

# 실행
if gen:
    if not client.api_key:
        st.error("OPENAI_API_KEY 가 설정되지 않았습니다. Streamlit Secrets에 추가해주세요.")
    else:
        with st.spinner("의미 요약/검증 중..."):
            generate_all()

if shorten_btn and st.session_state.result_boxes:
    with st.spinner("더 간결하게 요약 중..."):
        shorten_all()

# ====== 출력 그리기 ======
result_boxes = st.session_state.result_boxes
total_text = ""
for section in ["기술성", "사업성", "연구개발비 조정", "기타사항"]:
    st.markdown(f"**{section}**")
    box_val = result_boxes.get(section, "")
    st.text_area("", value=box_val, height=120, key=f"out_{section}")
    total_text += f"[{section}]\n{box_val}\n\n"

# 경고 영역(상의 의견/필수 누락)
if st.session_state.warnings_dissent:
    st.error("🔴 상이의견 검출됨\n- " + "\n- ".join(st.session_state.warnings_dissent))
if st.session_state.missing_required:
    st.warning("🟠 필수 기재 누락\n- " + "\n- ".join(st.session_state.missing_required))

# 바이트 카운트/한도 안내
total_bytes = count_bytes(total_text)
st.caption(f"글자수(바이트): {total_bytes} / 4000")
if total_bytes > 4000:
    st.warning("현재 4000바이트를 초과했습니다. [요약 더 줄이기] 버튼을 눌러 압축해 주세요.")

# TXT 다운로드
if txt_btn and total_text.strip():
    st.download_button("TXT 다운로드", data=total_text, file_name="종합의견.txt", mime="text/plain")
