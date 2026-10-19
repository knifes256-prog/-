import json
import re
from io import BytesIO

import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go


# --------------------------------------------------
# 1. 페이지 설정
# --------------------------------------------------

st.set_page_config(
    page_title="대한민국 고령화 지도",
    page_icon="🗺️",
    layout="wide",
)

st.title("🗺️ 대한민국 시군구별 인구 지도")
st.caption("2015~2026년 인구 자료를 이용한 고령인구·유소년인구 비율 분석")


# --------------------------------------------------
# 2. 데이터 주소
# --------------------------------------------------

DATA_URL = (
    "https://raw.githubusercontent.com/first2022-cyber/"
    "contents/main/population_ts_yearly_gender.zip"
)

GEOJSON_URL = (
    "https://raw.githubusercontent.com/first2022-cyber/"
    "contents/main/sigungu_kr.geojson"
)


# --------------------------------------------------
# 3. 데이터 불러오기
# --------------------------------------------------

@st.cache_data
def load_population_data():
    response = requests.get(DATA_URL, timeout=60)
    response.raise_for_status()

    df = pd.read_csv(
        BytesIO(response.content),
        compression="zip",
        encoding="utf-8-sig",
    )

    # 열 이름의 앞뒤 공백 제거
    df.columns = df.columns.astype(str).str.strip()

    return df


@st.cache_data
def load_geojson():
    response = requests.get(GEOJSON_URL, timeout=60)
    response.raise_for_status()

    geojson = response.json()

    # 지도 코드와 이름 정리
    for feature in geojson["features"]:
        properties = feature["properties"]

        code = str(properties["코드"]).strip()
        code = re.sub(r"\.0$", "", code)
        code = code.zfill(5)[:5]

        properties["코드"] = code

    return geojson


try:
    population_df = load_population_data()
    geojson = load_geojson()

except Exception as e:
    st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")
    st.stop()


# --------------------------------------------------
# 4. 필요한 열 찾기
# --------------------------------------------------

def find_column(df, candidates):
    """후보 이름 중 실제 데이터에 존재하는 열을 찾는다."""
    for column in candidates:
        if
