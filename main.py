from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# ============================================================
# 1. 기본 설정
# ============================================================

st.set_page_config(
    page_title="우리 동네 인구 피라미드",
    page_icon="🏡",
    layout="wide",
)

# 압축된 CSV 파일 경로
# 실제 파일명에 확장자가 없어도 읽을 수 있도록 여러 방식을 시도합니다.
DATA_PATH = Path(
    r"C:\Users\컴실\Downloads\population_ts_yearly_gender"
)

# 인구 피라미드에 사용할 나이 라벨을 0세부터 순서대로 만듭니다.
# 0~99세는 개별 나이이고, 마지막은 100세 이상입니다.
AGES = [f"{age}세" for age in range(100)] + ["100세 이상"]


# ============================================================
# 2. CSV 파일 읽기
# ============================================================

@st.cache_data
def load_data(file_path):
    """CSV 파일을 읽고 열 이름과 데이터 형식을 정리합니다."""

    # 파일 확장자가 없거나 압축 형식을 자동으로 판별하지 못하는
    # 경우를 대비해 여러 압축 방식을 차례로 시도합니다.
    compression_options = [
        "infer",
        "gzip",
        "zip",
        "bz2",
        "xz",
        None,
    ]

    errors = []

    for compression in compression_options:
        try:
            df = pd.read_csv(
                file_path,
                compression=compression,
                low_memory=False,
            )

            # 열 이름 앞뒤에 공백이 있으면 제거합니다.
            df.columns = df.columns.astype(str).str.strip()

            # 정상적으로 읽었다면 데이터 반환
            return df

        except Exception as error:
            errors.append(
                f"{compression}: {error}"
            )

    # 모든 방식이 실패한 경우 오류 내용을 알려줍니다.
    raise ValueError(
        "CSV 파일을 읽지 못했습니다.\n"
        + "\n".join(errors)
    )


# ============================================================
# 3. 화면 제목과 안내 문구
# ============================================================

st.title("🏡 우리 동네 인구 피라미드")

st.markdown(
    """
    시도, 시군구, 동을 차례대로 선택하면 해당 지역의
    **최신 연도 남녀별 인구 구조**를 확인할 수 있습니다.

    - 🟠 남자: 왼쪽
    - 🌸 여자: 오른쪽
    - 👶 아래쪽: 어린 나이
    - 👵 위쪽: 높은 나이
    """
)

st.divider()


# ============================================================
# 4. 데이터 불러오기 및 확인
# ============================================================

try:
    df = load_data(DATA_PATH)

except Exception as error:
    st.error(
        "데이터 파일을 불러오지 못했습니다. "
        "파일 경로와 압축 형식을 확인해 주세요."
    )
    st.code(str(error))
    st.stop()


# 지역 및 연도 열이 있는지 확인합니다.
required_columns = ["연도", "시도", "시군구", "동"]

missing_columns = [
    column
    for column in required_columns
    if column not in df.columns
]

if missing_columns:
    st.error(
        "필요한 열을 찾을 수 없습니다: "
        + ", ".join(missing_columns)
    )
    st.write("현재 파일의 열 이름:", df.columns.tolist())
    st.stop()


# 연도 열을 숫자로 변환합니다.
# 숫자로 변환할 수 없는 값은 결측값으로 처리합니다.
df["연도"] = pd.to_numeric(
    df["연도"],
    errors="coerce",
)

df = df.dropna(subset=["연도"]).copy()
df["연도"] = df["연도"].astype(int)

if df.empty:
    st.error("데이터에 유효한 연도 정보가 없습니다.")
    st.stop()


# ============================================================
# 5. 가장 최신 연도만 선택
# ============================================================

# 파일에 실제로 들어 있는 연도 중 가장 큰 연도를 선택합니다.
latest_year = int(df["연도"].max())

# 최신 연도의 행만 남깁니다.
latest_df = df.loc[
    df["연도"] == latest_year
].copy()

st.success(
    f"📅 분석 연도: {latest_year}년 "
    f"(파일에서 확인된 가장 최신 연도)"
)


# ============================================================
# 6. 나이별 남녀 인구 열 확인
# ============================================================

# 예: 남_0세, 여_0세, 남_100세 이상, 여_100세 이상
male_columns = [f"남_{age}" for age in AGES]
female_columns = [f"여_{age}" for age in AGES]

population_columns = male_columns + female_columns

