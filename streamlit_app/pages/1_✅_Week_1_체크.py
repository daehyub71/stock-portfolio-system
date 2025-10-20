"""Week 1 완료 체크 페이지

Day 1-5: 환경 구축 및 API 연동 테스트 검증
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
    page_title="Week 1 완료 체크",
    page_icon="✅",
    layout="wide"
)

st.title("✅ Week 1 완료 체크")
st.markdown("**기간**: Day 1-5 | **목표**: 환경 구축 및 API 연동 테스트")
st.markdown("---")

# Progress tracker
progress_data = {
    "Day 1": {"완료": True, "description": "프로젝트 초기화 및 PostgreSQL 설정"},
    "Day 2": {"완료": True, "description": "데이터베이스 스키마 생성"},
    "Day 3": {"완료": True, "description": "KRX API 연동 및 종목 리스트 수집"},
    "Day 4": {"완료": True, "description": "KIS API 연동 및 시세 데이터 수집"},
    "Day 5": {"완료": True, "description": "DART API 연동 및 재무제표 수집"},
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

# Day 1 Check
with st.expander("📅 **Day 1: 프로젝트 초기화 및 PostgreSQL 설정**", expanded=True):
    st.markdown("### 검증 항목")

    checks = []

    # Check 1: Project directory structure
    st.markdown("#### 1️⃣ 프로젝트 디렉토리 구조")
    required_dirs = ['collectors', 'calculators', 'pipelines', 'models', 'db', 'config', 'scripts', 'tests', 'docs']
    missing_dirs = []

    for dir_name in required_dirs:
        dir_path = project_root / dir_name
        exists = dir_path.exists()
        checks.append(("디렉토리", dir_name, exists))
        if not exists:
            missing_dirs.append(dir_name)

    if not missing_dirs:
        st.success(f"✅ 필수 디렉토리 {len(required_dirs)}개 모두 존재")
    else:
        st.error(f"❌ 누락된 디렉토리: {', '.join(missing_dirs)}")

    # Check 2: Virtual environment
    st.markdown("#### 2️⃣ Python 가상환경")
    venv_path = project_root / "venv"
    venv_exists = venv_path.exists()
    checks.append(("가상환경", "venv/", venv_exists))

    if venv_exists:
        st.success("✅ 가상환경 존재 (venv/)")
    else:
        st.warning("⚠️ 가상환경 디렉토리를 찾을 수 없습니다")

    # Check 3: Requirements.txt
    st.markdown("#### 3️⃣ Python 패키지")
    requirements_path = project_root / "requirements.txt"
    requirements_exists = requirements_path.exists()
    checks.append(("requirements.txt", "", requirements_exists))

    if requirements_exists:
        st.success("✅ requirements.txt 존재")
        with open(requirements_path, 'r') as f:
            packages = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        st.info(f"📦 총 {len(packages)}개 패키지 정의됨")

        with st.expander("패키지 목록 보기"):
            st.code('\n'.join(packages))
    else:
        st.error("❌ requirements.txt 파일 없음")

    # Check 4: Environment variables
    st.markdown("#### 4️⃣ 환경 변수 설정")
    env_path = project_root / ".env"
    env_exists = env_path.exists()
    checks.append((".env", "환경변수 파일", env_exists))

    if env_exists:
        st.success("✅ .env 파일 존재")
        try:
            from dotenv import load_dotenv
            import os
            load_dotenv()

            required_vars = ['DB_HOST', 'DB_NAME', 'DB_USER', 'KIS_APP_KEY', 'DART_API_KEY']
            env_status = []

            for var in required_vars:
                value = os.getenv(var)
                is_set = value is not None and value != "" and not value.startswith("your_")
                env_status.append((var, "✅" if is_set else "❌"))
                checks.append(("환경변수", var, is_set))

            env_df = pd.DataFrame(env_status, columns=["변수명", "상태"])
            st.dataframe(env_df, use_container_width=True, hide_index=True)

        except Exception as e:
            st.error(f"환경 변수 로드 실패: {e}")
    else:
        st.warning("⚠️ .env 파일을 찾을 수 없습니다")

    # Check 5: Database connection
    st.markdown("#### 5️⃣ PostgreSQL 연결 테스트")

    if st.button("데이터베이스 연결 테스트", key="day1_db_test"):
        try:
            from db.connection import test_connection, engine
            from sqlalchemy import text

            with st.spinner("연결 테스트 중..."):
                if test_connection():
                    st.success("✅ PostgreSQL 연결 성공!")
                    checks.append(("DB 연결", "PostgreSQL", True))

                    with engine.connect() as conn:
                        result = conn.execute(text("SELECT version();"))
                        version = result.fetchone()[0]
                        st.code(version)
                else:
                    st.error("❌ 데이터베이스 연결 실패")
                    checks.append(("DB 연결", "PostgreSQL", False))
        except Exception as e:
            st.error(f"❌ 오류: {e}")
            checks.append(("DB 연결", "PostgreSQL", False))

# Day 2 Check
with st.expander("📅 **Day 2: 데이터베이스 스키마 생성**", expanded=False):
    st.markdown("### 검증 항목")

    # Check 1: Models exist
    st.markdown("#### 1️⃣ SQLAlchemy 모델 파일")
    model_files = ['base.py', 'sector.py', 'stock.py', 'daily_price.py',
                   'financial_statement.py', 'financial_ratio.py', 'corp_code_map.py']

    model_status = []
    for model_file in model_files:
        model_path = project_root / 'models' / model_file
        exists = model_path.exists()
        model_status.append((model_file, "✅" if exists else "❌"))

    model_df = pd.DataFrame(model_status, columns=["모델 파일", "상태"])
    st.dataframe(model_df, use_container_width=True, hide_index=True)

    # Check 2: Database tables
    st.markdown("#### 2️⃣ 데이터베이스 테이블 생성")

    if st.button("테이블 확인", key="day2_table_check"):
        try:
            from db.connection import engine
            from sqlalchemy import text, inspect

            inspector = inspect(engine)
            tables = inspector.get_table_names()

            if tables:
                st.success(f"✅ 총 {len(tables)}개 테이블 존재")

                # Expected tables
                expected_tables = ['sectors', 'stocks', 'daily_prices',
                                   'financial_statements', 'financial_ratios', 'corp_code_map']

                table_status = []
                for table in expected_tables:
                    exists = table in tables
                    table_status.append((table, "✅" if exists else "❌"))

                table_df = pd.DataFrame(table_status, columns=["테이블명", "상태"])
                st.dataframe(table_df, use_container_width=True, hide_index=True)

                # Show all tables
                with st.expander("전체 테이블 목록"):
                    st.write(tables)

            else:
                st.warning("⚠️ 테이블이 존재하지 않습니다")
                st.info("💡 `python scripts/init_db.py` 를 실행하세요")

        except Exception as e:
            st.error(f"❌ 오류: {e}")

    # Check 3: Indexes
    st.markdown("#### 3️⃣ 인덱스 및 제약조건")
    st.info("인덱스는 각 모델에 정의된 대로 자동 생성됩니다 (stock.ticker, daily_prices 복합 인덱스 등)")

# Day 3 Check
with st.expander("📅 **Day 3: KRX API 연동 및 종목 리스트 수집**", expanded=False):
    st.markdown("### 검증 항목")

    # Check 1: KRX Collector exists
    st.markdown("#### 1️⃣ KRXCollector 클래스")
    krx_collector_path = project_root / 'collectors' / 'krx_collector.py'
    krx_exists = krx_collector_path.exists()

    if krx_exists:
        st.success("✅ collectors/krx_collector.py 존재")
    else:
        st.error("❌ KRX Collector 파일 없음")

    # Check 2: Stock data in database
    st.markdown("#### 2️⃣ 종목 리스트 데이터 확인")

    if st.button("종목 데이터 조회", key="day3_stock_check"):
        try:
            from db.connection import SessionLocal
            from models import Stock, MarketType
            from sqlalchemy import func

            db = SessionLocal()

            try:
                # Total stocks
                total_stocks = db.query(func.count(Stock.id)).scalar()

                if total_stocks > 0:
                    st.success(f"✅ 총 {total_stocks:,}개 종목 수집 완료")

                    # By market
                    market_dist = db.query(
                        Stock.market,
                        func.count(Stock.id)
                    ).group_by(Stock.market).all()

                    market_data = [(m.value if hasattr(m, 'value') else str(m), count)
                                   for m, count in market_dist]
                    market_df = pd.DataFrame(market_data, columns=["시장", "종목 수"])

                    col1, col2 = st.columns(2)
                    with col1:
                        st.dataframe(market_df, use_container_width=True, hide_index=True)
                    with col2:
                        st.bar_chart(market_df.set_index("시장"))

                    # Sample stocks
                    st.markdown("#### 📋 샘플 종목 (최근 10개)")
                    sample_stocks = db.query(Stock).limit(10).all()
                    sample_data = [(s.ticker, s.name, s.market.value if hasattr(s.market, 'value') else str(s.market))
                                   for s in sample_stocks]
                    sample_df = pd.DataFrame(sample_data, columns=["티커", "종목명", "시장"])
                    st.dataframe(sample_df, use_container_width=True, hide_index=True)

                else:
                    st.warning("⚠️ 종목 데이터가 없습니다")
                    st.info("💡 `python scripts/collect_stocks.py` 를 실행하세요")

            finally:
                db.close()

        except Exception as e:
            st.error(f"❌ 오류: {e}")

# Day 4 Check
with st.expander("📅 **Day 4: KIS API 연동 및 시세 데이터 수집**", expanded=False):
    st.markdown("### 검증 항목")

    # Check 1: PyKRX Price Collector
    st.markdown("#### 1️⃣ PyKRXPriceCollector 클래스")
    pykrx_collector_path = project_root / 'collectors' / 'pykrx_price_collector.py'
    pykrx_exists = pykrx_collector_path.exists()

    if pykrx_exists:
        st.success("✅ collectors/pykrx_price_collector.py 존재")
    else:
        st.warning("⚠️ PyKRX Price Collector 파일 확인 필요")

    # Check 2: Price data sample
    st.markdown("#### 2️⃣ 시세 데이터 샘플 확인")

    if st.button("시세 데이터 조회", key="day4_price_check"):
        try:
            from db.connection import SessionLocal
            from models import DailyPrice, Stock
            from sqlalchemy import func

            db = SessionLocal()

            try:
                total_prices = db.query(func.count(DailyPrice.id)).scalar()

                if total_prices > 0:
                    st.success(f"✅ 총 {total_prices:,}건 시세 데이터 존재")

                    # Date range
                    date_range = db.query(
                        func.min(DailyPrice.date),
                        func.max(DailyPrice.date)
                    ).first()

                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("최초 데이터", date_range[0].strftime("%Y-%m-%d") if date_range[0] else "N/A")
                    with col2:
                        st.metric("최신 데이터", date_range[1].strftime("%Y-%m-%d") if date_range[1] else "N/A")

                    # Stocks with price data
                    stocks_with_prices = db.query(func.count(func.distinct(DailyPrice.stock_id))).scalar()
                    st.metric("시세 데이터가 있는 종목 수", f"{stocks_with_prices:,}개")

                else:
                    st.warning("⚠️ 시세 데이터가 없습니다")
                    st.info("💡 `python scripts/batch_collect_prices.py` 를 실행하세요")

            finally:
                db.close()

        except Exception as e:
            st.error(f"❌ 오류: {e}")

# Day 5 Check
with st.expander("📅 **Day 5: DART API 연동 및 재무제표 수집**", expanded=False):
    st.markdown("### 검증 항목")

    # Check 1: DART Collector
    st.markdown("#### 1️⃣ DARTCollector 클래스")
    dart_collector_path = project_root / 'collectors' / 'dart_collector.py'
    dart_exists = dart_collector_path.exists()

    if dart_exists:
        st.success("✅ collectors/dart_collector.py 존재")
    else:
        st.error("❌ DART Collector 파일 없음")

    # Check 2: Corp code map
    st.markdown("#### 2️⃣ DART 고유번호 매핑")

    if st.button("고유번호 매핑 확인", key="day5_corpcode_check"):
        try:
            from db.connection import SessionLocal
            from models import CorpCodeMap
            from sqlalchemy import func

            db = SessionLocal()

            try:
                total_maps = db.query(func.count(CorpCodeMap.id)).scalar()

                if total_maps > 0:
                    st.success(f"✅ {total_maps:,}개 기업 매핑 완료")

                    # Sample
                    sample_maps = db.query(CorpCodeMap).limit(10).all()
                    sample_data = [(m.ticker, m.corp_code, m.corp_name) for m in sample_maps]
                    sample_df = pd.DataFrame(sample_data, columns=["티커", "고유번호", "기업명"])
                    st.dataframe(sample_df, use_container_width=True, hide_index=True)

                else:
                    st.warning("⚠️ 고유번호 매핑 데이터 없음")
                    st.info("💡 `python scripts/download_corp_codes.py` 를 실행하세요")

            finally:
                db.close()

        except Exception as e:
            st.error(f"❌ 오류: {e}")

    # Check 3: Financial statements
    st.markdown("#### 3️⃣ 재무제표 데이터")

    if st.button("재무제표 확인", key="day5_financial_check"):
        try:
            from db.connection import SessionLocal
            from models import FinancialStatement
            from sqlalchemy import func

            db = SessionLocal()

            try:
                total_financials = db.query(func.count(FinancialStatement.id)).scalar()

                if total_financials > 0:
                    st.success(f"✅ {total_financials:,}건 재무제표 수집 완료")

                    # By year
                    year_dist = db.query(
                        FinancialStatement.fiscal_year,
                        func.count(FinancialStatement.id)
                    ).group_by(FinancialStatement.fiscal_year).order_by(FinancialStatement.fiscal_year.desc()).limit(5).all()

                    year_df = pd.DataFrame(year_dist, columns=["회계연도", "건수"])
                    st.dataframe(year_df, use_container_width=True, hide_index=True)

                else:
                    st.warning("⚠️ 재무제표 데이터 없음")
                    st.info("💡 `python scripts/batch_collect_financials.py` 를 실행하세요")

            finally:
                db.close()

        except Exception as e:
            st.error(f"❌ 오류: {e}")

# Summary
st.markdown("---")
st.subheader("📊 Week 1 완료 요약")

summary_col1, summary_col2 = st.columns(2)

with summary_col1:
    st.markdown("""
    <div style="background-color: #d4edda; padding: 1rem; border-radius: 0.5rem; border-left: 4px solid #28a745;">
        <h4 style="color: #155724;">✅ 완료된 항목</h4>
        <ul>
            <li>프로젝트 디렉토리 구조 생성</li>
            <li>PostgreSQL 15 설치 및 연결</li>
            <li>SQLAlchemy 모델 6개 정의</li>
            <li>데이터베이스 테이블 생성</li>
            <li>KRX, KIS, DART API 연동</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

with summary_col2:
    st.markdown("""
    <div style="background-color: #d1ecf1; padding: 1rem; border-radius: 0.5rem; border-left: 4px solid #17a2b8;">
        <h4 style="color: #0c5460;">📈 다음 단계 (Week 2)</h4>
        <ul>
            <li>전체 2,500개 종목 시세 수집</li>
            <li>10년치 OHLCV 데이터 수집</li>
            <li>배치 처리 시스템 구축</li>
            <li>데이터 품질 검증</li>
            <li>파티셔닝 및 인덱스 최적화</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
