import streamlit as st
import pandas as pd
import re
import json
import time
from openai import OpenAI
import plotly.express as px

# ==========================================
# 1. 페이지 및 API 기본 설정
# ==========================================
st.set_page_config(page_title="KOVEA 마케팅 대시보드", layout="wide")
st.sidebar.title("⚙️ 대시보드 설정")
api_key = st.sidebar.text_input("Upstage API Key를 입력하세요", type="password")

st.title("⛺ KOVEA 초캠 카페 여론 통합 분석 대시보드")
st.markdown("월별 주요 이슈부터 연간 트렌드, 타사 경쟁 제품 매치업, 구매 여정까지 한눈에 파악합니다.")

# ==========================================
# 2. 데이터 불러오기 및 전처리 함수 (스마트 매칭 완비)
# ==========================================
@st.cache_data
def load_and_preprocess_data():
    crawled_file_path = r"C:\Users\dmlgu\Downloads\FICB4\kovea_naver_cafe_full.csv"
    product_file_path = r"C:\Users\dmlgu\Downloads\FICB4\kovea_product.csv"
    
    df = pd.read_csv(crawled_file_path)
    df_products = pd.read_csv(product_file_path)
    
    # 컬럼명 공백 제거 및 조회수(views), 댓글수 강제 숫자 변환
    df.columns = df.columns.str.strip()
    df['views'] = df.iloc[:, 2].astype(str).str.replace(',', '')
    df['views'] = pd.to_numeric(df['views'], errors='coerce').fillna(0)
    
    if 'comments_count' in df.columns:
        df['comments_count'] = df['comments_count'].astype(str).str.replace(',', '')
        df['comments_count'] = pd.to_numeric(df['comments_count'], errors='coerce').fillna(0)
    
    # 텍스트 병합 및 날짜 전처리
    df['title'] = df['title'].fillna('')
    df['body'] = df['body'].fillna('')
    df['comments'] = df['comments'].fillna('')
    df['full_text'] = df['title'].astype(str) + " " + df['body'].astype(str) + " " + df['comments'].astype(str)
    
    df['date'] = pd.to_datetime(df['date'], format='%Y.%m.%d.', errors='coerce')
    df = df.dropna(subset=['date']) 
    df['year_month'] = df['date'].dt.strftime('%Y-%m')
    
    df_products['검색용_제품명'] = df_products['제품명'].apply(lambda x: re.sub(r'\s*\(.*?\)\s*', '', str(x)).strip())
    kovea_keywords = df_products['검색용_제품명'].unique().tolist()
    kovea_category_map = dict(zip(df_products['검색용_제품명'], df_products['카테고리']))

    # 스마트 텍스트 매칭 사전
    kovea_alias_dict = {
        '네스트 W': ['네스트W', '네스트w', '네스트더블유', '네스트시리즈', '네스트'],
        '네스트 2': ['네스트2', '네트스2', '네트스 2'], 
        '고스트 팬텀': ['고스트팬텀', '고팬', '팬텀'],
        '구이바다': ['구이바다', '3WAY', '3웨이', '3웨이', '코베아39'],
        '캠프원': ['캠프1', '캠프원'],
        '몬스터': ['몬스터', '코베아몬스터'],
        '기가썬': ['기가썬', '기가선'],
        '문리버': ['문리버4', '문리버2', '문리버'],
        '이스턴': ['이스턴시그니처', '이스턴3', '이스턴'],
        '아웃백': ['아웃백골드', '아웃백시그니처', '아웃백'],
        '퀀텀골드': ['퀀텀골드', '퀀텀'],
        '크레모아 콜라보': ['크레모아', '감성포차', '이너프', '사이다', '반합'] 
    }

    def extract_product_advanced(text):
        if not isinstance(text, str): return '기타'
        norm_text = text.upper().replace(" ", "")
        
        for real_name, aliases in kovea_alias_dict.items():
            for alias in aliases:
                norm_alias = alias.upper().replace(" ", "")
                if norm_alias in norm_text: return real_name 
                    
        for kw in kovea_keywords:
            norm_kw = str(kw).upper().replace(" ", "")
            if norm_kw in norm_text: return kw
                
        if '코베아' in norm_text:
            if '망치' in norm_text: return '소품류(망치 등)'
            if '토치' in norm_text: return '소품류(토치 등)'
            if '침대' in norm_text or '매트' in norm_text: return '에어매트/침대류'
            return '코베아 단순언급'
            
        return '기타'

    df['제품_분류'] = df['full_text'].apply(extract_product_advanced)
    
    manual_category_map = {
        '구이바다': '버너', '캠프원': '버너', '기가썬': '난로', 
        '문리버': '텐트/타프', '이스턴': '텐트/타프', '아웃백': '텐트/타프', 
        '퀀텀골드': '텐트/타프', '크레모아 콜라보': '조명/액세서리',
        '소품류(망치 등)': '소품', '소품류(토치 등)': '소품', '에어매트/침대류': '매트', '코베아 단순언급': '기타'
    }
    kovea_category_map.update(manual_category_map)
    df['자사_카테고리'] = df['제품_분류'].map(kovea_category_map).fillna('기타')

    return df

