"""Week 2 완료 체크 페이지

Day 6-10: 전체 종목 시세 데이터 수집 검증
"""

import streamlit as st
from pathlib import Path
import sys
from datetime import datetime, timedelta
import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Page configuration
st.set_page_config(
    page_title="Week 2 완료 체크",
    page_icon="✅",
    layout="wide"
)

st.title("✅ Week 2 완료 체크")
st.markdown("**기간**: Day 6-10 | **목표**: 전체 종목 시세 데이터 수집 (10년치)")
st.markdown("---")

# Progress tracker
progress_data = {
    "Day 6": {"완료": True, "description": "첫 번째 그룹 500개 종목 수집"},
    "Day 7": {"완료": True, "description": "두 번째 그룹 500개 종목 수집"},
    "Day 8": {"완료": True, "description": "세 번째 그룹 500개 종목 수집"},
    "Day 9": {"완료": True, "description": "네 번째 그룹 500개 종목 수집"},
    "Day 10": {"완료": True, "description": "다섯 번째 그룹 500개 종목 수집 및 검증"},
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

# Overall Data Statistics
st.subheader("📊 전체 데이터 통계")

if st.button("전체 통계 조회", type="primary", key="overall_stats"):
    try:
        from db.connection import SessionLocal
        from models import Stock, DailyPrice
        from sqlalchemy import func, text

        db = SessionLocal()

        try:
            # Total stocks
            total_stocks = db.query(func.count(Stock.id)).scalar()

            # Total price records
            total_prices = db.query(func.count(DailyPrice.id)).scalar()

            # Stocks with price data
            stocks_with_prices = db.query(func.count(func.distinct(DailyPrice.stock_id))).scalar()

            # Date range
            date_range = db.query(
                func.min(DailyPrice.date),
                func.max(DailyPrice.date)
            ).first()

            # Coverage
            coverage = (stocks_with_prices / total_stocks * 100) if total_stocks > 0 else 0

            # Display metrics
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric(
                    "총 종목 수",
                    f"{total_stocks:,}개",
                    help="데이터베이스에 등록된 전체 종목 수"
                )

            with col2:
                st.metric(
                    "시세 데이터가 있는 종목",
                    f"{stocks_with_prices:,}개",
                    delta=f"{coverage:.1f}% 커버리지",
                    help="최소 1건 이상의 시세 데이터가 있는 종목 수"
                )

            with col3:
                st.metric(
                    "총 시세 레코드",
                    f"{total_prices:,}건",
                    help="수집된 전체 OHLCV 데이터 건수"
                )

            with col4:
                if date_range[0] and date_range[1]:
                    days_span = (date_range[1] - date_range[0]).days
                    st.metric(
                        "데이터 기간",
                        f"{days_span:,}일",
                        delta=f"{date_range[0].strftime('%Y-%m-%d')} ~",
                        help=f"최신: {date_range[1].strftime('%Y-%m-%d')}"
                    )

            # Expected vs Actual
            st.markdown("---")
            st.subheader("🎯 목표 대비 달성률")

            expected_stocks = 2500
            expected_days = 2500
            expected_records = expected_stocks * expected_days

            actual_avg_records = total_prices / stocks_with_prices if stocks_with_prices > 0 else 0

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric(
                    "목표 종목 수",
                    f"{expected_stocks:,}개",
                    delta=f"{stocks_with_prices - expected_stocks:+,}개" if stocks_with_prices >= expected_stocks else f"{stocks_with_prices - expected_stocks:,}개"
                )

            with col2:
                st.metric(
                    "평균 데이터 일수/종목",
                    f"{actual_avg_records:,.0f}일",
                    delta=f"목표 {expected_days:,}일"
                )

            with col3:
                achievement = (total_prices / expected_records * 100) if expected_records > 0 else 0
                st.metric(
                    "전체 달성률",
                    f"{achievement:.1f}%",
                    delta="목표 대비"
                )

        finally:
            db.close()

    except Exception as e:
        st.error(f"❌ 오류: {e}")

# Batch Group Analysis
st.markdown("---")
st.subheader("📦 그룹별 수집 현황")

if st.button("그룹별 분석", key="batch_groups"):
    try:
        from db.connection import SessionLocal
        from models import Stock, DailyPrice
        from sqlalchemy import func

        db = SessionLocal()

        try:
            # Get all stocks with price count
            stock_price_counts = db.query(
                Stock.id,
                Stock.ticker,
                Stock.name,
                Stock.market,
                func.count(DailyPrice.id).label('price_count')
            ).outerjoin(DailyPrice).group_by(Stock.id).order_by(Stock.id).all()

            if stock_price_counts:
                # Convert to DataFrame
                df = pd.DataFrame([
                    {
                        'stock_id': s.id,
                        'ticker': s.ticker,
                        'name': s.name,
                        'market': s.market.value if hasattr(s.market, 'value') else str(s.market),
                        'price_count': s.price_count
                    }
                    for s in stock_price_counts
                ])

                # Assign to groups (500 stocks per group)
                df['group'] = (df.index // 500) + 1

                # Group statistics
                group_stats = df.groupby('group').agg({
                    'stock_id': 'count',
                    'price_count': ['sum', 'mean', 'min', 'max']
                }).reset_index()

                group_stats.columns = ['그룹', '종목수', '총 레코드', '평균 레코드/종목', '최소 레코드', '최대 레코드']
                group_stats['총 레코드'] = group_stats['총 레코드'].astype(int)
                group_stats['평균 레코드/종목'] = group_stats['평균 레코드/종목'].round(0).astype(int)
                group_stats['최소 레코드'] = group_stats['최소 레코드'].astype(int)
                group_stats['최대 레코드'] = group_stats['최대 레코드'].astype(int)

                st.dataframe(group_stats, use_container_width=True, hide_index=True)

                # Visualization
                st.bar_chart(group_stats.set_index('그룹')['총 레코드'])

            else:
                st.warning("⚠️ 데이터가 없습니다")

        finally:
            db.close()

    except Exception as e:
        st.error(f"❌ 오류: {e}")

# Date Coverage Analysis
st.markdown("---")
st.subheader("📅 날짜별 커버리지 분석")

if st.button("날짜별 분석", key="date_coverage"):
    try:
        from db.connection import SessionLocal
        from models import DailyPrice
        from sqlalchemy import func

        db = SessionLocal()

        try:
            # Group by date
            date_counts = db.query(
                DailyPrice.date,
                func.count(DailyPrice.id).label('count')
            ).group_by(DailyPrice.date).order_by(DailyPrice.date.desc()).limit(100).all()

            if date_counts:
                df = pd.DataFrame([(d.date, d.count) for d in date_counts], columns=['날짜', '종목 수'])
                df = df.sort_values('날짜')

                st.line_chart(df.set_index('날짜'))

                st.markdown("#### 📋 최근 10일 데이터")
                recent_df = df.tail(10)
                st.dataframe(recent_df, use_container_width=True, hide_index=True)

            else:
                st.warning("⚠️ 날짜별 데이터가 없습니다")

        finally:
            db.close()

    except Exception as e:
        st.error(f"❌ 오류: {e}")

# Market Distribution
st.markdown("---")
st.subheader("📈 시장별 데이터 분포")

if st.button("시장별 분석", key="market_dist"):
    try:
        from db.connection import SessionLocal
        from models import Stock, DailyPrice
        from sqlalchemy import func

        db = SessionLocal()

        try:
            market_stats = db.query(
                Stock.market,
                func.count(func.distinct(Stock.id)).label('stock_count'),
                func.count(DailyPrice.id).label('price_count')
            ).outerjoin(DailyPrice).group_by(Stock.market).all()

            if market_stats:
                df = pd.DataFrame([
                    {
                        '시장': m.market.value if hasattr(m.market, 'value') else str(m.market),
                        '종목 수': m.stock_count,
                        '시세 레코드': m.price_count,
                        '평균 레코드/종목': int(m.price_count / m.stock_count) if m.stock_count > 0 else 0
                    }
                    for m in market_stats
                ])

                st.dataframe(df, use_container_width=True, hide_index=True)

                col1, col2 = st.columns(2)
                with col1:
                    st.bar_chart(df.set_index('시장')['종목 수'])
                with col2:
                    st.bar_chart(df.set_index('시장')['시세 레코드'])

            else:
                st.warning("⚠️ 시장별 데이터가 없습니다")

        finally:
            db.close()

    except Exception as e:
        st.error(f"❌ 오류: {e}")

# Sample Data Inspection
st.markdown("---")
st.subheader("🔍 샘플 데이터 확인")

ticker_input = st.text_input("종목 코드 입력 (예: 005930)", value="005930", key="sample_ticker")

if st.button("조회", key="sample_check"):
    try:
        from db.connection import SessionLocal
        from models import Stock, DailyPrice
        from sqlalchemy import desc

        db = SessionLocal()

        try:
            stock = db.query(Stock).filter(Stock.ticker == ticker_input).first()

            if stock:
                st.success(f"✅ {stock.name} ({stock.ticker}) - {stock.market.value if hasattr(stock.market, 'value') else stock.market}")

                # Price data
                prices = db.query(DailyPrice).filter(
                    DailyPrice.stock_id == stock.id
                ).order_by(desc(DailyPrice.date)).limit(20).all()

                if prices:
                    st.info(f"📊 총 {len(prices)}건의 최근 데이터 (최대 20건 표시)")

                    price_df = pd.DataFrame([
                        {
                            '날짜': p.date.strftime('%Y-%m-%d'),
                            '시가': f"{float(p.open_price):,.0f}",
                            '고가': f"{float(p.high_price):,.0f}",
                            '저가': f"{float(p.low_price):,.0f}",
                            '종가': f"{float(p.close_price):,.0f}",
                            '거래량': f"{p.volume:,}"
                        }
                        for p in prices
                    ])

                    st.dataframe(price_df, use_container_width=True, hide_index=True)

                else:
                    st.warning(f"⚠️ {stock.name} 종목의 시세 데이터가 없습니다")

            else:
                st.error(f"❌ 종목 코드 '{ticker_input}'를 찾을 수 없습니다")

        finally:
            db.close()

    except Exception as e:
        st.error(f"❌ 오류: {e}")

# Checkpoints Status
st.markdown("---")
st.subheader("💾 체크포인트 파일 확인")

checkpoint_dir = project_root / "data" / "checkpoints"

if checkpoint_dir.exists():
    checkpoint_files = list(checkpoint_dir.glob("price_checkpoint_*.json"))

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
                        '완료': data.get('completed', False),
                        '성공': data.get('successful_stocks', 0),
                        '실패': data.get('failed_stocks', 0),
                        '진행': f"{data.get('current_index', 0)}/{data.get('total_stocks', 0)}"
                    })
            except:
                pass

        if checkpoint_data:
            cp_df = pd.DataFrame(checkpoint_data)
            st.dataframe(cp_df, use_container_width=True, hide_index=True)

    else:
        st.info("📁 체크포인트 파일이 없습니다")
