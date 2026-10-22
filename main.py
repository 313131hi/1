import datetime
import pandas as pd
import plotly.express as px
import requests
import streamlit as st

# ==========================================
# 1. 페이지 기본 설정 및 헤더
# ==========================================
st.set_page_config(
    page_title="일별 박스오피스 순위", page_icon="🎬", layout="wide"
)

st.title("🎬 어제의 일별 박스오피스")


# ==========================================
# 2. 날짜 계산 (한국 시간 UTC+9 기준)
# ==========================================
# 배포 서버의 시계가 UTC(영국 표준시) 기준일 수 있으므로,
# 한국 시간(UTC+9)을 명확하게 계산하여 어제 날짜를 생성합니다.
utc_now = datetime.datetime.now(datetime.timezone.utc)
korea_tz = datetime.timezone(datetime.timedelta(hours=9))
korea_now = utc_now.astimezone(korea_tz)

# 오늘에서 하루를 빼서 '어제' 날짜를 만듭니다.
yesterday = korea_now - datetime.timedelta(days=1)
target_dt = yesterday.strftime("%Y%m%d")  # KOBIS 요청용 (YYYYMMDD 형식)
display_date = yesterday.strftime(
    "%Y년 %m월 %d일"
)  # 화면 표시용 (YYYY년 MM월 DD일)

st.caption(f"📅 기준일: **{display_date}** (한국 시간 기준 어제)")


# ==========================================
# 3. KOBIS API 인증키 불러오기
# ==========================================
# Streamlit Secrets(비밀 금고)에서 KOBIS_KEY를 가져옵니다.
if "KOBIS_KEY" not in st.secrets:
    st.error("🔑 **[설정 필요] Secrets에 `KOBIS_KEY`가 존재하지 않습니다.**")
    st.info(
        """
    **조치 방법:**
    1. Streamlit Cloud 앱 관리 페이지의 **App settings -> Secrets**로 이동하세요.
    2. 아래와 같이 KOBIS 인증키를 추가해 주세요:
       ```toml
       KOBIS_KEY = "발급받은_인증키_입력"
       ```
    """
    )
    st.stop()

api_key = st.secrets["KOBIS_KEY"]


# ==========================================
# 4. KOBIS API 데이터 요청 함수
# ==========================================
@st.cache_data(ttl=3600)  # 1시간 동안 응답 결과를 캐싱하여 API 호출 절약
def fetch_box_office(key, target_date):
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {"key": key, "targetDt": target_date}

    try:
        response = requests.get(url, params=params, timeout=10)
        # HTTP 응답 상태 코드가 200이 아니면 예외 발생
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.RequestException as e:
        return None, f"네트워크 요청에 실패했습니다: {e}"


# API 데이터 가져오기 실행
data, error_msg = fetch_box_office(api_key, target_dt)


# ==========================================
# 5. 예외 및 오류 처리
# ==========================================
# 네트워크 또는 HTTP 에러 발생 시
if error_msg:
    st.error("⚠️ 데이터를 불러오는 중 오류가 발생했습니다.")
    st.warning(f"**상세 내용:** {error_msg}")
    st.info("💡 인터넷 연결 상태를 확인하시거나 잠시 후 다시 시도해 주세요.")
    st.stop()

# KOBIS 특유의 오류 구조(faultInfo)가 포함되어 온 경우 (인증키 오류 등)
if "faultInfo" in data:
    fault = data["faultInfo"]
    st.error("⚠️ **KOBIS API 응답 오류가 발생했습니다.**")
    st.write(f"- **오류 코드:** {fault.get('errorCode', '알 수 없음')}")
    st.write(f"- **오류 메시지:** {fault.get('message', '알 수 없음')}")
    st.info(
        """
    💡 **확인 사항:**
    1. Streamlit Secrets에 입력한 `KOBIS_KEY`가 정확한지 확인해 주세요.
    2. KOBIS 영화관입장권통합전산망 오픈API 사이트에서 인증키가 활성화 상태인지 확인하세요.
    """
    )
    st.stop()

