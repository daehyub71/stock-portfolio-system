"""Week 3 (Day 11-12) 완료 체크 페이지

Day 11-12: 재무제표 수집 시작 및 계속
"""

import streamlit as st
from pathlib import Path
import sys
from datetime import datetime
import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Page configuration
st.set_page_config(
    page_title="Week 3 (Day 11-12) 체크",
    page_icon="✅",
    layout="wide"
)

st.title("✅ Week 3 (Day 11-12) 완료 체크")
st.markdown("**기간**: Day 11-12 | **목표**: 재무제표 수집 시작 (1,500개 종목)")
st.markdown("---")

# Progress tracker
progress_data = {
    "Day 11": {"완료": True, "description": "첫 500개 종목 재무제표 수집", "target": "10,000건"},
    "Day 12": {"완료": True, "description": "추가 1,000개 종목 수집 및 표준화", "target": "누적 30,000건"},
}

# Calculate overall progress
total_days = len(progress_data)
completed_days = sum(1 for day in progress_data.values() if day["완료"])
progress_percentage = (completed_days / total_days) * 100

# Overall progress
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("전체 진행률", f"{progress_percentage:.0f}%", f"{completed_days}/{total_days} days")
with col2:
    st.metric("완료", completed_days, delta=None if completed_days == total_days else f"{total_days - completed_days}일 남음")
with col3:
    st.metric("상태", "✅ 완료" if completed_days == total_days else "🚧 진행중")

st.progress(progress_percentage / 100)
st.markdown("---")

# Overall Financial Data Statistics
st.subheader("📊 재무제표 데이터 통계")

if st.button("전체 재무제표 통계 조회", type="primary", key="overall_financial_stats"):
    try:
        from db.connection import SessionLocal
        from models import FinancialStatement, Stock
        from sqlalchemy import func

        db = SessionLocal()

        try:
            # Total financial statements
            total_financials = db.query(func.count(FinancialStatement.id)).scalar()

            # Unique stocks with financials
            stocks_with_financials = db.query(
                func.count(func.distinct(FinancialStatement.stock_id))
            ).scalar()

            # Total stocks
            total_stocks = db.query(func.count(Stock.id)).scalar()

            # Coverage
            coverage = (stocks_with_financials / total_stocks * 100) if total_stocks > 0 else 0

            # Year range
            year_range = db.query(
                func.min(FinancialStatement.fiscal_year),
                func.max(FinancialStatement.fiscal_year)
            ).first()

            # Display metrics
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric(
                    "총 재무제표 건수",
                    f"{total_financials:,}건",
                    help="수집된 전체 재무제표 데이터"
                )

            with col2:
                st.metric(
                    "재무제표가 있는 종목",
                    f"{stocks_with_financials:,}개",
                    delta=f"{coverage:.1f}% 커버리지",
                    help="최소 1건 이상의 재무제표가 있는 종목"
                )

            with col3:
                if stocks_with_financials > 0:
                    avg_per_stock = total_financials / stocks_with_financials
                    st.metric(
                        "평균 재무제표/종목",
                        f"{avg_per_stock:.1f}건",
                        help="종목당 평균 재무제표 건수"
                    )

            with col4:
                if year_range[0] and year_range[1]:
                    st.metric(
                        "데이터 기간",
                        f"{year_range[0]} ~ {year_range[1]}",
                        delta=f"{year_range[1] - year_range[0] + 1}년",
                        help="회계연도 기준"
                    )

            # Expected vs Actual (Day 11-12 target)
            st.markdown("---")
            st.subheader("🎯 Day 11-12 목표 대비 달성률")

            expected_stocks_day12 = 1500  # Day 11: 500, Day 12: +1000
            expected_records_per_stock = 20  # 5년 × 4분기
            expected_total_day12 = expected_stocks_day12 * expected_records_per_stock

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric(
                    "목표 종목 수 (Day 11-12)",
                    f"{expected_stocks_day12:,}개",
                    delta=f"{stocks_with_financials - expected_stocks_day12:+,}개"
                )

            with col2:
                st.metric(
                    "목표 재무제표 건수",
                    f"{expected_total_day12:,}건",
                    delta=f"{total_financials - expected_total_day12:+,}건"
                )

            with col3:
                achievement = (total_financials / expected_total_day12 * 100) if expected_total_day12 > 0 else 0
                st.metric(
                    "달성률",
                    f"{achievement:.1f}%",
                    delta="목표 대비"
                )

        finally:
            db.close()

    except Exception as e:
        st.error(f"❌ 오류: {e}")

