"""데이터 품질 점검 페이지

수집된 데이터의 품질 및 완전성 검증
"""

import streamlit as st
from pathlib import Path
import sys
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Page configuration
st.set_page_config(
    page_title="데이터 품질 점검",
    page_icon="🔍",
    layout="wide"
)

st.title("🔍 데이터 품질 점검")
st.markdown("수집된 데이터의 품질, 완전성, 일관성 검증")
st.markdown("---")

# Tab navigation
tab1, tab2, tab3, tab4 = st.tabs(["📊 종목 데이터", "💹 시세 데이터", "📑 재무제표", "📈 전체 요약"])

# Tab 1: Stock Data Quality
with tab1:
    st.subheader("📊 종목 데이터 품질 점검")

    if st.button("종목 데이터 검증", key="stock_quality"):
        try:
            from db.connection import SessionLocal
            from models import Stock
            from sqlalchemy import func, and_, or_

            db = SessionLocal()

            try:
                # Total stocks
                total_stocks = db.query(func.count(Stock.id)).scalar()

                st.metric("총 종목 수", f"{total_stocks:,}개")

                # NULL checks
                st.markdown("#### 1️⃣ 필수 필드 NULL 체크")

                null_checks = []

                # Ticker NULL
                null_ticker = db.query(func.count(Stock.id)).filter(
                    or_(Stock.ticker == None, Stock.ticker == '')
                ).scalar()
                null_checks.append(('ticker (종목코드)', null_ticker, (1 - null_ticker/total_stocks)*100 if total_stocks > 0 else 0))

                # Name NULL
                null_name = db.query(func.count(Stock.id)).filter(
                    or_(Stock.name == None, Stock.name == '')
                ).scalar()
                null_checks.append(('name (종목명)', null_name, (1 - null_name/total_stocks)*100 if total_stocks > 0 else 0))

                # Market NULL
                null_market = db.query(func.count(Stock.id)).filter(Stock.market == None).scalar()
                null_checks.append(('market (시장구분)', null_market, (1 - null_market/total_stocks)*100 if total_stocks > 0 else 0))

                null_df = pd.DataFrame(null_checks, columns=['필드', 'NULL 건수', '완전성 (%)'])
                null_df['완전성 (%)'] = null_df['완전성 (%)'].round(2)

                st.dataframe(null_df, use_container_width=True, hide_index=True)

                # Overall completeness score
                avg_completeness = null_df['완전성 (%)'].mean()

                if avg_completeness >= 99:
                    st.success(f"✅ 데이터 완전성 우수 (평균 {avg_completeness:.2f}%)")
                elif avg_completeness >= 95:
                    st.warning(f"⚠️ 데이터 완전성 보통 (평균 {avg_completeness:.2f}%)")
                else:
                    st.error(f"❌ 데이터 완전성 개선 필요 (평균 {avg_completeness:.2f}%)")

                # Duplicates check
                st.markdown("#### 2️⃣ 중복 데이터 검사")

                duplicate_tickers = db.query(
                    Stock.ticker,
                    func.count(Stock.id).label('count')
                ).group_by(Stock.ticker).having(func.count(Stock.id) > 1).all()

                if duplicate_tickers:
                    st.error(f"❌ {len(duplicate_tickers)}개의 중복 종목코드 발견")
                    dup_df = pd.DataFrame([(d.ticker, d.count) for d in duplicate_tickers],
                                         columns=['종목코드', '중복 횟수'])
                    st.dataframe(dup_df, use_container_width=True, hide_index=True)
                else:
                    st.success("✅ 중복 종목코드 없음")

                # Active stocks
                st.markdown("#### 3️⃣ 상장/상폐 상태")

                active_count = db.query(func.count(Stock.id)).filter(Stock.is_active == True).scalar()
                inactive_count = total_stocks - active_count

                status_df = pd.DataFrame([
                    {'상태': '상장 (Active)', '종목 수': active_count, '비율': f"{active_count/total_stocks*100:.1f}%"},
                    {'상태': '상폐 (Inactive)', '종목 수': inactive_count, '비율': f"{inactive_count/total_stocks*100:.1f}%"}
                ])

                st.dataframe(status_df, use_container_width=True, hide_index=True)

            finally:
                db.close()

        except Exception as e:
            st.error(f"❌ 오류: {e}")

