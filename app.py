import re
import unicodedata
from io import BytesIO
from collections import Counter

import streamlit as st

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(page_title="TIPS 선정평가 종합의견 도우미 (MVP)", layout="wide")

st.title("📝 TIPS 선정평가 종합의견 도우미 (MVP)")
st.caption("위원별 의견을 항목별로 입력하면, 중복 제거/유사 그룹핑/상이 의견 감지/필수 문구 확인/글자수 관리까지 한 화면에서 처리합니다.")

# =============================
# 사이드바 (설정)
# =============================
with st.sidebar:
    st.header("⚙️ 설정")
    num_reviewers = st.number_input("평가위원 수", 1, 5, value=3)
    byte_limit = st.number_input("종합의견 글자수 한도(byte)", min_value=500, max_value=6000, value=4000, step=100)
    sim_threshold = st.slider("유사 판단 임계값(토큰 Jaccard)", 0.5, 0.95, 0.80, 0.01,
                              help="둘 문장의 토큰 겹침 비율이 이 값 이상이면 '중복/유사'로 간주해 묶습니다.")
    required_phrases_raw = st.text_area("필수 문구(콤마로 구분)", placeholder="평가단 승인사항, 협약 시 보완사항")

    st.markdown("---")
    st.caption("※ 외부 패키지 없이 동작하도록 구현되었습니다. (간단 토큰/Jaccard 기반)")

# 위원 이름 입력
with st.sidebar:
    st.subheader("👤 위원 이름")
    reviewer_names = []
    for i in range(num_reviewers):
        name = st.text_input(f"{i+1}번 위원 이름", value=f"위원{i+1}")
        reviewer_names.append(name)

# 필수문구 리스트
required_phrases = [p.strip() for p in required_phrases_raw.split(",") if p.strip()]

# =============================
# 텍스트 전처리/유틸
# =============================

def normalize_text(text: str) -> str:
    """간단 정규화: 유니코드 정규화 + 괄호·특수기호 최소화"""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\u200b", "")  # zero-width
    # 줄바꿈 정리: 문장경계 보존을 위해 줄바꿈은 마침표로 통일
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", ". ", text).strip()
    return text