# Statement Type Distribution
st.markdown("---")
st.subheader("📋 재무제표 유형별 분포")

if st.button("유형별 분석", key="statement_type_dist"):
    try:
        from db.connection import SessionLocal
        from models import FinancialStatement
        from sqlalchemy import func

        db = SessionLocal()

        try:
            type_dist = db.query(
                FinancialStatement.statement_type,
                func.count(FinancialStatement.id).label('count')
            ).group_by(FinancialStatement.statement_type).all()

            if type_dist:
                df = pd.DataFrame([
                    {
                        '유형': t.statement_type.value if hasattr(t.statement_type, 'value') else str(t.statement_type),
                        '건수': t.count
                    }
                    for t in type_dist
                ])

                col1, col2 = st.columns(2)
                with col1:
                    st.dataframe(df, use_container_width=True, hide_index=True)
                with col2:
                    st.bar_chart(df.set_index('유형'))

            else:
                st.warning("⚠️ 재무제표 유형 데이터가 없습니다")

        finally:
            db.close()

    except Exception as e:
        st.error(f"❌ 오류: {e}")

# Fiscal Year Distribution
st.markdown("---")
st.subheader("📅 회계연도별 분포")

if st.button("연도별 분석", key="fiscal_year_dist"):
    try:
        from db.connection import SessionLocal
        from models import FinancialStatement
        from sqlalchemy import func

        db = SessionLocal()

        try:
            year_dist = db.query(
                FinancialStatement.fiscal_year,
                func.count(FinancialStatement.id).label('count')
            ).group_by(FinancialStatement.fiscal_year).order_by(FinancialStatement.fiscal_year.desc()).all()

            if year_dist:
                df = pd.DataFrame([
                    {'회계연도': y.fiscal_year, '건수': y.count}
                    for y in year_dist
                ])

                col1, col2 = st.columns(2)
                with col1:
                    st.dataframe(df, use_container_width=True, hide_index=True)
                with col2:
                    st.line_chart(df.set_index('회계연도'))

            else:
                st.warning("⚠️ 회계연도별 데이터가 없습니다")

        finally:
            db.close()

    except Exception as e:
        st.error(f"❌ 오류: {e}")

# Quarter Distribution
st.markdown("---")
st.subheader("📊 분기별 분포 (분기보고서만)")

if st.button("분기별 분석", key="quarter_dist"):
    try:
        from db.connection import SessionLocal
        from models import FinancialStatement, StatementType
        from sqlalchemy import func

        db = SessionLocal()

        try:
            quarter_dist = db.query(
                FinancialStatement.fiscal_quarter,
                func.count(FinancialStatement.id).label('count')
            ).filter(
                FinancialStatement.statement_type == StatementType.QUARTERLY
            ).group_by(FinancialStatement.fiscal_quarter).order_by(FinancialStatement.fiscal_quarter).all()

            if quarter_dist:
                df = pd.DataFrame([
                    {'분기': f"{q.fiscal_quarter}Q" if q.fiscal_quarter else 'N/A', '건수': q.count}
                    for q in quarter_dist
                ])

                col1, col2 = st.columns(2)
                with col1:
                    st.dataframe(df, use_container_width=True, hide_index=True)
                with col2:
                    st.bar_chart(df.set_index('분기'))

            else:
                st.info("📌 분기보고서 데이터가 없습니다 (연간 보고서만 수집된 경우)")

        finally:
            db.close()

    except Exception as e:
        st.error(f"❌ 오류: {e}")

# JSONB Data Structure Validation
st.markdown("---")
st.subheader("🔍 JSONB 데이터 구조 검증")

