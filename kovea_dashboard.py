import streamlit as st
import pandas as pd
import plotly.express as px
import ast

# ==========================================
# 1. 페이지 기본 설정 (API 키 입력란 삭제, 초경량화)
# ==========================================
st.set_page_config(page_title="KOVEA 마케팅 대시보드", layout="wide")
st.title("초캠 카페 여론 분석 대시보드")
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
    tab1, tab2, tab3 = st.tabs(["📅 월별 상세 분석", "📈 연간 통합 대시보드", "💡 마케팅 액션 인사이트"])
    
    # --- [TAB 1] 월별 대시보드 ---
    with tab1:
        available_months = sorted(df['year_month'].unique())
        selected_month = st.sidebar.selectbox("분석할 월을 선택하세요", available_months)
        df_month = df[df['year_month'] == selected_month]
        
        st.subheader(f"[{selected_month}] 핵심 인사이트")
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("총 언급 게시글", f"{len(df_month)} 건")
        c2.metric("총 조회수", f"{df_month['views'].sum():,.0f} 회")
        
        # 💡 [수정됨] '코베아 단순언급'과 '기타'를 제외한 순수 제품 리스트 만들기
        df_valid_products = df_month[~df_month['제품_분류'].isin(['코베아 단순언급', '기타'])]
        top_product = df_valid_products['제품_분류'].mode()[0] if not df_valid_products.empty else "-"
        
        c3.metric("가장 많이 언급된 제품", top_product)
        c4.metric("주요 구매 여정", df_month['journey'].mode()[0] if not df_month.empty else "-")
        
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        with col1:
            # 💡 [수정됨] 바로 밑에 있는 바 차트(TOP 10)에서도 동일하게 제외되도록 df_valid_products를 사용합니다.
            top_products = df_valid_products['제품_분류'].value_counts().reset_index().head(10)
            fig_prod = px.bar(top_products, x='count', y='제품_분류', orientation='h', title="🏆 순수 제품별 언급 수 TOP 10")
            fig_prod.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_prod, use_container_width=True)
            
        with col2:
            df_journey_sent = df_month.groupby(['journey', 'sentiment']).size().reset_index(name='count')
            fig_journey = px.bar(df_journey_sent, x='journey', y='count', color='sentiment', barmode='group',
                                 title="🔄 구매 여정 × 감성 교차 분석",
                                 color_discrete_map={'긍정':'#00CC96', '부정':'#EF553B', '중립':'#636EFA'})
            st.plotly_chart(fig_journey, use_container_width=True)
            
        st.markdown("---")
        
        # 2. 🫧 [신규] 핵심 불만(Pain Point) 버블 차트
        st.subheader("🫧 고객 핵심 불만 (Pain Point) 버블 차트")
        if 'pain_point' in df_month.columns:
            # 기본 전처리 (빈 불만 사항 제외 및 그룹화)
            df_pain = df_month[df_month['pain_point'] != ''].groupby('pain_point').agg({'제품_분류':'count', '화제성_점수':'sum'}).reset_index()
            df_pain.rename(columns={'제품_분류':'언급횟수'}, inplace=True)
            
            if not df_pain.empty:
                # 💡 [핵심 수정] 화제성 점수가 높은 순으로 정렬 후 상위 10개만 추출
                # (버블 크기가 큰 녀석들이 화제성이 높은 핵심 불만입니다!)
                df_pain_top10 = df_pain.sort_values(by='화제성_점수', ascending=False).head(10)
                
                # 💡 Plotly Express가 자동으로 y축(언급횟수) 범위를 'TOP 10 데이터'에 맞춰줘서 더 보기 좋아집니다.
                fig_bubble = px.scatter(df_pain_top10, x='pain_point', y='언급횟수', size='화제성_점수', color='pain_point',
                                        title="TOP 10 불만 요인 파급력 분석 (버블 크기 = 화제성 점수)",
                                        size_max=50, template="plotly_white")
                
                # 💡 버블 수가 줄었으니, 그래프 높이를 살짝 키워서(height=500) 겹침을 더 줄였습니다.
                fig_bubble.update_layout(height=500, margin=dict(l=10, r=10, t=50, b=10))
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
        st.subheader("🏆 연간 마케팅 결산 명예의 전당 TOP 5")
        
        # 1. TOP 5 데이터 준비 (기타 및 단순언급 제외)
        df_valid = df[~df['제품_분류'].isin(['코베아 단순언급', '기타'])].copy()
        
        # 제품별 카테고리 매핑 (데이터 누락 방지용)
        category_map = {
            '네스트 W': '텐트/타프', '네스트 2': '텐트/타프', '고스트 팬텀': '텐트/타프', 
            '몬스터': '텐트/타프', '문리버': '텐트/타프', '이스턴': '텐트/타프', 
            '아웃백': '텐트/타프', '퀀텀골드': '텐트/타프',
            '구이바다': '버너/스토브', '캠프원': '버너/스토브', 
            '기가썬': '난로/히터', '에어매트/침대류': '매트/침구',
            '크레모아 콜라보': '조명/액세서리', '소품류(망치 등)': '캠핑 소품', '소품류(토치 등)': '캠핑 소품'
        }
        df_valid['카테고리'] = df_valid['제품_분류'].map(category_map).fillna('기타')
        
        # 타사 브랜드 추출
        all_competitors = []
        if 'competitors' in df.columns:
            for comps in df['competitors']:
                if isinstance(comps, list):
                    for c in comps:
                        b = c.get('brand', '')
                        if b and not any(x in str(b).upper() for x in ['코베아', 'KOVEA']):
                            all_competitors.append(b)
        
        # 2. TOP 5 계산
        top5_prod = df_valid['제품_분류'].value_counts().reset_index().head(5)
        top5_prod.columns = ['제품명', '언급량']
        
        top5_cat = df_valid[df_valid['카테고리'] != '기타']['카테고리'].value_counts().reset_index().head(5)
        top5_cat.columns = ['카테고리', '언급량']
        
        top5_brand = pd.Series(all_competitors).value_counts().reset_index().head(5)
        top5_brand.columns = ['타사 브랜드', '언급량']
        
        # 3. 3분할 화면에 가로 막대 그래프 그리기
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("##### 🥇 가장 많이 언급된 제품")
            fig1 = px.bar(top5_prod, x='언급량', y='제품명', orientation='h', color_discrete_sequence=['#00CC96'])
            fig1.update_layout(yaxis={'categoryorder':'total ascending'}, height=280, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig1, use_container_width=True)
            
        with col2:
            st.markdown("##### 📁 가장 많이 언급된 카테고리")
            fig2 = px.bar(top5_cat, x='언급량', y='카테고리', orientation='h', color_discrete_sequence=['#636EFA'])
            fig2.update_layout(yaxis={'categoryorder':'total ascending'}, height=280, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig2, use_container_width=True)
            
        with col3:
            st.markdown("##### 🥊 가장 많이 언급된 타사 브랜드")
            fig3 = px.bar(top5_brand, x='언급량', y='타사 브랜드', orientation='h', color_discrete_sequence=['#EF553B'])
            fig3.update_layout(yaxis={'categoryorder':'total ascending'}, height=280, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig3, use_container_width=True)

        st.markdown("---")
        
        # 4. 기존 연간 트렌드 차트 유지
        st.subheader("📅 계절성 및 연간 경쟁 트렌드 분석")
        df_trend = df.groupby(['year_month', 'sentiment']).size().reset_index(name='count')
        fig_trend = px.line(df_trend, x='year_month', y='count', color='sentiment', markers=True,
                            title="월별 언급량 및 여론 동향 추이",
                            color_discrete_map={'긍정':'#00CC96', '부정':'#EF553B', '중립':'#636EFA'})
        st.plotly_chart(fig_trend, use_container_width=True)
        
        st.markdown("---")
        
        # 5. 기존 라이벌 매치업 트리맵 유지
        st.subheader("🆚 코베아 라인업별 타사 라이벌 매치업 지형도")
        if 'competitors' in df.columns:
            comp_data = []
            for idx, row in df.iterrows():
                if isinstance(row['competitors'], list):
                    for comp in row['competitors']:
                        brand = comp.get('brand', '')
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

    # ==========================================
    # [TAB 3] 마케팅 액션 인사이트 (콘텐츠 & 전략 도출)
    # ==========================================
    with tab3:
        st.subheader("🎯 실무 밀착형 마케팅 전략 도출")
        st.markdown("데이터를 기반으로 다음 달 SNS 콘텐츠 주제와 프로모션 타겟 제품을 선정합니다.")
        
        # 순수 제품 데이터만 필터링
        df_valid = df[~df['제품_분류'].isin(['코베아 단순언급', '기타'])].copy()
        
        # ------------------------------------------
        # 1. 언급량 vs 관심도(조회수) 4분면 매트릭스
        # ------------------------------------------
        st.markdown("#### 🔍 1. 제품 포지셔닝 매트릭스 (숨은 히트 예감 제품 찾기)")
        
        # 제품별 언급량과 평균 조회수 계산
        df_matrix = df_valid.groupby('제품_분류').agg(
            언급량=('제품_분류', 'count'),
            평균조회수=('views', 'mean')
        ).reset_index()
        
        # 평균값(기준선) 계산
        med_mention = df_matrix['언급량'].median()
        med_views = df_matrix['평균조회수'].median()
        
        fig_matrix = px.scatter(df_matrix, x='언급량', y='평균조회수', text='제품_분류', size='평균조회수', 
                                color='언급량', color_continuous_scale='Sunset',
                                title="👉 우측 상단: 현재 대세 / 좌측 상단: 정보 부족(콘텐츠 발행 시 효율 극대화)")
        
        # 사분면 기준선 긋기
        fig_matrix.add_hline(y=med_views, line_dash="dash", line_color="gray")
        fig_matrix.add_vline(x=med_mention, line_dash="dash", line_color="gray")
        fig_matrix.update_traces(textposition='top center')
        fig_matrix.update_layout(height=500, template="plotly_white")
        st.plotly_chart(fig_matrix, use_container_width=True)
        
        st.markdown("---")
        
        # ------------------------------------------
        # 2. 구매 여정별 (질문 vs 후기) 맞춤형 페인포인트
        # ------------------------------------------
        st.markdown("#### 🗣️ 2. 구매 여정별 핵심 키워드 (맞춤형 콘텐츠 기획용)")
        col_j1, col_j2 = st.columns(2)
        
        with col_j1:
            st.info("🤔 **[구매 전] 고객들이 가장 망설이는 포인트** \n\n👉 상세페이지 보강 및 리뷰 영상 주제로 활용하세요.")
            df_before = df_valid[(df_valid['journey'] == '구매전') & (df_valid['pain_point'] != '')]
            if not df_before.empty:
                before_counts = df_before['pain_point'].value_counts().head(7).reset_index()
                before_counts.columns = ['고민 포인트', '언급량']
                fig_before = px.bar(before_counts, x='언급량', y='고민 포인트', orientation='h', color_discrete_sequence=['#FF9F43'])
                fig_before.update_layout(yaxis={'categoryorder':'total ascending'}, height=300, margin=dict(l=0, r=0, t=0, b=0))
                st.plotly_chart(fig_before, use_container_width=True)
                
        with col_j2:
            st.success("⛺ **[구매 후] 실제 사용 시 겪는 핵심 불편함** \n\n👉 AS팀 공유 및 '올바른 사용법' SNS 꿀팁 콘텐츠로 활용하세요.")
            df_after = df_valid[(df_valid['journey'] == '구매후') & (df_valid['pain_point'] != '')]
            if not df_after.empty:
                after_counts = df_after['pain_point'].value_counts().head(7).reset_index()
                after_counts.columns = ['불만 포인트', '언급량']
                fig_after = px.bar(after_counts, x='언급량', y='불만 포인트', orientation='h', color_discrete_sequence=['#EA5455'])
                fig_after.update_layout(yaxis={'categoryorder':'total ascending'}, height=300, margin=dict(l=0, r=0, t=0, b=0))
                st.plotly_chart(fig_after, use_container_width=True)

        st.markdown("---")
        
        # ------------------------------------------
        # 3. 제품별 계절성(Seasonality) 히트맵
        # ------------------------------------------
        st.markdown("#### ❄️ 3. 연간 제품별 계절성 (Seasonality) 트렌드 히트맵")
        st.write("진한 색상일수록 해당 월에 폭발적인 관심을 받았음을 의미합니다. 내년 프로모션 일정을 짤 때 참고하세요.")
        
        # 피벗 테이블로 데이터 형태 변환 (X축: 월, Y축: 제품명, 값: 언급량)
        df_heat = df_valid.groupby(['제품_분류', 'year_month']).size().reset_index(name='count')
        # 상위 15개 제품만 필터링 (너무 많으면 보기 힘듦)
        top_15_prods = df_valid['제품_분류'].value_counts().head(15).index
        df_heat_top = df_heat[df_heat['제품_분류'].isin(top_15_prods)]
        
        heat_pivot = df_heat_top.pivot(index='제품_분류', columns='year_month', values='count').fillna(0)
        
        fig_heat = px.imshow(heat_pivot, text_auto=True, aspect="auto", color_continuous_scale='Greens',
                             labels=dict(x="연월", y="제품명", color="언급량"))
        fig_heat.update_layout(height=500, margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig_heat, use_container_width=True)
