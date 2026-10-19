
import json
import requests
import streamlit as st
import pandas as pd
import plotly.express as px

# -----------------------------
# 페이지 설정
# -----------------------------
st.set_page_config(
    page_title="전국 고령화 단계구분도",
    page_icon="🗺️",
    layout="wide"
)

st.title("전국 고령화 단계구분도")
st.caption("2026년 6월 기준 · 시군구별 65세 이상 인구 비율")

POPULATION_URL = (
    "https://raw.githubusercontent.com/first2022-cyber/"
    "contents/main/population_ts_yearly_gender.zip"
)
GEOJSON_URL = (
    "https://raw.githubusercontent.com/first2022-cyber/"
    "contents/main/sigungu_kr.geojson"
)


# -----------------------------
# 데이터 불러오기
# -----------------------------
@st.cache_data
def load_population():
    # 압축 CSV를 pandas로 직접 읽기
    df = pd.read_csv(POPULATION_URL, compression="zip")

    # 2026년 자료만 선택
    df["연도"] = pd.to_numeric(df["연도"], errors="coerce")
    df = df[df["연도"] == 2026].copy()

    # 코드는 문자열로 처리해 앞자리 0을 보존
    df["코드"] = (
        df["코드"]
        .astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(10)
    )

    # 연도별 데이터에 중복 행이 있더라도 동별 인구를 합산
    # '계_'로 시작하는 나이별 열만 사용
    total_cols = [
        col for col in df.columns
        if col.startswith("계_")
    ]

    # 65세부터 100세 이상까지의 열
    senior_cols = [
        col for col in total_cols
        if (
            col == "계_100세 이상"
            or (
                col.startswith("계_")
                and col.endswith("세")
                and col[2:-1].isdigit()
                and int(col[2:-1]) >= 65
            )
        )
    ]

    if not total_cols or not senior_cols:
        raise ValueError(
            "인구 데이터에서 전체 인구 또는 65세 이상 인구 열을 "
            "찾을 수 없습니다. CSV의 열 이름을 확인해 주세요."
        )

    # 숫자로 변환한 뒤 결측값은 0으로 처리
    for col in total_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # 동 코드의 앞 5자리로 시군구 코드 생성
    df["시군구코드"] = df["코드"].str[:5]

    # 동별 전체 인구와 65세 이상 인구 계산
    df["전체인구"] = df[total_cols].sum(axis=1)
    df["65세이상인구"] = df[senior_cols].sum(axis=1)

    # 시군구별 합계
    result = (
        df.groupby("시군구코드", as_index=False)
        .agg(
            전체인구=("전체인구", "sum"),
            65세이상인구=("65세이상인구", "sum")
        )
    )

    # 0으로 나누는 오류 방지
    result["고령화율"] = (
        result["65세이상인구"]
        .div(result["전체인구"].replace(0, pd.NA))
        .mul(100)
    )

    result["고령화율"] = result["고령화율"].astype(float)

    return result


@st.cache_data
def load_geojson():
    response = requests.get(GEOJSON_URL, timeout=30)
    response.raise_for_status()
    geojson = response.json()

    # GeoJSON의 코드도 문자열 5자리로 통일
    for feature in geojson["features"]:
        properties = feature["properties"]
        code = str(properties["코드"]).strip()
        code = code.removesuffix(".0").zfill(5)
        properties["코드"] = code

    return geojson