if st.button("필수 계정과목 존재율 분석", key="jsonb_validation"):
    try:
        from db.connection import SessionLocal, engine
        from models import FinancialStatement
        from sqlalchemy import func, text

        db = SessionLocal()

        try:
            # Sample 100 recent statements
            sample_statements = db.query(FinancialStatement).order_by(
                FinancialStatement.id.desc()
            ).limit(100).all()

            if sample_statements:
                st.info(f"📊 최근 {len(sample_statements)}건의 재무제표 샘플 분석")

                # Check key accounts existence
                balance_sheet_keys = ['자산총계', '부채총계', '자본총계', '유동자산', '비유동자산']
                income_keys = ['매출액', '영업이익', '당기순이익']
                cashflow_keys = ['영업활동현금흐름', '투자활동현금흐름', '재무활동현금흐름']

                results = []

                for key in balance_sheet_keys:
                    count = sum(1 for s in sample_statements
                                if s.balance_sheet and key in str(s.balance_sheet))
                    results.append({
                        '구분': '재무상태표',
                        '계정과목': key,
                        '존재 건수': count,
                        '존재율': f"{count/len(sample_statements)*100:.1f}%"
                    })

                for key in income_keys:
                    count = sum(1 for s in sample_statements
                                if s.income_statement and key in str(s.income_statement))
                    results.append({
                        '구분': '손익계산서',
                        '계정과목': key,
                        '존재 건수': count,
                        '존재율': f"{count/len(sample_statements)*100:.1f}%"
                    })

                for key in cashflow_keys:
                    count = sum(1 for s in sample_statements
                                if s.cash_flow and key in str(s.cash_flow))
                    results.append({
                        '구분': '현금흐름표',
                        '계정과목': key,
                        '존재 건수': count,
                        '존재율': f"{count/len(sample_statements)*100:.1f}%"
                    })

                results_df = pd.DataFrame(results)
                st.dataframe(results_df, use_container_width=True, hide_index=True)

                # Overall quality score
                total_checks = len(results)
                high_quality = sum(1 for r in results if int(r['존재 건수']) > len(sample_statements) * 0.8)
                quality_score = (high_quality / total_checks * 100) if total_checks > 0 else 0

                if quality_score >= 80:
                    st.success(f"✅ 데이터 품질 우수 (품질 점수: {quality_score:.1f}%)")
                elif quality_score >= 60:
                    st.warning(f"⚠️ 데이터 품질 보통 (품질 점수: {quality_score:.1f}%)")
                else:
                    st.error(f"❌ 데이터 품질 개선 필요 (품질 점수: {quality_score:.1f}%)")

            else:
                st.warning("⚠️ 재무제표 데이터가 없습니다")

        finally:
            db.close()

    except Exception as e:
        st.error(f"❌ 오류: {e}")

# Sample Financial Statement Viewer
st.markdown("---")
st.subheader("📄 샘플 재무제표 조회")

ticker_input = st.text_input("종목 코드 입력 (예: 005930)", value="005930", key="financial_ticker")

if st.button("재무제표 조회", key="view_financial"):
    try:
        from db.connection import SessionLocal
        from models import Stock, FinancialStatement
        from sqlalchemy import desc
        import json

        db = SessionLocal()

        try:
            stock = db.query(Stock).filter(Stock.ticker == ticker_input).first()

            if stock:
                st.success(f"✅ {stock.name} ({stock.ticker})")

                # Get financial statements
                financials = db.query(FinancialStatement).filter(
                    FinancialStatement.stock_id == stock.id
                ).order_by(
                    desc(FinancialStatement.fiscal_year),
                    desc(FinancialStatement.fiscal_quarter)
                ).limit(5).all()

                if financials:
                    st.info(f"📊 최근 {len(financials)}건의 재무제표")

                    for fs in financials:
                        quarter_str = f"{fs.fiscal_quarter}Q" if fs.fiscal_quarter else "연간"
                        type_str = fs.statement_type.value if hasattr(fs.statement_type, 'value') else str(fs.statement_type)

                        with st.expander(f"📋 {fs.fiscal_year}년 {quarter_str} ({type_str})"):
                            col1, col2 = st.columns(2)

                            with col1:
                                st.markdown("**재무상태표**")
                                if fs.balance_sheet:
                                    st.json(fs.balance_sheet)
                                else:
                                    st.warning("데이터 없음")

                            with col2:
                                st.markdown("**손익계산서**")
                                if fs.income_statement:
                                    st.json(fs.income_statement)
                                else:
                                    st.warning("데이터 없음")

                            if fs.cash_flow:
                                st.markdown("**현금흐름표**")
                                st.json(fs.cash_flow)

                else:
                    st.warning(f"⚠️ {stock.name} 종목의 재무제표가 없습니다")

            else:
                st.error(f"❌ 종목 코드 '{ticker_input}'를 찾을 수 없습니다")

        finally:
            db.close()

    except Exception as e:
        st.error(f"❌ 오류: {e}")