def tokenize(text: str):
    """아주 단순한 토큰화(공백 기준), 불필요한 기호 제거"""
    text = text.lower()
    # 한글/영문/숫자/공백만 남기고 제거
    text = re.sub(r"[^0-9a-zA-Z가-힣% ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    return text.split(" ")

def jaccard_sim(a: str, b: str) -> float:
    ta, tb = set(tokenize(a)), set(tokenize(b))
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0

def dedup_and_group(items, threshold=0.8):
    """
    중복·유사 문장 그룹핑.
    - threshold 이상이면 같은 그룹으로 묶음
    - 각 그룹은 대표문장(가장 짧고 간결한 문장)을 선택
    return: [(대표문장, [원소...]) ...]
    """
    texts = [normalize_text(x) for x in items if normalize_text(x)]
    groups = []
    for t in texts:
        placed = False
        for g in groups:
            # 그룹 대표와 비교 (조금 보수적으로 대표문장과만 비교)
            rep = g[0]
            if jaccard_sim(t, rep) >= threshold:
                g[1].append(t)
                # 대표는 더 간결한 문장으로 갱신
                g[0] = min([g[0]] + [t], key=lambda s: len(s))
                placed = True
                break
        if not placed:
            groups.append([t, [t]])
    # (대표, 원문리스트)
    return [(g[0], g[1]) for g in groups]

POS_WORDS = ["우수", "탁월", "강점", "높다", "긍정", "양호", "적합", "우수함"]
NEG_WORDS = ["어렵", "미흡", "부족", "낮다", "부정", "취약", "부적합", "문제"]

def polarity(text: str):
    """긍/부정 단순 라벨링 (키워드 카운트)"""
    t = normalize_text(text)
    pos = sum(1 for w in POS_WORDS if w in t)
    neg = sum(1 for w in NEG_WORDS if w in t)
    if pos > neg:
        return "POS"
    if neg > pos:
        return "NEG"
    return "NEU"

def build_section(title, items, threshold=0.8):
    """
    항목별 취합(중복 제거/유사 그룹핑, 상이 의견 탐지)
    return: (표시용 리스트, 상이여부, 요약용 문자열)
    """
    groups = dedup_and_group(items, threshold=threshold)
    # 상이 여부 판단 (그룹 대표의 polarity 기반)
    labels = Counter([polarity(rep) for rep, _ in groups])
    conflict = labels.get("POS", 0) > 0 and labels.get("NEG", 0) > 0

    # 표시용 리스트(대표문장)
    pretty = [rep for rep, _ in groups]

    # 요약용 문자열
    out_lines = []
    out_lines.append(f"[{title}]")
    if conflict:
        out_lines.append("⚠️ 위원 간 의견이 상이합니다:")
    for rep, _ in groups:
        out_lines.append(f"- {rep}")
    section_text = "\n".join(out_lines).strip()
    return pretty, conflict, section_text

def byte_len(s: str) -> int:
    return len(s.encode("utf-8"))

def compress_summary_to_limit(text: str, limit: int, keep_keywords=None) -> str:
    """
    간단 압축:
    1) 공백/중복 특수기호 정리
    2) 문장단위로 자르면서 우선 보존 키워드가 들어간 문장을 우선 살림
    3) 그래도 초과면 마지막에 '…' 붙여 자름
    """
    if keep_keywords is None:
        keep_keywords = []

    # 문장 분리 ('. ' 기준)
    text = re.sub(r"\s+", " ", text).strip()
    sentences = [s.strip() for s in re.split(r"(?<=\.)\s+", text) if s.strip()]
    if not sentences:
        sentences = [text]

    # 키워드 스코어
    scored = []
    for s in sentences:
        score = sum(1 for k in keep_keywords if k and k in s)
        scored.append((score, s))
    # 키워드 많은 순 → 짧은 문장 순
    scored.sort(key=lambda x: (-x[0], len(x[1])))

    out = []
    for _, s in scored:
        if byte_len(" ".join(out + [s])) <= limit:
            out.append(s)

    if out:
        summary = " ".join(out).strip()
    else:
        # 첫 문장 최대한 잘라서라도
        summary = sentences[0]
        while byte_len(summary) > limit and len(summary) > 2:
            summary = summary[:-2].strip() + "…"

    # 혹시 초과면 맨끝에서 잘라냄
    while byte_len(summary) > limit and len(summary) > 2:
        summary = summary[:-2].strip() + "…"

    return summary

def txt_download_button(filename: str, content: str, label="TXT로 다운로드"):
    return st.download_button(
        label=label, data=content.encode("utf-8"),
        file_name=filename, mime="text/plain"
    )

# =============================
# 입력 UI (4개 항목, 위원 이름 반영)
# =============================
st.markdown("### 🧾 위원별 의견 입력")

tabs = st.tabs(["기술성", "사업성", "연구개발비 조정", "기타사항"])
raw_inputs = {
    "기술성": [],
    "사업성": [],
    "연구개발비 조정": [],
    "기타사항": [],
}

with tabs[0]:
    cols = st.columns(num_reviewers)
    for i, c in enumerate(cols):
        with c:
            raw_inputs["기술성"].append(
                st.text_area(f"{reviewer_names[i]} (기술성)", height=120, key=f"tech_{i}")
            )

with tabs[1]:
    cols = st.columns(num_reviewers)
    for i, c in enumerate(cols):
        with c:
            raw_inputs["사업성"].append(
                st.text_area(f"{reviewer_names[i]} (사업성)", height=120, key=f"biz_{i}")
            )

with tabs[2]:
    cols = st.columns(num_reviewers)
    for i, c in enumerate(cols):
        with c:
            raw_inputs["연구개발비 조정"].append(
                st.text_area(f"{reviewer_names[i]} (연구개발비 조정)", height=120, key=f"budget_{i}")
            )

with tabs[3]:
    cols = st.columns(num_reviewers)
    for i, c in enumerate(cols):
        with c:
            raw_inputs["기타사항"].append(
                st.text_area(f"{reviewer_names[i]} (기타사항)", height=120, key=f"etc_{i}")
            )

st.markdown("---")

# =============================
# 처리 & 출력
# =============================
left, right = st.columns([1, 1])

with left:
    st.subheader("📌 항목별 취합 결과 (중복 제거/유사 그룹핑)")
    for sec in ["기술성", "사업성", "연구개발비 조정", "기타사항"]:
        pretty, conflict, section_text = build_section(sec, raw_inputs[sec], threshold=sim_threshold)
        box = st.container()
        with box:
            st.markdown(f"**{sec}**")
            if conflict:
                st.markdown(":warning: **위원 간 상이한 의견이 감지되었습니다.**")
            if pretty:
                for p in pretty:
                    st.write(f"- {p}")
            else:
                st.caption("입력된 의견이 없습니다.")
        st.divider()

with right:
    st.subheader("🧩 종합의견 초안")
    # 네 섹션을 합쳐 초안 생성
    sec_texts = []
    conflicts = False
    for sec in ["기술성", "사업성", "연구개발비 조정", "기타사항"]:
        pretty, conflict, section_text = build_section(sec, raw_inputs[sec], threshold=sim_threshold)
        conflicts = conflicts or conflict
        if section_text.strip():
            sec_texts.append(section_text)
    draft = "\n\n".join(sec_texts).strip()

    # 필수문구 확인
    missing = [p for p in required_phrases if p and p not in draft]

    # 표시
    st.text_area("종합의견(초안)", value=draft, height=280, key="summary_draft")

    # 글자수
    blen = byte_len(draft)
    st.caption(f"글자수(byte): **{blen} / {byte_limit}**")
    st.progress(min(1.0, blen / max(1, byte_limit)))

    if conflicts:
        st.warning("⚠️ 상이 의견이 포함되어 있습니다. 최종 문구 확정 전에 검토하세요.")
    if missing:
        st.error("❌ 누락된 필수 문구: " + ", ".join(missing))

    # 글자수 줄이기 (중요단어 중심)
    st.markdown("##### ✂️ 글자수 자동 줄이기")
    keep_keys_raw = st.text_input("요약 시 우선 보존 키워드(콤마 구분)",
                                  value="핵심 기술, 사업모델, 매출, 시장, 검토, 조정, 보완, 승인")
    keep_keys = [k.strip() for k in keep_keys_raw.split(",") if k.strip()]
    if st.button("한도 내로 요약/압축"):
        compressed = compress_summary_to_limit(draft, byte_limit, keep_keywords=keep_keys)
        st.session_state["summary_draft"] = compressed
        st.success("요약/압축 완료! (아래 텍스트박스가 갱신되었습니다.)")

    st.markdown("##### ⬇️ 내보내기")
    txt_download_button("종합의견_초안.txt", st.session_state.get("summary_draft", draft), "TXT로 다운로드")
