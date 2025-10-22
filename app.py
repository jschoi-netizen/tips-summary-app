import streamlit as st
import json
import os
import textwrap

# ========== 1) OpenAI API ==========
# Streamlit Secrets에 OPENAI_API_KEY 저장 후 사용
# (앱 우상단 ⋮ → Edit secrets → 아래 형식)
# OPENAI_API_KEY = "sk-xxxx..."
from openai import OpenAI

def get_client():
    api_key = st.secrets.get("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))
    if not api_key:
        st.error("❗ OPENAI_API_KEY가 설정되어 있지 않습니다. (Streamlit → Edit secrets)")
        st.stop()
    return OpenAI(api_key=api_key)

SYSTEM_PROMPT = """너는 TIPS 선정평가 ‘종합의견’ 작성 보조 도우미다. 출력은 항상 아래 규칙을 따른다.

[출력 포맷(JSON)]
{
  "summary": {
    "기술성": "2~3문장, 중립 표현",
    "사업성": "2~3문장, 중립 표현",
    "연구개발비 조정": "1~2문장, 필요한 경우만",
    "기타사항": "1~2문장"
  },
  "flags": {
    "상이의견": ["기술성","사업성" ...],
    "중복의견제거내역": { "기술성": ["..."], "사업성": [], "연구개발비 조정": [], "기타사항": [] },
    "누락된필수문구": []
  },
  "length": {
    "byte_length": 0,
    "limit": 4000
  }
}

[규칙]
1) 위원별 의견을 의미 기준으로 취합·병합한다. (표현이 달라도 의미가 같으면 하나로 통합)
2) 위원 간 상이한 견해가 있으면 해당 항목을 flags.상이의견에 넣고, summary에는
   “위원 간 의견이 상이함(예: A·B·C)” 식으로 간략히 알린다.
3) 필수 문구(평가단 승인사항, 협약 시 보완사항 등) 목록을 입력으로 받으면, summary에 반드시 포함하고
   포함 못할 경우 flags.누락된필수문구에 이름을 적는다.
4) 문체는 “~으로 판단됨.” “~필요함.” “~없음.” 식으로 행정 보고체로 쓴다.
5) 결과 전체는 4,000바이트를 넘기지 않도록 한다. 넘을 경우 스스로 함축·요약하여 4,000바이트 내로 줄인다.
6) 출력은 반드시 위 JSON 스키마로만 반환한다. 설명·주석·여분 텍스트 금지.
"""

# ========== 2) UI ==========

st.set_page_config(page_title="TIPS 선정평가 종합의견 도우미 (API)", layout="wide")
st.title("TIPS 선정평가 종합의견 도우미 (API)")

with st.sidebar:
    st.markdown("### ⚙️ 설정")
    num_reviewers = st.number_input("평가위원 수", 1, 7, 3)
    req_phrases_raw = st.text_area(
        "필수 문구(한 줄에 하나)", 
        value="평가단 승인사항\n협약 시 보완사항",
        height=120
    )
    req_phrases = [s.strip() for s in req_phrases_raw.splitlines() if s.strip()]
    max_bytes = st.number_input("바이트 제한(UTF-8)", 1000, 8000, 4000, step=100)
    st.caption("※ 결과가 제한을 넘으면 자동으로 요약/압축합니다.")

st.markdown("#### 위원별 의견 입력")
tabs = st.tabs(["기술성", "사업성", "연구개발비 조정", "기타사항"])
inputs = {}
for cat, tab in zip(["기술성", "사업성", "연구개발비 조정", "기타사항"], tabs):
    with tab:
        cols = st.columns(num_reviewers)
        vals = []
        for i, c in enumerate(cols, start=1):
            with c:
                val = st.text_area(f"위원{i}", height=120, key=f"{cat}_{i}")
                vals.append(val.strip())
        inputs[cat] = [v for v in vals if v]

st.divider()

# ========== 3) GPT 호출 함수 ==========

def call_gpt_summarize(client, inputs, required_phrases, max_bytes):
    # user 메시지 구성
    # 사람이 읽는 설명 없이, 기계가 해석하기 쉽도록 명확한 섹션 구조 제공
    def section(cat):
        lines = [f"[{cat}]"]
        for i, txt in enumerate(inputs.get(cat, []), start=1):
            if txt:
                lines.append(f"- 위원{i}: {txt}")
        return "\n".join(lines)

    user_content = "\n\n".join([
        section("기술성"),
        section("사업성"),
        section("연구개발비 조정"),
        section("기타사항"),
        "[필수 문구]",
        *[f"- {p}" for p in required_phrases]
    ])

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0,
        messages=[
            {"role":"system","content":SYSTEM_PROMPT},
            {"role":"user","content":user_content}
        ],
        response_format={"type":"json_object"}
    )
    data = json.loads(resp.choices[0].message.content)

    # 모델이 보고한 길이가 틀릴 수 있으니 실제 바이트 재계산
    full_text = "\n".join([
        data["summary"].get("기술성","").strip(),
        data["summary"].get("사업성","").strip(),
        data["summary"].get("연구개발비 조정","").strip(),
        data["summary"].get("기타사항","").strip(),
    ])
    real_len = len(full_text.encode("utf-8"))
    data["length"]["byte_length"] = real_len
    data["length"]["limit"] = max_bytes

    # 만약 여전히 초과라면 한 번 더 압축 요청
    if real_len > max_bytes:
        resp2 = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[
                {"role":"system","content":"아래 문장을 동일 의미로 더 간결하게 4000바이트 이하로 요약하라. 출력은 JSON {summary:{...}} 만 반환."},
                {"role":"user","content":json.dumps({"summary":data["summary"]}, ensure_ascii=False)}
            ],
            response_format={"type":"json_object"}
        )
        data2 = json.loads(resp2.choices[0].message.content)
        data["summary"] = data2.get("summary", data["summary"])
        full_text = "\n".join([data["summary"].get(k,"") for k in ["기술성","사업성","연구개발비 조정","기타사항"]])
        data["length"]["byte_length"] = len(full_text.encode("utf-8"))

    # 필수 문구 강제 점검(이중 안전장치)
    missing = []
    for p in required_phrases:
        if p not in full_text:
            missing.append(p)
    # 모델이 넣어뒀을 수도 있으니 합집합
    if "누락된필수문구" in data.get("flags", {}):
        missing = sorted(set(missing + data["flags"]["누락된필수문구"]))
    if "flags" not in data:
        data["flags"] = {}
    data["flags"]["누락된필수문구"] = missing

    return data

