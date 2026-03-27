import streamlit as st
import pandas as pd
import plotly.express as px
import ast

# ==========================================
# 1. 페이지 기본 설정 (API 키 입력란 삭제, 초경량화)
# ==========================================
st.set_page_config(page_title="KOVEA 마케팅 대시보드", layout="wide")
st.title("⛺ KOVEA 초캠 카페 여론 통합 분석 대시보드")
st.markdown("월별 주요 이슈부터 연간 트렌드, 타사 경쟁 제품 매치업, 구매 여정까지 한눈에 파악합니다.")

# ==========================================
# 2. 완성된 분석 데이터 불러오기 (API 호출 X, 로딩 1초)
# ==========================================
@st.cache_data
def load_analyzed_data():
    # 💡 깃허브에 함께 올려둔 완성본 엑셀 파일 이름
    analyzed_file_path = "kovea_analyzed_result.csv"
    
    try:
        df = pd.read_csv(analyzed_file_path)
        
        # 컬럼명 공백 제거
        df.columns = df.columns.str.strip()
        
        # 3번째 열(인덱스 2) 조회수 쉼표 제거 및 숫자 변환
        df['views'] = df.iloc[:, 2].astype(str).str.replace(',', '')
        df['views'] = pd.to_numeric(df['views'], errors='coerce').fillna(0)
        
        # 댓글수 숫자 변환
        if 'comments_count' in df.columns:
            df['comments_count'] = df['comments_count'].astype(str).str.replace(',', '')
            df['comments_count'] = pd.to_numeric(df['comments_count'], errors='coerce').fillna(0)
        else:
            df['comments_count'] = 0
            
        # 화제성 점수 계산 (조회수 + 댓글수*50)
        df['화제성_점수'] = df['views'] + (df['comments_count'] * 50)
        
        # 날짜 및 월별 데이터 파생
        df['date'] = pd.to_datetime(df['date'], format='%Y.%m.%d.', errors='coerce')
        df = df.dropna(subset=['date']) 
        df['year_month'] = df['date'].dt.strftime('%Y-%m')
        
        # 문자열로 저장된 타사 경쟁사 리스트를 실제 파이썬 리스트로 복원
        def parse_competitors(comp_str):
            try:
                return ast.literal_eval(comp_str) if isinstance(comp_str, str) else []
            except:
                return []
        
        if 'competitors' in df.columns:
            df['competitors'] = df['competitors'].apply(parse_competitors)
            
        return df
    except FileNotFoundError:
        st.error(f"❌ '{analyzed_file_path}' 파일을 찾을 수 없습니다. 깃허브에 분석 완료된 엑셀 파일이 잘 올라가 있는지 확인해주세요!")
        return pd.DataFrame()

# ==========================================
# 3. 대시보드 시각화 (즉시 렌더링)
# ==========================================
df = load_analyzed_data()