# ==========================================
# 3. Upstage API 심층 분석 함수
# ==========================================
@st.cache_data(show_spinner=False)
def run_upstage_analysis(df, api_key):
    client = OpenAI(api_key=api_key, base_url="https://api.upstage.ai/v1/solar")
    results = []
    my_bar = st.progress(0, text="Upstage(Solar) 모델이 데이터를 심층 분석 중입니다...")
    
    for idx, row in df.iterrows():
        text, product = row['full_text'], row['제품_분류']
        prompt = f"""
        당신은 캠핑 마케팅 전문가입니다. 아래 게시글을 읽고 다음 JSON 형식으로만 응답하세요.
        타겟 코베아 제품: [{product}]
        
        {{
            "sentiment": "긍정, 부정, 중립 중 택 1",
            "summary": "해당 글의 핵심 이슈 1줄 요약",
            "pain_point": "만약 부정이면 불만 핵심 키워드(예: AS지연, 폴대휨, 결로). 부정이 아니면 빈칸 ''",
            "journey": "구매전(질문/고민) 또는 구매후(후기/정보) 중 택 1",
            "competitors": [
                {{"brand": "타사 브랜드명", "product": "타사 제품명", "category": "카테고리"}}
            ]
        }}
        게시글: {text[:1500]}
        """
        try:
            response = client.chat.completions.create(
                model="solar-1-mini-chat",
                response_format={ "type": "json_object" },
                messages=[{"role": "system", "content": "You output JSON strictly."}, {"role": "user", "content": prompt}],
                temperature=0.1
            )
            parsed = json.loads(response.choices[0].message.content)
            results.append(parsed)
        except Exception as e:
            results.append({"sentiment": "중립", "summary": "분석 오류", "pain_point": "", "journey": "구매후", "competitors": []})
            
        my_bar.progress((idx + 1) / len(df))
        time.sleep(0.3)
        
    my_bar.empty()
    df['sentiment'] = [r.get('sentiment', '중립') for r in results]
    df['summary'] = [r.get('summary', '') for r in results]
    df['pain_point'] = [r.get('pain_point', '') for r in results]
    df['journey'] = [r.get('journey', '구매후') for r in results]
    df['competitors'] = [r.get('competitors', []) for r in results]
    df['화제성_점수'] = df['views'] + (df['comments_count'] * 50)
    
    return df

# ==========================================
# 4. 대시보드 시각화
# ==========================================
df_raw = load_and_preprocess_data()

