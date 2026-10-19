
import json
import re
from io import BytesIO

import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go


# ==================================================
# 1. 페이지 설정
# ==================================================

st.set_page_config(
    page_title="대한민국 인구 지도",
    page_icon="🗺️",
    layout="wide",
)

st.title("🗺️ 대한민국 시군구별 인구 지도")
st.caption("2015~2026년 고령인구 및 유소년인구 비율 분석")


# ==================================================
# 2. 데이터 주소
# ==================================================

DATA_URL = (
    "https://raw.githubusercontent.com/first2022-cyber/"
    "contents/main/population_ts_yearly_gender.zip"
)

GEOJSON_URL = (
    "https://raw.githubusercontent.com/first2022-cyber/"
    "contents/main/sigungu_kr.geojson"
)


# ==================================================
# 3. 데이터 불러오기
# ==================================================

@st.cache_data
def load_population_data():
    response = requests.get(DATA_URL, timeout=90)
    response.raise_for_status()

    df = pd.read_csv(
        BytesIO(response.content),
        compression="zip",
        encoding="utf-8-sig",
    )

    df.columns = df.columns.astype(str).str.strip()
    return df


@st.cache_data
def load_geojson():
    response = requests.get(GEOJSON_URL, timeout=90)
    response.raise_for_status()

    geojson = response.json()

    for feature in geojson["features"]:
        props = feature["properties"]

        code = str(props["코드"]).strip()
        code = re.sub(r"\.0$", "", code)

        props["코드"] = code.zfill(5)[:5]

    return geojson


try:
    raw_df = load_population_data()
    geojson = load_geojson()

except Exception as e:
    st.error(f"데이터를 불러오지 못했습니다: {e}")
    st.stop()


# ==================================================
# 4. 필요한 열 찾기
# ==================================================

def find_column(df, candidates):
    for name in candidates:
        if name in df.columns:
            return name
    return None


code_column = find_column(
    raw_df,
    [
        "행정구역코드",
        "시군구코드",
        "지역코드",
        "법정동코드",
        "코드",
    ],
)

year_column = find_column(
    raw_df,
    [
        "연도",
        "년도",
        "기준연도",
        "년",
        "시점",
    ],
)

if code_column is None:
    st.error(
        "행정구역 코드 열을 찾지 못했습니다.\n\n"
        f"현재 열 이름: {list(raw_df.columns)}"
    )
    st.stop()

if year_column is None:
    st.error(
        "연도 열을 찾지 못했습니다.\n\n"
        f"현재 열 이름: {list(raw_df.columns)}"
    )
    st.stop()


# ==================================================
# 5. 연도 및 행정구역 코드 정리
# ==================================================

raw_df["연도"] = pd.to_numeric(
    raw_df[year_column]
    .astype(str)
    .str.extract(r"(20\d{2})", expand=False),
    errors="coerce",
)

raw_df = raw_df.dropna(subset=["연도"]).copy()
raw_df["연도"] = raw_df["연도"].astype(int)


def normalize_code(value):
    if pd.isna(value):
        return None

    code = str(value).strip()
    code = re.sub(r"\.0$", "", code)

    if not code.isdigit():
        return None

    code = code.zfill(5)[:5]

    # 군위군 코드 변경
    if code == "47720":
        code = "27720"

    # 강원특별자치도 및 전북특별자치도 코드 변경
    elif code.startswith("42"):
        code = "51" + code[2:]

    elif code.startswith("45"):
        code = "52" + code[2:]

    return code


raw_df["시군구코드"] = raw_df[code_column].apply(normalize_code)

raw_df = raw_df.dropna(
    subset=["시군구코드"]
).copy()


# ==================================================
# 6. 연령별 인구 열 확인
# ==================================================

def get_age(column):
    match = re.search(r"계_(\d+)\s*세", column)

    if match:
        return int(match.group(1))

    return None


age_columns = []

for column in raw_df.columns:
    if not column.startswith("계_"):
        continue

    age = get_age(column)

    if age is not None:
        age_columns.append(column)


if not age_columns:
    st.error(
        "연령별 인구 열을 찾지 못했습니다. "
        "예상 형식: 계_0세, 계_1세, 계_65세"
    )
    st.stop()


elderly_columns = [
    column
    for column in age_columns
    if get_age(column) >= 65
]

youth_columns = [
    column
    for column in age_columns
    if get_age(column) <= 14
]

if not elderly_columns:
    st.error("65세 이상 인구 열이 없습니다.")
    st.stop()

if not youth_columns:
    st.error("0~14세 인구 열이 없습니다.")
    st.stop()


# 인구 열을 숫자로 변환
for column in age_columns:
    raw_df[column] = pd.to_numeric(
        raw_df[column]
        .astype(str)
        .str.replace(",", "", regex=False),
        errors="coerce",
    ).fillna(0)


# ==================================================
# 7. 인구 집계
# ==================================================

raw_df["전체인구"] = raw_df[age_columns].sum(axis=1)
raw_df["고령인구"] = raw_df[elderly_columns].sum(axis=1)
raw_df["유소년인구"] = raw_df[youth_columns].sum(axis=1)