else:
    st.warning(f"⚠️ 체크포인트 디렉토리가 없습니다: {checkpoint_dir}")

# Summary
st.markdown("---")
st.subheader("📊 Week 2 완료 요약")

summary_col1, summary_col2 = st.columns(2)

with summary_col1:
    st.markdown("""
    <div style="background-color: #d4edda; padding: 1rem; border-radius: 0.5rem; border-left: 4px solid #28a745;">
        <h4 style="color: #155724;">✅ 완료된 항목</h4>
        <ul>
            <li>배치 수집 스크립트 구현 (체크포인트 시스템)</li>
            <li>전체 2,500개 종목 그룹화 (500개씩 5그룹)</li>
            <li>10년치 OHLCV 데이터 수집</li>
            <li>수집 모니터링 대시보드</li>
            <li>데이터 품질 검증 스크립트</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

with summary_col2:
    st.markdown("""
    <div style="background-color: #d1ecf1; padding: 1rem; border-radius: 0.5rem; border-left: 4px solid #17a2b8;">
        <h4 style="color: #0c5460;">📈 다음 단계 (Week 3)</h4>
        <ul>
            <li>전체 종목 재무제표 수집</li>
            <li>DART API 배치 처리</li>
            <li>JSONB 데이터 검증</li>
            <li>재무비율 계산 로직 구현</li>
            <li>Magic Formula 지표 계산</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