# 필요한 인구 열이 누락되었는지 확인합니다.
missing_population_columns = [
    column
    for column in population_columns
    if column not in latest_df.columns
]

if missing_population_columns:
    st.error(
        "다음 인구 열이 데이터에 없습니다. "
        "실제 CSV의 열 이름을 확인해 주세요."
    )
    st.write(missing_population_columns)
    st.stop()


# 인구 열을 숫자로 변환합니다.
# 숫자가 아닌 값이나 결측값은 0으로 처리합니다.
for column in population_columns:
    latest_df[column] = pd.to_numeric(
        latest_df[column],
        errors="coerce",
    ).fillna(0)


# 지역 이름의 공백을 정리합니다.
for column in ["시도", "시군구", "동"]:
    latest_df[column] = (
        latest_df[column]
        .fillna("")
        .astype(str)
        .str.strip()
    )


# ============================================================
# 7. 시도 → 시군구 → 동 드롭다운
# ============================================================

st.subheader("📍 지역 선택")

# 첫 번째 드롭다운: 시도
sido_list = sorted(
    latest_df.loc[
        latest_df["시도"] != "", "시도"
    ].unique().tolist()
)

if not sido_list:
    st.error("선택할 수 있는 시도 데이터가 없습니다.")
    st.stop()

selected_sido = st.selectbox(
    "① 시도",
    options=sido_list,
    key="selected_sido",
)

# 선택한 시도에 속하는 행만 남깁니다.
sido_df = latest_df.loc[
    latest_df["시도"] == selected_sido
].copy()

# 두 번째 드롭다운: 시군구
sigungu_list = sorted(
    sido_df.loc[
        sido_df["시군구"] != "", "시군구"
    ].unique().tolist()
)

if not sigungu_list:
    st.warning("선택한 시도에 시군구 데이터가 없습니다.")
    st.stop()

selected_sigungu = st.selectbox(
    "② 시군구",
    options=sigungu_list,
    key="selected_sigungu",
)

# 선택한 시군구에 속하는 행만 남깁니다.
sigungu_df = sido_df.loc[
    sido_df["시군구"] == selected_sigungu
].copy()

# 세 번째 드롭다운: 동
dong_list = sorted(
    sigungu_df.loc[
        sigungu_df["동"] != "", "동"
    ].unique().tolist()
)

if not dong_list:
    st.warning("선택한 시군구에 동 데이터가 없습니다.")
    st.stop()

selected_dong = st.selectbox(
    "③ 동",
    options=dong_list,
    key="selected_dong",
)


# ============================================================
# 8. 선택한 동네의 인구 데이터 추출
# ============================================================

selected_df = latest_df.loc[
    (latest_df["시도"] == selected_sido)
    & (latest_df["시군구"] == selected_sigungu)
    & (latest_df["동"] == selected_dong)
].copy()

if selected_df.empty:
    st.warning("선택한 지역의 인구 데이터를 찾을 수 없습니다.")
    st.stop()


# 같은 지역에 여러 행이 있으면 나이별로 합산합니다.
# 각 행이 서로 다른 하위 구역을 나타내는 데이터에도 대응합니다.
male_population = (
    selected_df[male_columns]
    .sum()
    .to_numpy(dtype=float)
)

female_population = (
    selected_df[female_columns]
    .sum()
    .to_numpy(dtype=float)
)


# ============================================================
# 9. 인구 피라미드 그래프 그리기
# ============================================================

# 남성은 왼쪽에 표시하도록 음수로 변환합니다.
male_values = -male_population

# 여성은 오른쪽에 표시하도록 양수를 유지합니다.
female_values = female_population

# 그래프의 최대 범위를 좌우 대칭으로 설정합니다.
max_population = max(
    float(np.max(male_population)),
    float(np.max(female_population)),
    1.0,
)

axis_limit = max_population * 1.15

fig = go.Figure()

# 남자 막대: 음수이므로 왼쪽에 나타납니다.
fig.add_trace(
    go.Bar(
        name="남자",
        y=AGES,
        x=male_values,
        orientation="h",
        marker_color="#D98B5F",
        hovertemplate=(
            "나이: %{y}<br>"
            "남자 인구: %{customdata:,.0f}명"
            "<extra></extra>"
        ),
        customdata=male_population,
    )
)

