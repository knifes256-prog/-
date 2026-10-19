import requests
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# -----------------------------
# 페이지 설정
# -----------------------------
st.set_page_config(
    page_title="전국 고령화 단계구분도",
    page_icon="🗺️",
    layout="wide",
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
# 코드 정리
# -----------------------------
def normalize_code(value, length):
    if pd.isna(value):
        return None

    code = str(value).strip()

    if code.endswith(".0"):
        code = code[:-2]

    if not code.isdigit():
        return None

    return code.zfill(length)


# -----------------------------
# 인구 데이터 불러오기
# -----------------------------
@st.cache_data
def load_population():
    df = pd.read_csv(
        POPULATION_URL,
        compression="zip",
        dtype={"코드": "string"},
    )

    required = {"연도", "코드"}
    if not required.issubset(df.columns):
        raise ValueError(
            f"필수 열이 없습니다: {required - set(df.columns)}"
        )

    # 2026년 자료만 선택
    df["연도"] = pd.to_numeric(df["연도"], errors="coerce")
    df = df[df["연도"] == 2026].copy()

    if df.empty:
        raise ValueError("2026년 인구 자료가 없습니다.")

    # 코드를 문자열로 통일
    df["코드"] = df["코드"].map(
        lambda x: normalize_code(x, 10)
    )
    df = df[df["코드"].notna()].copy()

    # 전체 인구 열
    total_cols = [
        col for col in df.columns
        if col.startswith("계_")
    ]

    # 65세 이상 인구 열
    senior_cols = []

    for col in total_cols:
        age_label = col[2:]

        if age_label == "100세 이상":
            senior_cols.append(col)
        elif age_label.endswith("세"):
            age_text = age_label[:-1]

            if age_text.isdigit() and int(age_text) >= 65:
                senior_cols.append(col)

    if not total_cols:
        raise ValueError("'계_'로 시작하는 인구 열이 없습니다.")

    if not senior_cols:
        raise ValueError("65세 이상 인구 열을 찾지 못했습니다.")

    # 인구 열을 숫자로 변환
    for col in total_cols:
        df[col] = pd.to_numeric(
            df[col], errors="coerce"
        ).fillna(0)

    # 동 코드 앞 5자리로 시군구 코드 생성
    df["시군구코드"] = df["코드"].str[:5]

    df["전체인구"] = df[total_cols].sum(axis=1)
    df["65세이상인구"] = df[senior_cols].sum(axis=1)

    # 시군구별 합계
    result = (
        df.groupby("시군구코드", as_index=False)
        .agg(
            전체인구=("전체인구", "sum"),
            65세이상인구=("65세이상인구", "sum"),
        )
    )

    # 전체 인구가 0인 경우 비율은 결측값으로 처리
    denominator = result["전체인구"].where(
        result["전체인구"] != 0
    )

    result["고령화율"] = (
        result["65세이상인구"] / denominator * 100
    )

    return result


# -----------------------------
# GeoJSON 불러오기
# -----------------------------
@st.cache_data
def load_geojson():
    response = requests.get(
        GEOJSON_URL,
        timeout=60,
    )
    response.raise_for_status()

    geojson = response.json()

    if "features" not in geojson:
        raise ValueError("GeoJSON에 features가 없습니다.")

    for feature in geojson["features"]:
        properties = feature.get("properties", {})

        if "코드" not in properties:
            raise ValueError("GeoJSON에 '코드' 속성이 없습니다.")

        properties["코드"] = normalize_code(
            properties["코드"], 5
        )

    return geojson


# -----------------------------
# 앱 실행
# -----------------------------
try:
    with st.spinner("인구 데이터와 지도를 불러오는 중입니다..."):
        population = load_population()
        geojson = load_geojson()

    # GeoJSON의 모든 시군구를 기준으로 데이터 구성
    boundary_rows = []

    for feature in geojson["features"]:
        properties = feature["properties"]

        boundary_rows.append({
            "코드": properties["코드"],
            "시군구": properties.get("시군구", "이름 없음"),
            "시도": properties.get("시도", "시도 미상"),
        })

    boundary_df = pd.DataFrame(boundary_rows)

    # 중복 경계 코드 제거
    boundary_df = boundary_df.drop_duplicates(
        subset=["코드"]
    )

    # 인구 데이터와 코드 기준으로 연결
    map_df = boundary_df.merge(
        population,
        left_on="코드",
        right_on="시군구코드",
        how="left",
        validate="one_to_one",
    )

    valid = map_df.dropna(
        subset=["고령화율"]
    ).copy()

    missing = map_df[
        map_df["고령화율"].isna()
    ].copy()

    if valid.empty:
        st.error(
            "인구 데이터와 GeoJSON의 코드가 일치하지 않습니다. "
            "두 데이터의 코드 형식을 확인해 주세요."
        )
        st.stop()

    # -----------------------------
    # 요약 지표
    # -----------------------------
    total_population = valid["전체인구"].sum()
    senior_population = valid["65세이상인구"].sum()

    national_rate = (
        senior_population / total_population * 100
        if total_population > 0
        else 0
    )

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "전국 고령화율",
        f"{national_rate:.2f}%",
    )
    col2.metric(
        "매칭된 시군구",
        f"{len(valid):,}곳",
    )
    col3.metric(
        "인구 자료 미매칭",
        f"{len(missing):,}곳",
    )

    # -----------------------------
    # 단계구분도
    # -----------------------------
    fig = go.Figure()

    # 인구 자료가 있는 지역
    fig.add_trace(
        go.Choropleth(
            geojson=geojson,
            locations=valid["코드"],
            z=valid["고령화율"],
            featureidkey="properties.코드",
            colorscale="YlOrRd",
            zmin=0,
            zmax=50,
            marker_line_color="white",
            marker_line_width=0.5,
            colorbar=dict(
                title="고령화율(%)",
                ticksuffix="%",
            ),
            customdata=valid[
                ["시군구", "시도", "전체인구", "65세이상인구"]
            ].to_numpy(),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "시도: %{customdata[1]}<br>"
                "고령화율: %{z:.2f}%<br>"
                "전체 인구: %{customdata[2]:,.0f}명<br>"
                "65세 이상 인구: %{customdata[3]:,.0f}명"
                "<extra></extra>"
            ),
            name="고령화율",
        )
    )

    # 인구 자료가 없는 지역은 회색으로 표시
    if not missing.empty:
        missing_codes = set(missing["코드"])

        missing_features = [
            feature
            for feature in geojson["features"]
            if feature["properties"]["코드"] in missing_codes
        ]

        missing_geojson = {
            "type": "FeatureCollection",
            "features": missing_features,
        }

        fig.add_trace(
            go.Choropleth(
                geojson=missing_geojson,
                locations=missing["코드"],
                z=[0] * len(missing),
                featureidkey="properties.코드",
                zmin=0,
                zmax=1,
                colorscale=[
                    [0, "#D9D9D9"],
                    [1, "#D9D9D9"],
                ],
                showscale=False,
                marker_line_color="white",
                marker_line_width=0.5,
                customdata=missing[
                    ["시군구", "시도"]
                ].to_numpy(),
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "시도: %{customdata[1]}<br>"
                    "인구 자료 없음"
                    "<extra></extra>"
                ),
                name="자료 없음",
            )
        )

    # 배경 타일 없이 경계만 표시
    fig.update_geos(
        visible=False,
        fitbounds="locations",
        showcountries=False,
        showcoastlines=False,
        showland=False,
        bgcolor="rgba(0,0,0,0)",
    )

    fig.update_layout(
        title="시군구별 65세 이상 인구 비율",
        height=750,
        margin=dict(l=0, r=0, t=60, b=0),
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={"scrollZoom": True},
    )

    st.caption(
        "색이 진할수록 고령화율이 높습니다. "
        "회색 지역은 인구 자료가 연결되지 않은 지역입니다."
    )

    if not missing.empty:
        st.warning(
            f"총 {len(missing)}개 시군구에 인구 자료가 연결되지 "
            "않았습니다. 행정구역 코드 변경이나 원본 데이터의 "
            "코드 형식을 확인해 주세요."
        )

    # -----------------------------
    # 시군구별 표
    # -----------------------------
    st.subheader("시군구별 고령화율")

    table_df = (
        valid[
            [
                "시도",
                "시군구",
                "코드",
                "전체인구",
                "65세이상인구",
                "고령화율",
            ]
        ]
        .sort_values(
            "고령화율",
            ascending=False,
        )
        .reset_index(drop=True)
    )

    st.dataframe(
        table_df.style.format({
            "전체인구": "{:,.0f}",
            "65세이상인구": "{:,.0f}",
            "고령화율": "{:.2f}%",
        }),
        use_container_width=True,
        hide_index=True,
    )

    # -----------------------------
    # CSV 다운로드
    # -----------------------------
    csv = table_df.to_csv(
        index=False
    ).encode("utf-8-sig")

    st.download_button(
        "시군구별 고령화율 CSV 다운로드",
        data=csv,
        file_name="2026_시군구별_고령화율.csv",
        mime="text/csv",
    )

except Exception as e:
    st.error("데이터 처리 중 오류가 발생했습니다.")
    st.code(f"{type(e).__name__}: {e}")
    st.info(
        "오류가 계속되면 위 오류 메시지를 복사해서 보내 주세요. "
        "원인을 확인해 추가로 수정할 수 있습니다."
    )