# Tab 2: Price Data Quality
with tab2:
    st.subheader("💹 시세 데이터 품질 점검")

    if st.button("시세 데이터 검증", key="price_quality"):
        try:
            from db.connection import SessionLocal
            from models import Stock, DailyPrice
            from sqlalchemy import func, and_, or_

            db = SessionLocal()

            try:
                # Total price records
                total_prices = db.query(func.count(DailyPrice.id)).scalar()
                st.metric("총 시세 레코드", f"{total_prices:,}건")

                # Coverage analysis
                st.markdown("#### 1️⃣ 종목별 커버리지")

                total_stocks = db.query(func.count(Stock.id)).scalar()
                stocks_with_prices = db.query(func.count(func.distinct(DailyPrice.stock_id))).scalar()
                stocks_without_prices = total_stocks - stocks_with_prices

                coverage_df = pd.DataFrame([
                    {'구분': '시세 데이터 있음', '종목 수': stocks_with_prices, '비율': f"{stocks_with_prices/total_stocks*100:.1f}%"},
                    {'구분': '시세 데이터 없음', '종목 수': stocks_without_prices, '비율': f"{stocks_without_prices/total_stocks*100:.1f}%"}
                ])

                st.dataframe(coverage_df, use_container_width=True, hide_index=True)

                if stocks_without_prices > 0:
                    st.warning(f"⚠️ {stocks_without_prices}개 종목에 시세 데이터가 없습니다")

                # NULL checks in OHLCV
                st.markdown("#### 2️⃣ OHLCV 필드 NULL 체크 (샘플 1,000건)")

                sample_prices = db.query(DailyPrice).limit(1000).all()

                if sample_prices:
                    null_checks = []

                    null_open = sum(1 for p in sample_prices if p.open_price is None)
                    null_checks.append(('open_price', null_open, (1 - null_open/len(sample_prices))*100))

                    null_high = sum(1 for p in sample_prices if p.high_price is None)
                    null_checks.append(('high_price', null_high, (1 - null_high/len(sample_prices))*100))

                    null_low = sum(1 for p in sample_prices if p.low_price is None)
                    null_checks.append(('low_price', null_low, (1 - null_low/len(sample_prices))*100))

                    null_close = sum(1 for p in sample_prices if p.close_price is None)
                    null_checks.append(('close_price', null_close, (1 - null_close/len(sample_prices))*100))

                    null_volume = sum(1 for p in sample_prices if p.volume is None)
                    null_checks.append(('volume', null_volume, (1 - null_volume/len(sample_prices))*100))

                    null_df = pd.DataFrame(null_checks, columns=['필드', 'NULL 건수', '완전성 (%)'])
                    null_df['완전성 (%)'] = null_df['완전성 (%)'].round(2)

                    st.dataframe(null_df, use_container_width=True, hide_index=True)

                    avg_completeness = null_df['완전성 (%)'].mean()

                    if avg_completeness >= 99:
                        st.success(f"✅ OHLCV 데이터 완전성 우수 (평균 {avg_completeness:.2f}%)")
                    else:
                        st.warning(f"⚠️ OHLCV 데이터 품질 확인 필요 (평균 {avg_completeness:.2f}%)")

                # Logic errors (High < Low, Close > High, etc.)
                st.markdown("#### 3️⃣ 논리 오류 검사 (OHLCV 관계)")

                # High >= Low
                logic_error1 = db.query(func.count(DailyPrice.id)).filter(
                    DailyPrice.high_price < DailyPrice.low_price
                ).scalar()

                # Close between Low and High
                logic_error2 = db.query(func.count(DailyPrice.id)).filter(
                    or_(
                        DailyPrice.close_price > DailyPrice.high_price,
                        DailyPrice.close_price < DailyPrice.low_price
                    )
                ).scalar()

                # Open between Low and High
                logic_error3 = db.query(func.count(DailyPrice.id)).filter(
                    or_(
                        DailyPrice.open_price > DailyPrice.high_price,
                        DailyPrice.open_price < DailyPrice.low_price
                    )
                ).scalar()

                # Volume >= 0
                logic_error4 = db.query(func.count(DailyPrice.id)).filter(
                    DailyPrice.volume < 0
                ).scalar()

                logic_df = pd.DataFrame([
                    {'검사 항목': 'High >= Low', '오류 건수': logic_error1, '오류율': f"{logic_error1/total_prices*100:.4f}%"},
                    {'검사 항목': 'Low <= Close <= High', '오류 건수': logic_error2, '오류율': f"{logic_error2/total_prices*100:.4f}%"},
                    {'검사 항목': 'Low <= Open <= High', '오류 건수': logic_error3, '오류율': f"{logic_error3/total_prices*100:.4f}%"},
                    {'검사 항목': 'Volume >= 0', '오류 건수': logic_error4, '오류율': f"{logic_error4/total_prices*100:.4f}%"}
                ])

                st.dataframe(logic_df, use_container_width=True, hide_index=True)

                total_logic_errors = logic_error1 + logic_error2 + logic_error3 + logic_error4

                if total_logic_errors == 0:
                    st.success("✅ 논리 오류 없음")
                else:
                    st.warning(f"⚠️ 총 {total_logic_errors}건의 논리 오류 발견 (전체의 {total_logic_errors/total_prices*100:.4f}%)")

                # Date continuity check
                st.markdown("#### 4️⃣ 날짜 연속성 검사 (샘플 종목)")

                sample_stock = db.query(Stock).filter(Stock.ticker == '005930').first()

                if sample_stock:
                    prices = db.query(DailyPrice.date).filter(
                        DailyPrice.stock_id == sample_stock.id
                    ).order_by(DailyPrice.date).all()

                    if len(prices) > 1:
                        dates = [p.date for p in prices]
                        date_diffs = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]

                        # Find large gaps (> 7 days, accounting for weekends)
                        large_gaps = [d for d in date_diffs if d > 7]

                        st.info(f"📊 {sample_stock.name} ({sample_stock.ticker}): 총 {len(prices)}일의 데이터")

                        if large_gaps:
                            st.warning(f"⚠️ 7일 이상 데이터 공백: {len(large_gaps)}회 (최대 {max(large_gaps)}일)")
                        else:
                            st.success("✅ 날짜 연속성 양호")

            finally:
                db.close()

        except Exception as e:
            st.error(f"❌ 오류: {e}")

