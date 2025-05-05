import streamlit as st
import pandas as pd
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
from sqlalchemy import create_engine
from geopy.distance import geodesic

# ---------------------------
# DB 연결 설정
# ---------------------------
DB_URI = "mysql+pymysql://root:acorn1234@localhost:3306/disaster_dashboard?charset=utf8mb4"
engine = create_engine(DB_URI)

# ---------------------------
# 데이터 불러오기
# ---------------------------
@st.cache_data
def load_data():
    shelters = pd.read_sql("SELECT * FROM shelters", engine)
    artillery = pd.read_sql("SELECT * FROM artillery_range", engine)
    dmz = pd.read_sql("SELECT * FROM military_demarcation_line", engine)
    return shelters, artillery, dmz

shelters, artillery, dmz = load_data()

# ---------------------------
# 위험도 점수 계산 함수
# ---------------------------
def calculate_risk(row, center, max_radius):
    shelter_coord = (row['위도(EPSG4326)'], row['경도(EPSG4326)'])
    distance_km = geodesic(shelter_coord, center).km
    in_range = distance_km <= max_radius
    risk_score = 0
    if in_range:
        risk_score += 50  # 포격 범위 내 가산점
    if pd.notnull(row['수용률(%)']):
        if row['수용률(%)'] < 30:
            risk_score += 50
        elif row['수용률(%)'] < 60:
            risk_score += 30
        else:
            risk_score += 10
    return risk_score

# ---------------------------
# 사이드바 필터
# ---------------------------
st.sidebar.title("대피소 필터")
sido_list = sorted(shelters['시도별'].dropna().unique())
selected_sido = st.sidebar.selectbox("시도 선택", ["전체"] + sido_list)
rate_range = st.sidebar.slider("수용률 (%) 범위", 0, 200, (0, 100))

# 포격 중심점 및 최대 반경 설정 (최대 사거리 기준)
center = [38.0, 126.8]  # 개성 근처
max_range_km = artillery['최대사거리_km'].max()

# 위험도 점수 계산 및 필터 적용
shelters['위험도점수'] = shelters.apply(lambda row: calculate_risk(row, center, max_range_km), axis=1)

# 위험도 등급 색상 설정 함수
def get_color(score):
    if score >= 90:
        return 'darkred'
    elif score >= 70:
        return 'orangered'
    elif score >= 50:
        return 'orange'
    else:
        return 'green'

# 필터 적용
data_filtered = shelters.copy()
if selected_sido != "전체":
    data_filtered = data_filtered[data_filtered['시도별'] == selected_sido]
data_filtered = data_filtered[data_filtered['수용률(%)'].between(*rate_range)]

# ---------------------------
# 탭 설정
# ---------------------------
tab1, tab2 = st.tabs(["🗺️ 지도 시각화", "📊 수용률 분석"])

# ---------------------------
# 지도 탭
# ---------------------------
with tab1:
    st.subheader("대피소 및 군사분계선 + 포격 범위 + 위험도 시각화")
    
    m = folium.Map(location=[37.5, 127.0], zoom_start=8)

    # 군사분계선
    dmz_coords = dmz[['위도_EPSG4326', '경도_EPSG4326']].values.tolist()
    folium.PolyLine(locations=dmz_coords, color='red', weight=3).add_to(m)

    # 포격 사거리 원
    for _, row in artillery.iterrows():
        folium.Circle(
            location=center,
            radius=row['최대사거리_km'] * 1000,
            popup=row['무기'],
            color='orange', fill=True, fill_opacity=0.2
        ).add_to(m)

    # 대피소 마커 (위험도 기반 색상)
    cluster = MarkerCluster().add_to(m)
    for _, row in data_filtered.iterrows():
        folium.CircleMarker(
            location=[row['위도(EPSG4326)'], row['경도(EPSG4326)']],
            radius=4,
            popup=f"{row['소재지전체주소']}\n수용률: {row['수용률(%)']}%\n위험도점수: {row['위험도점수']}",
            color=get_color(row['위험도점수']),
            fill=True, fill_opacity=0.7
        ).add_to(cluster)

    st_folium(m, width=800, height=600)

# ---------------------------
# 분석 탭
# ---------------------------
with tab2:
    st.subheader("시도별 평균 수용률 순위")
    avg_rate_by_sido = shelters.groupby('시도별')['수용률(%)'].mean().sort_values(ascending=False)
    st.bar_chart(avg_rate_by_sido)

    st.subheader("위험도 점수 상위 10개 대피소")
    top10 = shelters.sort_values("위험도점수", ascending=False).head(10)
    st.dataframe(top10[['소재지전체주소', '수용률(%)', '위험도점수']])
