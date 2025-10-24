"""Day 14-15 완료 체크 페이지

Day 14-15: 재무제표 기반 재무비율 계산 (하이브리드 전략)
"""

import streamlit as st
from pathlib import Path
import sys
from datetime import datetime
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Page configuration
st.set_page_config(
    page_title="Day 14-15 재무비율 체크",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Day 14-15: 재무비율 계산 체크")
st.markdown("**기간**: Day 14-15 | **목표**: 재무제표 기반 10개 재무비율 계산")
st.markdown("---")

# Progress tracker
progress_data = {
    "Task 14.1": {"완료": True, "description": "FinancialRatioCalculator 모듈 구현", "target": "10개 지표"},
    "Task 14.2": {"완료": True, "description": "calculate_quarterly_ratios.py 스크립트 작성", "target": "배치 계산"},
    "Task 14.3": {"완료": True, "description": "PostgreSQL 뷰 생성 (vw_daily_combined_ratios)", "target": "통합 조회"},
    "Task 15.1": {"완료": False, "description": "전체 종목 재무비율 계산 실행", "target": "2,500개 종목"},
    "Task 15.2": {"완료": False, "description": "계산 결과 검증 (이상치 탐지)", "target": "이상치 <5%"},
}

# Calculate overall progress
total_tasks = len(progress_data)
completed_tasks = sum(1 for task in progress_data.values() if task["완료"])
progress_percentage = (completed_tasks / total_tasks) * 100

# Overall progress
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("전체 진행률", f"{progress_percentage:.0f}%", f"{completed_tasks}/{total_tasks} tasks")
with col2:
    st.metric("완료", completed_tasks, delta=None if completed_tasks == total_tasks else f"{total_tasks - completed_tasks}개 남음")
with col3:
    st.metric("상태", "✅ 완료" if completed_tasks == total_tasks else "🚧 진행중")
with col4:
    st.metric("검증 기준", "50,000건", "2,500 × 20")

st.progress(progress_percentage / 100)
st.markdown("---")

# Task details
with st.expander("📋 Task 상세 내역", expanded=False):
    for task_id, task_info in progress_data.items():
        status_icon = "✅" if task_info["완료"] else "🚧"
        st.markdown(f"{status_icon} **{task_id}**: {task_info['description']} (목표: {task_info['target']})")

st.markdown("---")

# =============================================================================
# 1. 계산 가능한 재무비율 확인
# =============================================================================
st.header("1️⃣ 계산 가능한 재무비율 (10개)")

ratio_categories = {
    "수익성 지표 (4개)": [
        {"name": "ROA (총자산이익률)", "field": "roa", "formula": "(당기순이익 / 자산총계) × 100"},
        {"name": "매출총이익률", "field": "gross_profit_margin", "formula": "((매출액 - 매출원가) / 매출액) × 100"},
        {"name": "영업이익률", "field": "operating_profit_margin", "formula": "(영업이익 / 매출액) × 100"},
        {"name": "순이익률", "field": "net_profit_margin", "formula": "(당기순이익 / 매출액) × 100"},
    ],
    "안정성 지표 (4개)": [
        {"name": "부채비율", "field": "debt_ratio", "formula": "(부채총계 / 자기자본) × 100"},
        {"name": "부채자본비율", "field": "debt_to_equity", "formula": "(부채총계 / 자기자본) × 100"},
        {"name": "유동비율", "field": "current_ratio", "formula": "(유동자산 / 유동부채) × 100"},
        {"name": "자기자본비율", "field": "equity_ratio", "formula": "(자기자본 / 자산총계) × 100"},
    ],
    "활동성 지표 (1개)": [
        {"name": "총자산회전율", "field": "asset_turnover", "formula": "매출액 / 평균자산"},
    ],
    "성장성 지표 (1개)": [
        {"name": "매출액 증가율", "field": "revenue_growth", "formula": "((당기매출액 - 전기매출액) / 전기매출액) × 100"},
    ],
}

for category, ratios in ratio_categories.items():
    with st.expander(f"📊 {category}", expanded=True):
        ratio_df = pd.DataFrame(ratios)
        st.dataframe(ratio_df, use_container_width=True, hide_index=True)

st.markdown("---")

# =============================================================================
# 2. 분기별 재무비율 계산 현황
# =============================================================================
st.header("2️⃣ 분기별 재무비율 계산 현황")

if st.button("📊 재무비율 계산 통계 조회", type="primary", key="quarterly_ratio_stats"):
    try:
        from db.connection import SessionLocal
        from models import FinancialRatio, Stock, FinancialStatement
        from sqlalchemy import func, and_

        db = SessionLocal()

        try:
            # 전체 종목 수
            total_stocks = db.query(func.count(Stock.id)).filter(Stock.is_active == True).scalar()

            # 분기별 재무비율 수집 현황 (fiscal_year != NULL)
            quarterly_ratios_count = db.query(func.count(FinancialRatio.id)).filter(
                FinancialRatio.fiscal_year != None
            ).scalar()

            quarterly_stocks_count = db.query(
                func.count(func.distinct(FinancialRatio.stock_id))
            ).filter(FinancialRatio.fiscal_year != None).scalar()

            # 일별 pykrx 비율 수집 현황 (fiscal_year == NULL)
            daily_ratios_count = db.query(func.count(FinancialRatio.id)).filter(
                FinancialRatio.fiscal_year == None
            ).scalar()

            daily_stocks_count = db.query(
                func.count(func.distinct(FinancialRatio.stock_id))
            ).filter(FinancialRatio.fiscal_year == None).scalar()

            # 재무제표 보유 종목 (계산 가능한 종목)
            stmt_stocks_count = db.query(
                func.count(func.distinct(FinancialStatement.stock_id))
            ).scalar()

            # 목표 대비 달성률
            target_stocks = 2500
            target_quarterly_records = 50000  # 2,500 × 20

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric(
                    "분기별 재무비율 레코드",
                    f"{quarterly_ratios_count:,}건",
                    f"{quarterly_ratios_count/target_quarterly_records*100:.1f}% 달성" if quarterly_ratios_count > 0 else "미수집"
                )
                st.caption(f"목표: {target_quarterly_records:,}건 (2,500 × 20)")

            with col2:
                st.metric(
                    "재무비율 계산 종목",
                    f"{quarterly_stocks_count:,}개",
                    f"{quarterly_stocks_count/target_stocks*100:.1f}% 달성" if quarterly_stocks_count > 0 else "미수집"
                )
                st.caption(f"목표: {target_stocks:,}개")

            with col3:
                st.metric(
                    "재무제표 보유 종목",
                    f"{stmt_stocks_count:,}개",
                    "계산 가능"
                )
                st.caption(f"전체: {total_stocks:,}개")

            st.markdown("---")

            # 데이터 타입별 통계
            st.subheader("📊 데이터 타입별 통계")

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**🔢 분기별 재무제표 계산 데이터**")
                st.metric("레코드 수", f"{quarterly_ratios_count:,}건")
                st.metric("종목 수", f"{quarterly_stocks_count:,}개")
                if quarterly_stocks_count > 0:
                    avg_quarters = quarterly_ratios_count / quarterly_stocks_count
                    st.metric("평균 분기 수", f"{avg_quarters:.1f}개/종목")

            with col2:
                st.markdown("**📅 일별 pykrx 데이터**")
                st.metric("레코드 수", f"{daily_ratios_count:,}건")
                st.metric("종목 수", f"{daily_stocks_count:,}개")
                if daily_stocks_count > 0:
                    avg_days = daily_ratios_count / daily_stocks_count
                    st.metric("평균 거래일 수", f"{avg_days:.0f}일/종목")

            st.markdown("---")

            # 분기별 분포
            st.subheader("📈 분기별 데이터 분포")

            quarter_dist = db.query(
                FinancialRatio.fiscal_year,
                FinancialRatio.fiscal_quarter,
                func.count(FinancialRatio.id).label('count')
            ).filter(
                FinancialRatio.fiscal_year != None
            ).group_by(
                FinancialRatio.fiscal_year,
                FinancialRatio.fiscal_quarter
            ).order_by(
                FinancialRatio.fiscal_year.desc(),
                FinancialRatio.fiscal_quarter.desc()
            ).all()

            if quarter_dist:
                quarter_df = pd.DataFrame(quarter_dist, columns=['fiscal_year', 'fiscal_quarter', 'count'])
                quarter_df['quarter_label'] = quarter_df.apply(
                    lambda x: f"{x['fiscal_year']}" if pd.isna(x['fiscal_quarter']) else f"{x['fiscal_year']}Q{int(x['fiscal_quarter'])}",
                    axis=1
                )

                fig = px.bar(
                    quarter_df,
                    x='quarter_label',
                    y='count',
                    title='분기별 재무비율 레코드 수',
                    labels={'quarter_label': '분기', 'count': '레코드 수'},
                    color='count',
                    color_continuous_scale='Blues'
                )
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("분기별 재무비율 데이터가 없습니다.")

            st.markdown("---")

            # 계산 성공률 (NULL 체크)
            st.subheader("✅ 재무비율 계산 성공률")

            ratio_fields = [
                'roa', 'gross_profit_margin', 'operating_profit_margin', 'net_profit_margin',
                'debt_ratio', 'debt_to_equity', 'current_ratio', 'equity_ratio',
                'asset_turnover', 'revenue_growth'
            ]

            if quarterly_ratios_count > 0:
                success_rates = []
                for field in ratio_fields:
                    non_null_count = db.query(func.count(FinancialRatio.id)).filter(
                        FinancialRatio.fiscal_year != None,
                        getattr(FinancialRatio, field) != None
                    ).scalar()

                    success_rate = (non_null_count / quarterly_ratios_count * 100) if quarterly_ratios_count > 0 else 0
                    success_rates.append({
                        'ratio': field,
                        'non_null': non_null_count,
                        'success_rate': success_rate
                    })

                success_df = pd.DataFrame(success_rates)

                fig = px.bar(
                    success_df,
                    x='ratio',
                    y='success_rate',
                    title='재무비율별 계산 성공률',
                    labels={'ratio': '재무비율', 'success_rate': '성공률 (%)'},
                    color='success_rate',
                    color_continuous_scale='Greens',
                    text='success_rate'
                )
                fig.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
                fig.update_layout(height=500, xaxis_tickangle=-45)
                st.plotly_chart(fig, use_container_width=True)

                # 상세 테이블
                with st.expander("📋 재무비율별 상세 통계", expanded=False):
                    success_df['total'] = quarterly_ratios_count
                    success_df['null_count'] = quarterly_ratios_count - success_df['non_null']
                    success_df = success_df[['ratio', 'non_null', 'null_count', 'success_rate']]
                    success_df.columns = ['재무비율', '계산 성공', '계산 실패 (NULL)', '성공률 (%)']
                    success_df['성공률 (%)'] = success_df['성공률 (%)'].round(2)
                    st.dataframe(success_df, use_container_width=True, hide_index=True)
            else:
                st.warning("분기별 재무비율 데이터가 없어 성공률을 계산할 수 없습니다.")

        finally:
            db.close()

    except Exception as e:
        st.error(f"데이터 조회 중 오류 발생: {e}")
        st.exception(e)

st.markdown("---")

# =============================================================================
# 3. 샘플 종목 상세 조회
# =============================================================================
st.header("3️⃣ 샘플 종목 상세 조회")

ticker_input = st.text_input("종목코드 입력 (예: 005930)", value="005930", key="sample_ticker")

if st.button("🔍 종목 재무비율 조회", type="primary", key="sample_stock_ratios"):
    try:
        from db.connection import SessionLocal
        from models import FinancialRatio, Stock
        from sqlalchemy import and_

        db = SessionLocal()

        try:
            # 종목 조회
            stock = db.query(Stock).filter(Stock.ticker == ticker_input).first()

            if not stock:
                st.error(f"종목을 찾을 수 없습니다: {ticker_input}")
            else:
                st.success(f"✅ {stock.ticker} {stock.name} ({stock.market.value})")

                # 분기별 재무비율 조회
                quarterly_ratios = db.query(FinancialRatio).filter(
                    and_(
                        FinancialRatio.stock_id == stock.id,
                        FinancialRatio.fiscal_year != None
                    )
                ).order_by(
                    FinancialRatio.fiscal_year.desc(),
                    FinancialRatio.fiscal_quarter.desc()
                ).all()

                if quarterly_ratios:
                    st.subheader(f"📊 분기별 재무비율 ({len(quarterly_ratios)}건)")

                    # 데이터프레임 생성
                    ratio_data = []
                    for ratio in quarterly_ratios:
                        quarter_label = f"{ratio.fiscal_year}" if ratio.fiscal_quarter is None else f"{ratio.fiscal_year}Q{ratio.fiscal_quarter}"
                        ratio_data.append({
                            '분기': quarter_label,
                            '보고일': ratio.report_date,
                            'ROA': f"{ratio.roa:.2f}%" if ratio.roa else "N/A",
                            '영업이익률': f"{ratio.operating_profit_margin:.2f}%" if ratio.operating_profit_margin else "N/A",
                            '순이익률': f"{ratio.net_profit_margin:.2f}%" if ratio.net_profit_margin else "N/A",
                            '부채비율': f"{ratio.debt_ratio:.2f}%" if ratio.debt_ratio else "N/A",
                            '유동비율': f"{ratio.current_ratio:.2f}%" if ratio.current_ratio else "N/A",
                            '자기자본비율': f"{ratio.equity_ratio:.2f}%" if ratio.equity_ratio else "N/A",
                            '총자산회전율': f"{ratio.asset_turnover:.2f}회" if ratio.asset_turnover else "N/A",
                            '매출액증가율': f"{ratio.revenue_growth:.2f}%" if ratio.revenue_growth else "N/A",
                        })

                    ratio_df = pd.DataFrame(ratio_data)
                    st.dataframe(ratio_df, use_container_width=True, hide_index=True)

                    # 시계열 차트
                    st.subheader("📈 재무비율 추이")

                    # 수익성 지표
                    col1, col2 = st.columns(2)

                    with col1:
                        if any(r.roa for r in quarterly_ratios):
                            roa_data = [{'분기': f"{r.fiscal_year}Q{r.fiscal_quarter}" if r.fiscal_quarter else f"{r.fiscal_year}", 'ROA': float(r.roa)} for r in quarterly_ratios if r.roa]
                            roa_df = pd.DataFrame(roa_data)
                            fig = px.line(roa_df, x='분기', y='ROA', title='ROA 추이', markers=True)
                            fig.update_layout(height=300)
                            st.plotly_chart(fig, use_container_width=True)

                    with col2:
                        if any(r.operating_profit_margin for r in quarterly_ratios):
                            opm_data = [{'분기': f"{r.fiscal_year}Q{r.fiscal_quarter}" if r.fiscal_quarter else f"{r.fiscal_year}", '영업이익률': float(r.operating_profit_margin)} for r in quarterly_ratios if r.operating_profit_margin]
                            opm_df = pd.DataFrame(opm_data)
                            fig = px.line(opm_df, x='분기', y='영업이익률', title='영업이익률 추이', markers=True)
                            fig.update_layout(height=300)
                            st.plotly_chart(fig, use_container_width=True)

                    # 안정성 지표
                    col1, col2 = st.columns(2)

                    with col1:
                        if any(r.debt_ratio for r in quarterly_ratios):
                            debt_data = [{'분기': f"{r.fiscal_year}Q{r.fiscal_quarter}" if r.fiscal_quarter else f"{r.fiscal_year}", '부채비율': float(r.debt_ratio)} for r in quarterly_ratios if r.debt_ratio]
                            debt_df = pd.DataFrame(debt_data)
                            fig = px.line(debt_df, x='분기', y='부채비율', title='부채비율 추이', markers=True)
                            fig.update_layout(height=300)
                            st.plotly_chart(fig, use_container_width=True)

                    with col2:
                        if any(r.current_ratio for r in quarterly_ratios):
                            current_data = [{'분기': f"{r.fiscal_year}Q{r.fiscal_quarter}" if r.fiscal_quarter else f"{r.fiscal_year}", '유동비율': float(r.current_ratio)} for r in quarterly_ratios if r.current_ratio]
                            current_df = pd.DataFrame(current_data)
                            fig = px.line(current_df, x='분기', y='유동비율', title='유동비율 추이', markers=True)
                            fig.update_layout(height=300)
                            st.plotly_chart(fig, use_container_width=True)

                else:
                    st.warning(f"{stock.ticker} {stock.name}의 분기별 재무비율 데이터가 없습니다.")

                    # 재무제표 확인
                    from models import FinancialStatement
                    stmt_count = db.query(func.count(FinancialStatement.id)).filter(
                        FinancialStatement.stock_id == stock.id
                    ).scalar()

                    if stmt_count > 0:
                        st.info(f"💡 재무제표는 {stmt_count}건 있습니다. 재무비율 계산을 실행하세요:")
                        st.code(f"python scripts/calculate_quarterly_ratios.py --ticker {ticker_input} --all-quarters")
                    else:
                        st.warning("재무제표 데이터도 없습니다.")

        finally:
            db.close()

    except Exception as e:
        st.error(f"종목 조회 중 오류 발생: {e}")
        st.exception(e)

st.markdown("---")

# =============================================================================
# 4. 실행 가이드
# =============================================================================
st.header("4️⃣ 실행 가이드")

st.markdown("""
### 📋 재무비율 계산 실행 방법

#### 1. 단일 종목 계산
```bash
# 삼성전자 전체 분기 계산
python scripts/calculate_quarterly_ratios.py --ticker 005930 --all-quarters

# 삼성전자 2024Q4만 계산
python scripts/calculate_quarterly_ratios.py --ticker 005930 --year 2024 --quarter 4
```

#### 2. 전체 종목 계산
```bash
# 전체 종목, 전체 분기 계산 (시간 소요)
python scripts/calculate_quarterly_ratios.py --all-stocks

# 테스트 (상위 10개 종목만)
python scripts/calculate_quarterly_ratios.py --all-stocks --limit 10

# 2024년만 계산
python scripts/calculate_quarterly_ratios.py --all-stocks --year 2024
```

#### 3. PostgreSQL 뷰 생성
```bash
# 일별 + 분기별 통합 조회용 뷰 생성
python scripts/create_combined_ratios_view.py
```

#### 4. 뷰를 사용한 조회
```python
from db.connection import SessionLocal
from sqlalchemy import text

db = SessionLocal()

# 특정 날짜의 모든 재무비율 조회
result = db.execute(text('''
    SELECT * FROM vw_daily_combined_ratios
    WHERE ticker = '005930' AND date = '2024-12-31'
''')).fetchone()

print(f"PER: {result.per} (일별)")
print(f"ROA: {result.roa}% (분기: {result.fiscal_year}Q{result.fiscal_quarter})")

db.close()
```

### 📚 참고 문서
- [QUARTERLY_RATIOS_CALCULATION_GUIDE.md](../docs/QUARTERLY_RATIOS_CALCULATION_GUIDE.md) - 완전한 사용 가이드
- [FINANCIAL_RATIOS_COMPARISON.md](../docs/FINANCIAL_RATIOS_COMPARISON.md) - 재무비율 계산 가능성 비교
- [DAILY_VS_QUARTERLY_RATIOS_STRATEGY.md](../docs/DAILY_VS_QUARTERLY_RATIOS_STRATEGY.md) - 하이브리드 전략 상세
""")

st.markdown("---")

# Footer
st.caption(f"최종 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
st.caption("Day 14-15: 재무제표 기반 재무비율 계산 (하이브리드 전략)")
