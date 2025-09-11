import streamlit as st

st.title("TIPS 선정평가 종합의견 도우미")

st.write("이 앱은 평가위원별 의견을 취합하고 정리하여 간사님의 종합의견 작성 시간을 줄여줍니다.")

# 샘플 입력란
st.header("의견 입력 예시")
tech = st.text_area("기술성 의견")
biz = st.text_area("사업성 의견")
budget = st.text_area("연구개발비 조정 의견")
etc = st.text_area("기타사항")

if st.button("종합의견 생성"):
    summary = f"""
    [기술성] {tech}

    [사업성] {biz}

    [연구개발비 조정] {budget}

    [기타사항] {etc}

    ※ 중복/오탈자 제거 및 글자수 조정 필요
    """
    st.success("종합의견 초안")
    st.write(summary)