# Batch Collection Status
st.markdown("---")
st.subheader("💾 재무제표 수집 체크포인트")

checkpoint_dir = project_root / "data" / "checkpoints"

if checkpoint_dir.exists():
    checkpoint_files = list(checkpoint_dir.glob("financial_checkpoint_*.json"))

    if checkpoint_files:
        st.success(f"✅ {len(checkpoint_files)}개 체크포인트 파일 발견")

        import json
        checkpoint_data = []

        for cp_file in sorted(checkpoint_files):
            try:
                with open(cp_file, 'r') as f:
                    data = json.load(f)
                    checkpoint_data.append({
                        '파일명': cp_file.name,
                        '그룹 ID': data.get('group_id', 'N/A'),
                        '완료': '✅' if data.get('completed', False) else '🚧',
                        '성공': data.get('successful_stocks', 0),
                        '실패': data.get('failed_stocks', 0),
                        '진행률': f"{data.get('current_index', 0)}/{data.get('total_stocks', 0)}"
                    })
            except:
                pass

        if checkpoint_data:
            cp_df = pd.DataFrame(checkpoint_data)
            st.dataframe(cp_df, use_container_width=True, hide_index=True)

    else:
        st.info("📁 재무제표 수집 체크포인트 파일이 없습니다")
else:
    st.warning(f"⚠️ 체크포인트 디렉토리가 없습니다: {checkpoint_dir}")

# Summary
st.markdown("---")
st.subheader("📊 Day 11-12 완료 요약")

summary_col1, summary_col2 = st.columns(2)

with summary_col1:
    st.markdown("""
    <div style="background-color: #d4edda; padding: 1rem; border-radius: 0.5rem; border-left: 4px solid #28a745;">
        <h4 style="color: #155724;">✅ 완료된 항목</h4>
        <ul>
            <li><b>Day 11</b>: 첫 500개 종목 재무제표 수집 (10,000건)</li>
            <li><b>Day 12</b>: 추가 1,000개 종목 수집 (누적 30,000건)</li>
            <li>DART API 배치 수집 스크립트 구현</li>
            <li>JSONB 데이터 검증 로직</li>
            <li>계정과목 표준화 작업 시작</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

with summary_col2:
    st.markdown("""
    <div style="background-color: #d1ecf1; padding: 1rem; border-radius: 0.5rem; border-left: 4px solid #17a2b8;">
        <h4 style="color: #0c5460;">📈 다음 단계 (Day 13-15)</h4>
        <ul>
            <li><b>Day 13</b>: 나머지 1,000개 종목 수집 완료</li>
            <li><b>Day 14</b>: 재무비율 계산 로직 구현 (15개 지표)</li>
            <li><b>Day 15</b>: 밸류에이션 지표 및 Magic Formula</li>
            <li>전체 종목 재무비율 계산 실행</li>
            <li>이상치 탐지 및 데이터 품질 개선</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

# Data Quality Notes
st.markdown("---")
st.info("""
💡 **데이터 품질 주의사항**

- **계정과목 표준화**: 기업마다 동일한 항목을 다른 이름으로 사용할 수 있습니다 (예: "자산총계" vs "총자산")
- **JSONB 구조**: 유연한 데이터 구조로 다양한 재무제표 형식을 수용합니다
- **필수 계정과목**: 재무비율 계산을 위해 핵심 계정과목의 존재율이 95% 이상이어야 합니다
- **분기 vs 연간**: 분기보고서는 누적값일 수 있으므로 재무비율 계산 시 주의가 필요합니다
""")