# Tab 3: Financial Statement Quality
with tab3:
    st.subheader("📑 재무제표 데이터 품질 점검")

    if st.button("재무제표 데이터 검증", key="financial_quality"):
        try:
            from db.connection import SessionLocal
            from models import Stock, FinancialStatement
            from sqlalchemy import func

            db = SessionLocal()

            try:
                total_financials = db.query(func.count(FinancialStatement.id)).scalar()
                st.metric("총 재무제표 건수", f"{total_financials:,}건")

                # Coverage
                st.markdown("#### 1️⃣ 종목별 커버리지")

                total_stocks = db.query(func.count(Stock.id)).scalar()
                stocks_with_financials = db.query(func.count(func.distinct(FinancialStatement.stock_id))).scalar()
                stocks_without_financials = total_stocks - stocks_with_financials

                coverage_df = pd.DataFrame([
                    {'구분': '재무제표 있음', '종목 수': stocks_with_financials, '비율': f"{stocks_with_financials/total_stocks*100:.1f}%"},
                    {'구분': '재무제표 없음', '종목 수': stocks_without_financials, '비율': f"{stocks_without_financials/total_stocks*100:.1f}%"}
                ])

                st.dataframe(coverage_df, use_container_width=True, hide_index=True)

                # JSONB fields NULL check
                st.markdown("#### 2️⃣ JSONB 필드 NULL 체크")

                null_balance_sheet = db.query(func.count(FinancialStatement.id)).filter(
                    FinancialStatement.balance_sheet == None
                ).scalar()

                null_income = db.query(func.count(FinancialStatement.id)).filter(
                    FinancialStatement.income_statement == None
                ).scalar()

                null_cashflow = db.query(func.count(FinancialStatement.id)).filter(
                    FinancialStatement.cash_flow == None
                ).scalar()

                jsonb_df = pd.DataFrame([
                    {'필드': 'balance_sheet (재무상태표)', 'NULL 건수': null_balance_sheet, '존재율': f"{(1-null_balance_sheet/total_financials)*100:.1f}%"},
                    {'필드': 'income_statement (손익계산서)', 'NULL 건수': null_income, '존재율': f"{(1-null_income/total_financials)*100:.1f}%"},
                    {'필드': 'cash_flow (현금흐름표)', 'NULL 건수': null_cashflow, '존재율': f"{(1-null_cashflow/total_financials)*100:.1f}%"}
                ])

                st.dataframe(jsonb_df, use_container_width=True, hide_index=True)

                # Key accounts existence (sample)
                st.markdown("#### 3️⃣ 핵심 계정과목 존재율 (샘플 100건)")

                sample_financials = db.query(FinancialStatement).limit(100).all()

                if sample_financials:
                    key_accounts_checks = []

                    # Balance sheet
                    bs_keys = ['자산총계', '부채총계', '자본총계']
                    for key in bs_keys:
                        count = sum(1 for f in sample_financials if f.balance_sheet and key in str(f.balance_sheet))
                        key_accounts_checks.append((f'재무상태표 - {key}', count, f"{count/len(sample_financials)*100:.1f}%"))

                    # Income statement
                    is_keys = ['매출액', '영업이익', '당기순이익']
                    for key in is_keys:
                        count = sum(1 for f in sample_financials if f.income_statement and key in str(f.income_statement))
                        key_accounts_checks.append((f'손익계산서 - {key}', count, f"{count/len(sample_financials)*100:.1f}%"))

                    accounts_df = pd.DataFrame(key_accounts_checks, columns=['계정과목', '존재 건수', '존재율'])
                    st.dataframe(accounts_df, use_container_width=True, hide_index=True)

                    # Quality score
                    avg_existence = sum(c[1] for c in key_accounts_checks) / (len(key_accounts_checks) * len(sample_financials)) * 100

                    if avg_existence >= 90:
                        st.success(f"✅ 핵심 계정과목 존재율 우수 (평균 {avg_existence:.1f}%)")
                    elif avg_existence >= 70:
                        st.warning(f"⚠️ 핵심 계정과목 존재율 보통 (평균 {avg_existence:.1f}%)")
                    else:
                        st.error(f"❌ 핵심 계정과목 존재율 개선 필요 (평균 {avg_existence:.1f}%)")

                # Year distribution quality
                st.markdown("#### 4️⃣ 연도별 데이터 분포")

                year_dist = db.query(
                    FinancialStatement.fiscal_year,
                    func.count(FinancialStatement.id).label('count')
                ).group_by(FinancialStatement.fiscal_year).order_by(FinancialStatement.fiscal_year.desc()).limit(10).all()

                if year_dist:
                    year_df = pd.DataFrame([(y.fiscal_year, y.count) for y in year_dist], columns=['회계연도', '건수'])
                    st.dataframe(year_df, use_container_width=True, hide_index=True)
                    st.line_chart(year_df.set_index('회계연도'))

            finally:
                db.close()

        except Exception as e:
            st.error(f"❌ 오류: {e}")