# ========== 4) 생성 실행 ==========

left, right = st.columns([1,1])
with left:
    if st.button("종합의견 생성", type="primary", use_container_width=True):
        client = get_client()
        with st.spinner("의견 취합 중…"):
            result = call_gpt_summarize(client, inputs, req_phrases, max_bytes)
        st.session_state["result"] = result

with right:
    if "result" in st.session_state:
        result = st.session_state["result"]
        summary = result["summary"]
        flags = result.get("flags", {})
        byte_len = result["length"]["byte_length"]
        limit = result["length"]["limit"]

        st.markdown("### ✅ 종합의견 초안")
        st.text_area(
            "기술성",
            summary.get("기술성","").strip(),
            height=120
        )
        st.text_area(
            "사업성",
            summary.get("사업성","").strip(),
            height=120
        )
        st.text_area(
            "연구개발비 조정",
            summary.get("연구개발비 조정","").strip(),
            height=100
        )
        st.text_area(
            "기타사항",
            summary.get("기타사항","").strip(),
            height=80
        )

        st.caption(f"글자수(바이트): {byte_len} / {limit}")

        # 경고/알림
        warn_cols = st.columns(3)
        with warn_cols[0]:
            if flags.get("상이의견"):
                st.warning("⚠️ 상이의견: " + ", ".join(flags["상이의견"]))
            else:
                st.success("👍 항목 간 상이의견 없음")

        with warn_cols[1]:
            missing = flags.get("누락된필수문구", [])
            if missing:
                st.error("❗ 필수 문구 누락: " + ", ".join(missing))
            else:
                st.success("🔒 필수 문구 포함 완료")

        with warn_cols[2]:
            if byte_len > limit:
                if st.button("글자수 자동 줄이기", use_container_width=True):
                    client = get_client()
                    text_all = "\n".join([
                        summary.get("기술성",""),
                        summary.get("사업성",""),
                        summary.get("연구개발비 조정",""),
                        summary.get("기타사항","")
                    ])
                    resp = client.chat.completions.create(
                        model="gpt-4o-mini",
                        temperature=0,
                        messages=[
                            {"role":"system","content":f"아래 텍스트를 동일 의미로 더 간결하게 {limit}바이트 이하로 요약. 4개 항목 구조(기술성/사업성/연구개발비 조정/기타사항) 유지. JSON {{summary:{{...}}}}만 반환."},
                            {"role":"user","content":text_all}
                        ],
                        response_format={"type":"json_object"}
                    )
                    data2 = json.loads(resp.choices[0].message.content)
                    st.session_state["result"]["summary"] = data2.get("summary", summary)
                    # 화면 갱신
                    st.experimental_rerun()
            else:
                st.info("✅ 바이트 제한 충족")

        # TXT 다운로드
        def compose_txt(s):
            return textwrap.dedent(f"""
            [기술성]
            {s.get('기술성','').strip()}

            [사업성]
            {s.get('사업성','').strip()}

            [연구개발비 조정]
            {s.get('연구개발비 조정','').strip()}

            [기타사항]
            {s.get('기타사항','').strip()}
            """).strip()

        txt = compose_txt(st.session_state["result"]["summary"])
        st.download_button("TXT로 다운로드", data=txt, file_name="종합의견.txt", mime="text/plain")