# 데이터 결과 검증
box_office_result = data.get("boxOfficeResult", {})
movie_list = box_office_result.get("dailyBoxOfficeList", [])

# 영화 목록이 비어 있는 경우
if not movie_list:
    st.warning(
        f"⚠️ **{display_date}**의 박스오피스 데이터가 비어 있거나 아직 집계되지 않았습니다."
    )
    st.info(
        """
    💡 **확인 사항:**
    1. KOBIS 시스템의 어제 자 일별 박스오피스 집계가 지연되고 있을 수 있습니다.
    2. 잠시 후 페이지를 새로고침(F5)해 보세요.
    """
    )
    st.stop()


# ==========================================
# 6. 데이터 전처리 (문자열 -> 숫자 변환)
# ==========================================
df = pd.DataFrame(movie_list)

# API 응답의 숫자 컬럼이 문자열로 전달되므로 정수형(int)으로 변환합니다.
int_columns = ["rank", "audiCnt", "audiAcc", "scrnCnt", "showCnt"]
for col in int_columns:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)


# ==========================================
# 7. 1위 영화 지표 카드 (Metrics)
# ==========================================
st.subheader("🥇 1위 영화 하이라이트")

top_1 = df[df["rank"] == 1].iloc[0]

# 순위 증감 표시 텍스트 작성
rank_inten = top_1.get("rankInten", "0")
try:
    rank_inten_num = int(rank_inten)
    if rank_inten_num > 0:
        delta_text = f"▲ {rank_inten_num}"
    elif rank_inten_num < 0:
        delta_text = f"▼ {abs(rank_inten_num)}"
    else:
        delta_text = "변동 없음"
except ValueError:
    delta_text = rank_inten

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        label="🎬 1위 영화명",
        value=top_1["movieNm"],
        delta=f"순위 변동: {delta_text}",
    )

with col2:
    st.metric(
        label="🍿 어제 관객수",
        value=f"{top_1['audiCnt']:,} 명",
    )

with col3:
    st.metric(
        label="👥 누적 관객수",
        value=f"{top_1['audiAcc']:,} 명",
    )

st.markdown("---")


# ==========================================
# 8. 관객수 상위 5편 막대그래프
# ==========================================
st.subheader("📊 관객수 TOP 5 영화")

# 1~5위 영화 데이터 추출
top_5_df = df.head(5).copy()

# 막대그래프 생성 (Plotly)
fig = px.bar(
    top_5_df,
    x="movieNm",
    y="audiCnt",
    text="audiCnt",
    labels={"movieNm": "영화명", "audiCnt": "어제 관객수(명)"},
    color="audiCnt",
    color_continuous_scale="Blues",
)

# 그래프 레이아웃 세부 설정
fig.update_traces(
    texttemplate="%{text:,}명", textposition="outside", cliponaxis=False
)
fig.update_layout(
    xaxis_title="",
    yaxis_title="관객수 (명)",
    coloraxis_showscale=False,
    height=400,
    margin=dict(t=30, b=10, l=10, r=10),
)

st.plotly_chart(fig, use_container_width=True)

st.markdown("---")


# ==========================================
# 9. 전체 박스오피스 순위표
# ==========================================
st.subheader("📋 전체 박스오피스 순위표")

# 화면에 보여줄 컬럼 선택 및 이름 변경
display_df = df[
    ["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]
].copy()
display_df.columns = [
    "순위",
    "영화명",
    "개봉일",
    "어제 관객수",
    "누적 관객수",
    "스크린수",
]

# 테이블 내 숫자 포맷 지정 (천 단위 쉼표)
st.dataframe(
    display_df,
    column_config={
        "순위": st.column_config.NumberColumn(format="%d위"),
        "어제 관객수": st.column_config.NumberColumn(format="%s 명"),
        "누적 관객수": st.column_config.NumberColumn(format="%s 명"),
        "스크린수": st.column_config.NumberColumn(format="%s 개"),
    },
    use_container_width=True,
    hide_index=True,
)