# -----------------------------
# 앱 실행
# -----------------------------
try:
    with st.spinner("인구 데이터와 시군구 경계를 불러오는 중..."):
        population = load_population()
        geojson = load_geojson()

    # 경계 데이터의 코드와 인구 데이터의 코드를 정확히 연결
    geo_codes = {
        feature["properties"]["코드"]
        for feature in geojson["features"]
    }
    population_codes = set(population["시군구코드"])

    # 인구 데이터가 있는 지역만 지도에 표시
    map_df = population[
        population["시군구코드"].isin(geo_codes)
    ].copy()

    # 데이터가 없는 지역은 회색으로 표시하기 위해
    # GeoJSON의 모든 지역을 기준으로 데이터 병합
    boundary_df = pd.DataFrame([
        {
            "코드": feature["properties"]["코드"],
            "시군구": feature["properties"]["시군구"],
            "시도": feature["properties"]["시도"],
        }
        for feature in geojson["features"]
    ])

    map_df = boundary_df.merge(
        population,
        left_on="코드",
        right_on="시군구코드",
        how="left",
        validate="one_to_one"
    )

    matched_count = map_df["고령화율"].notna().sum()
    unmatched_count = map_df["고령화율"].isna().sum()

    # -----------------------------
    # 요약 지표
    # -----------------------------
    valid = map_df.dropna(subset=["고령화율"])

    if valid.empty:
        st.error(
            "GeoJSON과 인구 데이터의 코드가 일치하지 않습니다. "
            "각 데이터의 코드 형식을 확인해 주세요."
        )
        st.stop()

    national_rate = (
        valid["65세이상인구"].sum()
        / valid["전체인구"].sum()
        * 100
        if valid["전체인구"].sum() > 0
        else 0
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("전국 고령화율", f"{national_rate:.2f}%")
    col2.metric("매칭된 시군구", f"{matched_count:,}곳")
    col3.metric("인구 자료 미매칭", f"{unmatched_count:,}곳")

    # -----------------------------
    # 단계구분도
    # -----------------------------
    fig = px.choropleth(
        map_df,
        geojson=geojson,
        locations="코드",
        featureidkey="properties.코드",
        color="고령화율",
        color_continuous_scale="YlOrRd",
        hover_name="시군구",
        hover_data={
            "코드": False,
            "시도": True,
            "고령화율": ":.2f",
            "전체인구": ":,.0f",
            "65세이상인구": ":,.0f",
        },
        labels={
            "시도": "시도",
            "고령화율": "고령화율(%)",
            "전체인구": "전체 인구",
            "65세이상인구": "65세 이상 인구",
        },
        title="시군구별 65세 이상 인구 비율"
    )

    # 지도 타일 없이 경계와 색상만 표시
    fig.update_geos(
        visible=False,
        fitbounds="locations",
        showcountries=False,
        showcoastlines=False,
        showland=False,
        bgcolor="rgba(0,0,0,0)"
    )

    fig.update_traces(
        marker_line_color="white",
        marker_line_width=0.5,
        hovertemplate=(
            "<b>%{hovertext}</b><br>"
            "시도: %{customdata[0]}<br>"
            "고령화율: %{z:.2f}%<br>"
            "<extra></extra>"
        )
    )

    # 데이터가 없는 지역은 별도 표시
    missing_codes = set(
        map_df.loc[map_df["고령화율"].isna(), "코드"]
    )

    if missing_codes:
        missing_geojson = {
            "type": "FeatureCollection",
            "features": [
                feature for feature in geojson["features"]
                if feature["properties"]["코드"] in missing_codes
            ]
        }

        fig.add_trace(
            px.choropleth(
                boundary_df[
                    boundary_df["코드"].isin(missing_codes)
                ],
                geojson=missing_geojson,
                locations="코드",
                featureidkey="properties.코드",
            ).data[0]
        )

        fig.data[-1].update(
            z=None,
            showscale=False,
            colorscale=[[0, "#D9D9D9"], [1, "#D9D9D9"]],
            marker_line_color="white",
            marker_line_width=0.5,
            hovertemplate=(
                "<b>%{location}</b><br>"
                "인구 자료 없음"
                "<extra></extra>"
            )
        )

    fig.update_layout(
        height=750,
        margin=dict(l=0, r=0, t=60, b=0),
        coloraxis_colorbar=dict(
            title="고령화율(%)",
            ticksuffix="%"
        ),
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={"scrollZoom": True}
    )

    st.caption(
        "색이 진할수록 65세 이상 인구 비율이 높습니다. "
        "회색 지역은 인구 자료가 연결되지 않은 지역입니다."
    )

    # -----------------------------
    # 시군구별 표
    # -----------------------------
    st.subheader("시군구별 고령화율")

    table_df = (
        map_df.dropna(subset=["고령화율"])
        [["시도", "시군구", "코드", "전체인구",
          "65세이상인구", "고령화율"]]
        .sort_values("고령화율", ascending=False)
        .reset_index(drop=True)
    )

    st.dataframe(
        table_df.style.format({
            "전체인구": "{:,.0f}",
            "65세이상인구": "{:,.0f}",
            "고령화율": "{:.2f}%"
        }),
        use_container_width=True,
        hide_index=True
    )

    csv = table_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "시군구별 고령화율 CSV 다운로드",
        data=csv,
        file_name="2026_시군구별_고령화율.csv",
        mime="text/csv"
    )

except Exception as e:
    st.error(f"데이터 처리 중 오류가 발생했습니다: {e}")
    st.info(
        "GitHub 데이터 주소, CSV 열 이름, GeoJSON의 코드 속성을 "
        "확인해 주세요."
    )