# 여자 막대: 양수이므로 오른쪽에 나타납니다.
fig.add_trace(
    go.Bar(
        name="여자",
        y=AGES,
        x=female_values,
        orientation="h",
        marker_color="#E7A0A8",
        hovertemplate=(
            "나이: %{y}<br>"
            "여자 인구: %{x:,.0f}명"
            "<extra></extra>"
        ),
    )
)

fig.update_layout(
    title={
        "text": (
            f"{selected_sido} {selected_sigungu} "
            f"{selected_dong} 인구 피라미드 ({latest_year}년)"
        ),
        "x": 0.5,
        "xanchor": "center",
    },
    barmode="overlay",
    bargap=0.12,
    height=1100,
    plot_bgcolor="#FFF9F3",
    paper_bgcolor="#FFF9F3",
    font={
        "family": "Malgun Gothic, Apple SD Gothic Neo, sans-serif",
        "size": 12,
        "color": "#49382F",
    },
    legend={
        "title": "성별",
        "orientation": "h",
        "yanchor": "bottom",
        "y": 1.02,
        "xanchor": "center",
        "x": 0.5,
    },
    margin={
        "l": 100,
        "r": 45,
        "t": 100,
        "b": 75,
    },
)

# 가로축: 남성은 음수지만 눈금에는 양수 인구로 표시합니다.
tick_step = max(
    1,
    int(np.ceil(axis_limit / 5 / 100) * 100),
)

tick_values_positive = list(
    range(0, int(axis_limit) + tick_step, tick_step)
)

# 양쪽의 눈금 범위가 동일하도록 음수와 양수를 함께 지정합니다.
tick_values = (
    [-value for value in reversed(tick_values_positive[1:])]
    + tick_values_positive
)

fig.update_xaxes(
    title_text="인구수 (명)",
    range=[-axis_limit, axis_limit],
    tickmode="array",
    tickvals=tick_values,
    ticktext=[
        f"{abs(value):,}" for value in tick_values
    ],
    zeroline=True,
    zerolinecolor="#8B7765",
    zerolinewidth=1.5,
    gridcolor="#EADFD5",
)


# ============================================================
# 10. 세로축 나이 순서 고정 및 최종 확인
# ============================================================

# 중요!
# 나이 라벨을 0세부터 100세 이상까지 직접 지정합니다.
# categoryorder="array"와 categoryarray를 사용하므로
# 값의 크기에 따라 나이가 정렬되지 않습니다.
# autorange="normal"은 축 전체를 뒤집지 않습니다.
fig.update_yaxes(
    title_text="나이",
    type="category",
    categoryorder="array",
    categoryarray=AGES,
    autorange="normal",
    tickmode="array",
    tickvals=AGES,
    ticktext=AGES,
    showgrid=False,
)

# 그래프에 전달된 나이 순서를 다시 검사합니다.
# 의도한 순서와 다르면 오류를 표시해 잘못된 그래프를 방지합니다.
assert AGES[0] == "0세"
assert AGES[-1] == "100세 이상"
assert len(AGES) == 101
assert len(fig.data) == 2
assert list(fig.data[0].y) == AGES
assert list(fig.data[1].y) == AGES

st.subheader("📊 인구 피라미드")

st.caption(
    "왼쪽은 남자, 오른쪽은 여자입니다. "
    "막대에 마우스를 올리면 해당 나이의 인구를 확인할 수 있습니다."
)

st.plotly_chart(
    fig,
    use_container_width=True,
    config={
        "displaylogo": False,
        "responsive": True,
    },
)

# 화면에서도 마지막으로 나이 축의 의도한 순서를 알려 줍니다.
st.caption(
    "나이 축 확인: 맨 아래 0세 → 맨 위 100세 이상 "
    "(101개 나이 라벨을 지정된 순서대로 고정)"
)

st.divider()

# ============================================================
# 11. 선택한 지역의 간단한 인구 요약
# ============================================================

total_male = int(male_population.sum())
total_female = int(female_population.sum())
total_population = total_male + total_female

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        label="전체 인구",
        value=f"{total_population:,}명",
    )

with col2:
    st.metric(
        label="남자 인구",
        value=f"{total_male:,}명",
    )

with col3:
    st.metric(
        label="여자 인구",
        value=f"{total_female:,}명",
    )

st.caption(
    "※ 인구는 선택한 지역의 최신 연도 자료를 기준으로 계산했습니다."
)