# 주의: 숫자로 시작하는 이름을 agg()의 인자명으로 쓰지 않는다.
# 임시 이름으로 집계한 뒤 원래 열 이름으로 바꾼다.
result = (
    raw_df.groupby(
        ["연도", "시군구코드"],
        as_index=False,
    )
    .agg(
        전체인구=("전체인구", "sum"),
        senior_population=("고령인구", "sum"),
        youth_population=("유소년인구", "sum"),
    )
    .rename(
        columns={
            "senior_population": "65세이상인구",
            "youth_population": "유소년인구",
        }
    )
)

result["고령인구비율"] = (
    result["65세이상인구"]
    .div(result["전체인구"].replace(0, float("nan")))
    * 100
)

result["유소년인구비율"] = (
    result["유소년인구"]
    .div(result["전체인구"].replace(0, float("nan")))
    * 100
)


# ==================================================
# 8. 지도 데이터 정리
# ==================================================

geo_rows = []

for feature in geojson["features"]:
    props = feature["properties"]

    geo_rows.append(
        {
            "시군구코드": props["코드"],
            "시도": props.get("시도", "미상"),
            "시군구": props.get("시군구", "미상"),
        }
    )

geo_df = pd.DataFrame(geo_rows)

geo_df = geo_df.drop_duplicates(
    subset=["시군구코드"]
).copy()


# ==================================================
# 9. 사이드바 설정
# ==================================================

st.sidebar.header("지도 설정")

available_years = sorted(
    year
    for year in result["연도"].unique()
    if 2015 <= year <= 2026
)

if not available_years:
    st.error("2015~2026년 자료를 찾지 못했습니다.")
    st.stop()


# 연도 슬라이더
selected_year = st.sidebar.select_slider(
    "분석 연도",
    options=available_years,
    value=max(available_years),
    format_func=lambda year: f"{year}년",
)


# 분석 지표 선택
metric_label = st.sidebar.selectbox(
    "분석 지표",
    [
        "고령인구 비율 (65세 이상)",
        "유소년인구 비율 (0~14세)",
    ],
)

if metric_label == "고령인구 비율 (65세 이상)":
    metric_column = "고령인구비율"
    count_column = "65세이상인구"

    # 고령인구 비율은 모든 연도에서 같은 경계값 사용
    thresholds = [19, 23, 28, 38]

    legend_title = "고령인구 비율"

else:
    metric_column = "유소년인구비율"
    count_column = "유소년인구"

    # 유소년인구 비율은 고령인구보다 낮으므로 별도 구간 사용
    thresholds = [5, 8, 11, 14]

    legend_title = "유소년인구 비율"


# 시도 선택
province_names = sorted(
    geo_df["시도"].dropna().unique().tolist()
)

selected_province = st.sidebar.selectbox(
    "시도 선택",
    ["전국"] + province_names,
)


# ==================================================
# 10. 연도별 자료와 지도 연결
# ==================================================

year_df = result[
    result["연도"] == selected_year
].copy()

map_df = geo_df.merge(
    year_df,
    on="시군구코드",
    how="left",
)

if selected_province != "전국":
    map_df = map_df[
        map_df["시도"] == selected_province
    ].copy()

if map_df.empty:
    st.warning("선택한 지역의 지도 자료가 없습니다.")
    st.stop()


selected_codes = set(map_df["시군구코드"])

selected_features = [
    feature
    for feature in geojson["features"]
    if feature["properties"]["코드"] in selected_codes
]

selected_geojson = {
    "type": "FeatureCollection",
    "features": selected_features,
}


# ==================================================
# 11. 통계 계산
# ==================================================

# 첫 번째 카드에는 항상 전국 고령화율 표시
national_total = year_df["전체인구"].sum()
national_elderly = year_df["65세이상인구"].sum()

national_aging_rate = (
    national_elderly / national_total * 100
    if national_total > 0
    else 0
)

# 두 번째와 세 번째 카드는 현재 선택한 지표 기준
valid_df = map_df.dropna(
    subset=[metric_column]
).copy()

if not valid_df.empty:
    highest = valid_df.loc[
        valid_df[metric_column].idxmax()
    ]

    lowest = valid_df.loc[
        valid_df[metric_column].idxmin()
    ]

    highest_name = f"{highest['시도']} {highest['시군구']}"
    lowest_name = f"{lowest['시도']} {lowest['시군구']}"

    highest_rate = float(highest[metric_column])
    lowest_rate = float(lowest[metric_column])

else:
    highest_name = "자료 없음"
    lowest_name = "자료 없음"
    highest_rate = 0
    lowest_rate = 0


# ==================================================
# 12. 지도 위 통계 카드 3개
# ==================================================

st.subheader(f"{selected_year}년 인구 현황")

card1, card2, card3 = st.columns(3)

with card1:
    st.metric(
        "전국 고령화율",
        f"{national_aging_rate:.2f}%",
    )

with card2:
    st.metric(
        f"{metric_label} 최고",
        highest_name,
        f"{highest_rate:.2f}%",
    )

with card3:
    st.metric(
        f"{metric_label} 최저",
        lowest_name,
        f"{lowest_rate:.2f}%",
    )