# Tab 4: Overall Summary
with tab4:
    st.subheader("📈 전체 데이터 품질 요약")

    if st.button("전체 품질 점수 계산", type="primary", key="overall_quality"):
        try:
            from db.connection import SessionLocal
            from models import Stock, DailyPrice, FinancialStatement
            from sqlalchemy import func, or_

            db = SessionLocal()

            try:
                scores = []

                # 1. Stock data quality
                total_stocks = db.query(func.count(Stock.id)).scalar()
                null_ticker = db.query(func.count(Stock.id)).filter(
                    or_(Stock.ticker == None, Stock.ticker == '')
                ).scalar()
                stock_completeness = (1 - null_ticker/total_stocks) * 100 if total_stocks > 0 else 0
                scores.append(('종목 데이터 완전성', stock_completeness))

                # 2. Price data coverage
                stocks_with_prices = db.query(func.count(func.distinct(DailyPrice.stock_id))).scalar()
                price_coverage = (stocks_with_prices / total_stocks * 100) if total_stocks > 0 else 0
                scores.append(('시세 데이터 커버리지', price_coverage))

                # 3. Price data completeness (sample)
                sample_prices = db.query(DailyPrice).limit(1000).all()
                if sample_prices:
                    null_count = sum(1 for p in sample_prices if p.close_price is None)
                    price_completeness = (1 - null_count/len(sample_prices)) * 100
                    scores.append(('시세 데이터 완전성', price_completeness))

                # 4. Financial data coverage
                stocks_with_financials = db.query(func.count(func.distinct(FinancialStatement.stock_id))).scalar()
                financial_coverage = (stocks_with_financials / total_stocks * 100) if total_stocks > 0 else 0
                scores.append(('재무제표 커버리지', financial_coverage))

                # 5. Financial data completeness
                total_financials = db.query(func.count(FinancialStatement.id)).scalar()
                if total_financials > 0:
                    null_balance = db.query(func.count(FinancialStatement.id)).filter(
                        FinancialStatement.balance_sheet == None
                    ).scalar()
                    financial_completeness = (1 - null_balance/total_financials) * 100
                    scores.append(('재무제표 완전성', financial_completeness))

                # Display scores
                scores_df = pd.DataFrame(scores, columns=['평가 항목', '점수 (%)'])
                scores_df['점수 (%)'] = scores_df['점수 (%)'].round(2)

                st.dataframe(scores_df, use_container_width=True, hide_index=True)

                # Overall score
                overall_score = scores_df['점수 (%)'].mean()

                st.markdown("---")
                st.markdown("### 🎯 종합 품질 점수")

                col1, col2, col3 = st.columns([2, 1, 1])

                with col1:
                    st.metric("종합 점수", f"{overall_score:.2f}점 / 100점")

                with col2:
                    if overall_score >= 90:
                        st.success("✅ 우수")
                    elif overall_score >= 70:
                        st.warning("⚠️ 양호")
                    else:
                        st.error("❌ 개선필요")

                with col3:
                    grade = 'A' if overall_score >= 90 else 'B' if overall_score >= 80 else 'C' if overall_score >= 70 else 'D'
                    st.metric("등급", grade)

                # Recommendations
                st.markdown("---")
                st.markdown("### 💡 개선 권장사항")

                recommendations = []

                if stock_completeness < 99:
                    recommendations.append("- 종목 데이터의 NULL 값을 확인하고 보완하세요")

                if price_coverage < 95:
                    recommendations.append(f"- {total_stocks - stocks_with_prices}개 종목의 시세 데이터를 수집하세요")

                if financial_coverage < 90:
                    recommendations.append(f"- {total_stocks - stocks_with_financials}개 종목의 재무제표를 수집하세요")

                if len(recommendations) == 0:
                    st.success("✅ 모든 데이터 품질 지표가 우수합니다!")
                else:
                    for rec in recommendations:
                        st.info(rec)

                # Visualization
                st.markdown("---")
                st.markdown("### 📊 품질 점수 시각화")

                import plotly.graph_objects as go

                fig = go.Figure(go.Bar(
                    x=scores_df['점수 (%)'],
                    y=scores_df['평가 항목'],
                    orientation='h',
                    marker=dict(
                        color=scores_df['점수 (%)'],
                        colorscale='RdYlGn',
                        cmin=0,
                        cmax=100
                    ),
                    text=scores_df['점수 (%)'].round(1),
                    textposition='auto'
                ))

                fig.update_layout(
                    title='데이터 품질 평가 항목별 점수',
                    xaxis_title='점수 (%)',
                    yaxis_title='평가 항목',
                    height=400,
                    xaxis=dict(range=[0, 100])
                )

                st.plotly_chart(fig, use_container_width=True)

            finally:
                db.close()

        except Exception as e:
            st.error(f"❌ 오류: {e}")

# Footer
st.markdown("---")
st.info("""
💡 **데이터 품질 기준**

- **우수 (90점 이상)**: 데이터가 안정적이며 분석 및 백테스팅에 사용 가능
- **양호 (70-89점)**: 일부 개선이 필요하나 기본적인 분석은 가능
- **개선필요 (70점 미만)**: 데이터 품질 개선이 필요하며, 추가 수집 또는 정제 작업 권장
""")