if api_key:
    # 빠른 테스트를 원하시면 df_raw = df_raw.head(20) 로 변경하세요
    df = run_upstage_analysis(df_raw, api_key) 
    
    tab1, tab2 = st.tabs(["📅 월별 상세 분석 대시보드", "📈 연간 통합 대시보드 (라이벌 매치업)"])
    
    # ==========================================
    # [TAB 1] 월별 대시보드
    # ==========================================
    with tab1:
        available_months = sorted(df['year_month'].unique())
        if not available_months:
            st.warning("분석 가능한 날짜 데이터가 없습니다.")
        else:
            selected_month = st.sidebar.selectbox("분석할 월을 선택하세요", available_months)
            df_month = df[df['year_month'] == selected_month]
            
            st.subheader(f"[{selected_month}] 핵심 인사이트")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("총 언급 게시글", f"{len(df_month)} 건")
            c2.metric("총 조회수", f"{df_month['views'].sum():,.0f} 회")
            c3.metric("가장 많이 언급된 제품", df_month['제품_분류'].mode()[0] if not df_month.empty else "-")
            c4.metric("주요 구매 여정", df_month['journey'].mode()[0] if not df_month.empty else "-")
            
            st.markdown("---")
            
            # 1. 제품 언급 수 및 🌟 [신규] 구매여정 x 감성 교차 분석
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
            
            # 2. 🌟 [신규] 핵심 불만(Pain Point) 버블 차트
            st.subheader("🫧 고객 핵심 불만 (Pain Point) 버블 차트")
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
            df_best = df_month.sort_values(by='화제성_점수', ascending=False).head(5)
            st.dataframe(df_best[['date', 'title', '제품_분류', 'sentiment', 'pain_point', 'summary', 'views']], use_container_width=True)

            # 원인 분석용 '기타' 분류 테이블 (히든 데이터 파악)
            with st.expander("🚨 [원인 분석용] '기타' 분류 원문 데이터 확인"):
                df_others = df_month[df_month['제품_분류'] == '기타']
                if not df_others.empty:
                    st.dataframe(df_others[['title', 'body', 'comments']], use_container_width=True)
                else:
                    st.success("'기타'로 분류된 글이 없습니다!")
        
    # ==========================================
    # [TAB 2] 연간 통합 대시보드
    # ==========================================
    with tab2:
        st.subheader("📅 계절성 및 연간 경쟁 트렌드 분석")
        
        # 1. 월별 전체 언급량 추이
        df_trend = df.groupby(['year_month', 'sentiment']).size().reset_index(name='count')
        fig_trend = px.line(df_trend, x='year_month', y='count', color='sentiment', markers=True,
                            title="월별 언급량 및 여론 동향 추이",
                            color_discrete_map={'긍정':'#00CC96', '부정':'#EF553B', '중립':'#636EFA'})
        st.plotly_chart(fig_trend, use_container_width=True)
        
        # 2. 🌟 [신규] 라이벌 매치업 트리맵 (Treemap)
        st.markdown("---")
        st.subheader("🆚 코베아 라인업별 타사 라이벌 매치업 지형도")
        
        comp_data = []
        for idx, row in df.iterrows():
            if isinstance(row['competitors'], list):
                for comp in row['competitors']:
                    brand = comp.get('brand', '')
                    # 경쟁사에서 '코베아' 완벽 제외
                    if brand and not any(x in str(brand).upper() for x in ['코베아', 'KOVEA']):
                        comp_data.append({
                            '코베아_제품': row['제품_분류'],
                            '타사_브랜드': brand,
                            '타사_제품': comp.get('product', '')
                        })
                        
        df_comp_flat = pd.DataFrame(comp_data)
        
        if not df_comp_flat.empty:
            df_tree = df_comp_flat.groupby(['코베아_제품', '타사_브랜드']).size().reset_index(name='count')
            # 코베아 제품 카테고리 안에 타사 브랜드가 묶이는 트리맵 구조
            fig_tree = px.treemap(df_tree, path=[px.Constant("전체 경쟁 현황"), '코베아_제품', '타사_브랜드'], values='count', 
                                  title="어떤 타사 브랜드와 가장 많이 비교될까? (박스 크기 = 언급량)",
                                  color='count', color_continuous_scale='Blues')
            fig_tree.update_traces(root_color="lightgrey")
            fig_tree.update_layout(margin=dict(t=50, l=25, r=25, b=25))
            st.plotly_chart(fig_tree, use_container_width=True)
        else:
            st.info("비교 언급된 타사 브랜드 데이터가 부족하여 지형도를 그릴 수 없습니다.")

else:
    st.warning("👈 왼쪽 사이드바에 Upstage API Key를 입력하시면 실제 크롤링 데이터 분석이 시작됩니다.")