# ==================================================
# 13. 고정 색상 구간
# ==================================================

palette = [
    "#f7fbff",
    "#deebf7",
    "#9ecae1",
    "#4292c6",
    "#084594",
]


def make_discrete_colorscale(breaks, colors):
    """
    각 경계값에서 색이 바뀌도록 색상표를 만든다.
    연도가 달라져도 같은 지표의 색 구간은 변하지 않는다.
    """
    boundaries = [0] + breaks + [100]
    scale = []

    for index, color in enumerate(colors):
        left = boundaries[index] / 100
        right = boundaries[index + 1] / 100

        scale.append([left, color])
        scale.append([right, color])

    return scale


colorscale = make_discrete_colorscale(
    thresholds,
    palette,
)


# ==================================================
# 14. 지도 만들기
# ==================================================

fig = go.Figure()

matched_df = map_df.dropna(
    subset=[metric_column]
).copy()

matched_codes = set(
    matched_df["시군구코드"]
)

if not matched_df.empty:
    customdata = matched_df[
        [
            "시도",
            "시군구",
            "전체인구",
            count_column,
        ]
    ].to_numpy()

    fig.add_trace(
        go.Choropleth(
            geojson=selected_geojson,
            locations=matched_df["시군구코드"],
            z=matched_df[metric_column],
            featureidkey="properties.코드",
            colorscale=colorscale,
            zmin=0,
            zmax=100,
            marker_line_color="white",
            marker_line_width=0.5,
            colorbar={
                "title": f"{legend_title} (%)",
                "tickvals": [0] + thresholds + [50, 100],
            },
            customdata=customdata,
            hovertemplate=(
                "<b>%{customdata[0]} %{customdata[1]}</b><br>"
                f"{metric_label}: %{{z:.2f}}%<br>"
                "전체 인구: %{customdata[2]:,.0f}명<br>"
                "해당 인구: %{customdata[3]:,.0f}명"
                "<extra></extra>"
            ),
            name=metric_label,
        )
    )


# ==================================================
# 15. 자료가 연결되지 않은 지역은 회색으로 표시
# ==================================================

unmatched_codes = [
    code
    for code in map_df["시군구코드"]
    if code not in matched_codes
]

if unmatched_codes:
    fig.add_trace(
        go.Choropleth(
            geojson=selected_geojson,
            locations=unmatched_codes,
            z=[0] * len(unmatched_codes),
            featureidkey="properties.코드",
            colorscale=[
                [0, "#d9d9d9"],
                [1, "#d9d9d9"],
            ],
            showscale=False,
            marker_line_color="white",
            marker_line_width=0.5,
            hovertemplate=(
                "인구 자료 연결 안 됨"
                "<extra></extra>"
            ),
            name="자료 없음",
        )
    )


# ==================================================
# 16. 지도 레이아웃
# ==================================================

fig.update_geos(
    fitbounds="locations",
    visible=False,
    showcountries=False,
    showcoastlines=False,
    showland=True,
    landcolor="#f5f5f5",
)

fig.update_layout(
    height=720,
    margin=dict(l=0, r=0, t=20, b=0),
    paper_bgcolor="white",
    plot_bgcolor="white",
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=0.01,
        xanchor="left",
        x=0.01,
    ),
)

st.plotly_chart(
    fig,
    use_container_width=True,
)


# ==================================================
# 17. 지도 아래 안내 문구
# ==================================================

if unmatched_codes:
    st.warning(
        f"선택한 지역 중 {len(unmatched_codes)}개 시군구는 "
        "인구 자료와 지도 경계 파일의 코드가 일치하지 않습니다. "
        "해당 지역은 회색으로 표시됩니다. "
        "행정구역 개편이나 코드 체계 차이로 발생할 수 있습니다."
    )
else:
    st.success(
        "선택한 지역의 지도와 인구 자료가 모두 연결되었습니다."
    )


# ==================================================
# 18. 시군구별 상세 자료 및 CSV 다운로드
# ==================================================

st.subheader("시군구별 상세 자료")

table_columns = [
    "시도",
    "시군구",
    "전체인구",
    "65세이상인구",
    "고령인구비율",
    "유소년인구",
    "유소년인구비율",
]

table_df = map_df[table_columns].copy()

table_df = table_df.rename(
    columns={
        "전체인구": "전체 인구",
        "65세이상인구": "65세 이상 인구",
        "고령인구비율": "고령인구 비율(%)",
        "유소년인구": "0~14세 인구",
        "유소년인구비율": "유소년인구 비율(%)",
    }
)

sort_column = (
    "고령인구 비율(%)"
    if metric_column == "고령인구비율"
    else "유소년인구 비율(%)"
)

table_df = table_df.sort_values(
    by=sort_column,
    ascending=False,
    na_position="last",
)

st.dataframe(
    table_df,
    use_container_width=True,
    hide_index=True,
)

st.download_button(
    label="상세 자료 CSV 다운로드",
    data=table_df.to_csv(
        index=False,
    ).encode("utf-8-sig"),
    file_name=f"인구현황_{selected_year}.csv",
    mime="text/csv",
)