if not df.empty:
    tab1, tab2 = st.tabs(["📅 월별 상세 분석 대시보드", "📈 연간 통합 대시보드 (라이벌 매치업)"])
    
    # --- [TAB 1] 월별 대시보드 ---
    with tab1:
        available_months = sorted(df['year_month'].unique())
        selected_month = st.sidebar.selectbox("분석할 월을 선택하세요", available_months)
        df_month = df[df['year_month'] == selected_month]
        
        st.subheader(f"[{selected_month}] 핵심 인사이트")
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("총 언급 게시글", f"{len(df_month)} 건")
        c2.metric("총 조회수", f"{df_month['views'].sum():,.0f} 회")
        c3.metric("가장 많이 언급된 제품", df_month['제품_분류'].mode()[0] if not df_month.empty else "-")
        c4.metric("주요 구매 여정", df_month['journey'].mode()[0] if not df_month.empty else "-")
        
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        with col1:
            top_products = df_month['제품_분류'].value_counts().reset_index().head(10)
            fig_prod = px.bar(top_products, x='count', y='제품_분류', orientation='h', title="🏆 제품별 언급 수 TOP 10")
            fig_prod.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_prod, use_container_width=True)
            
        with col2:
            df_journey_sent = df_month.groupby(['journey', 'sentiment']).size().reset_index(name='count')
            fig_journey = px.bar(df_journey_sent, x='journey', y='count', color='sentiment', barmode='group',
                                 title="🔄 구매 여정 × 감성 교차 분석",
                                 color_discrete_map={'긍정':'#00CC96', '부정':'#EF553B', '중립':'#636EFA'})
            st.plotly_chart(fig_journey, use_container_width=True)
            
        st.markdown("---")
        
        st.subheader("🫧 고객 핵심 불만 (Pain Point) 버블 차트")
        if 'pain_point' in df_month.columns:
            df_pain = df_month[df_month['pain_point'] != ''].groupby('pain_point').agg({'제품_분류':'count', '화제성_점수':'sum'}).reset_index()
            df_pain.rename(columns={'제품_분류':'언급횟수'}, inplace=True)
            
            if not df_pain.empty:
                fig_bubble = px.scatter(df_pain, x='pain_point', y='언급횟수', size='화제성_점수', color='pain_point',
                                        title="불만 요인 파급력 분석 (버블 크기 = 화제성 점수)",
                                        size_max=50, template="plotly_white")
                st.plotly_chart(fig_bubble, use_container_width=True)
            else:
                st.info("해당 월에 감지된 뚜렷한 불만(Pain Point)이 없습니다.")
        
        st.markdown("---")
        st.subheader("🔥 파급력 기반 (조회수+댓글) 핵심 이슈 게시글")
        if '화제성_점수' in df_month.columns:
            df_best = df_month.sort_values(by='화제성_점수', ascending=False).head(5)
            cols_to_show = [c for c in ['date', 'title', '제품_분류', 'sentiment', 'pain_point', 'summary', 'views'] if c in df_best.columns]
            st.dataframe(df_best[cols_to_show], use_container_width=True)

    # --- [TAB 2] 연간 통합 대시보드 ---
    with tab2:
        st.subheader("📅 계절성 및 연간 경쟁 트렌드 분석")
        
        df_trend = df.groupby(['year_month', 'sentiment']).size().reset_index(name='count')
        fig_trend = px.line(df_trend, x='year_month', y='count', color='sentiment', markers=True,
                            title="월별 언급량 및 여론 동향 추이",
                            color_discrete_map={'긍정':'#00CC96', '부정':'#EF553B', '중립':'#636EFA'})
        st.plotly_chart(fig_trend, use_container_width=True)
        
        st.markdown("---")
        st.subheader("🆚 코베아 라인업별 타사 라이벌 매치업 지형도")
        
        if 'competitors' in df.columns:
            comp_data = []
            for idx, row in df.iterrows():
                if isinstance(row['competitors'], list):
                    for comp in row['competitors']:
                        brand = comp.get('brand', '')
                        # 경쟁사에서 코베아 제외 로직
                        if brand and not any(x in str(brand).upper() for x in ['코베아', 'KOVEA']):
                            comp_data.append({'코베아_제품': row['제품_분류'], '타사_브랜드': brand})
                            
            df_comp_flat = pd.DataFrame(comp_data)
            
            if not df_comp_flat.empty:
                df_tree = df_comp_flat.groupby(['코베아_제품', '타사_브랜드']).size().reset_index(name='count')
                fig_tree = px.treemap(df_tree, path=[px.Constant("전체 경쟁 현황"), '코베아_제품', '타사_브랜드'], values='count', 
                                      title="어떤 타사 브랜드와 가장 많이 비교될까? (박스 크기 = 언급량)",
                                      color='count', color_continuous_scale='Blues')
                fig_tree.update_traces(root_color="lightgrey")
                fig_tree.update_layout(margin=dict(t=50, l=25, r=25, b=25))
                st.plotly_chart(fig_tree, use_container_width=True)
            else:
                st.info("비교 언급된 타사 브랜드 데이터가 부족합니다.")
