"""데이터베이스 개요 페이지

PostgreSQL 데이터베이스 테이블 및 전체 현황
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
    page_title="데이터베이스 개요",
    page_icon="💾",
    layout="wide"
)

st.title("💾 데이터베이스 개요")
st.markdown("PostgreSQL 데이터베이스 스키마 및 데이터 현황")
st.markdown("---")

# Database Connection Info
st.subheader("🔌 데이터베이스 연결 정보")

try:
    import os
    from dotenv import load_dotenv
    load_dotenv()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Host", os.getenv('DB_HOST', 'localhost'))
    with col2:
        st.metric("Port", os.getenv('DB_PORT', '5432'))
    with col3:
        st.metric("Database", os.getenv('DB_NAME', 'stock_portfolio'))
    with col4:
        st.metric("User", os.getenv('DB_USER', 'N/A'))

except Exception as e:
    st.error(f"환경 변수 로드 실패: {e}")

st.markdown("---")

# PostgreSQL Version
st.subheader("📊 PostgreSQL 버전 정보")

if st.button("버전 확인", key="pg_version"):
    try:
        from db.connection import engine
        from sqlalchemy import text

        with engine.connect() as conn:
            result = conn.execute(text("SELECT version();"))
            version = result.fetchone()[0]
            st.code(version, language="text")

            # Additional info
            result = conn.execute(text("SHOW server_encoding;"))
            encoding = result.fetchone()[0]

            result = conn.execute(text("SHOW lc_collate;"))
            collate = result.fetchone()[0]

            col1, col2 = st.columns(2)
            with col1:
                st.metric("Encoding", encoding)
            with col2:
                st.metric("LC_COLLATE", collate)

    except Exception as e:
        st.error(f"❌ 오류: {e}")

st.markdown("---")

# Tables Overview
st.subheader("📋 테이블 목록 및 레코드 수")

if st.button("테이블 조회", type="primary", key="tables_overview"):
    try:
        from db.connection import SessionLocal, engine
        from models import Stock, DailyPrice, FinancialStatement, FinancialRatio, Sector, CorpCodeMap
        from sqlalchemy import text, inspect, func

        db = SessionLocal()

        try:
            # Get all tables
            inspector = inspect(engine)
            tables = inspector.get_table_names()

            st.success(f"✅ 총 {len(tables)}개 테이블 발견")

            # Get row counts for each table
            table_info = []

            # Sectors
            sector_count = db.query(func.count(Sector.id)).scalar() if 'sectors' in tables else 0
            table_info.append(('sectors', '업종 분류', sector_count, '종목의 업종 정보'))

            # Stocks
            stock_count = db.query(func.count(Stock.id)).scalar() if 'stocks' in tables else 0
            table_info.append(('stocks', '종목 정보', stock_count, 'KOSPI/KOSDAQ 상장 종목'))

            # DailyPrice
            price_count = db.query(func.count(DailyPrice.id)).scalar() if 'daily_prices' in tables else 0
            table_info.append(('daily_prices', '일별 시세', price_count, 'OHLCV 데이터'))

            # FinancialStatement
            fs_count = db.query(func.count(FinancialStatement.id)).scalar() if 'financial_statements' in tables else 0
            table_info.append(('financial_statements', '재무제표', fs_count, 'DART API 수집 (JSONB)'))

            # FinancialRatio
            fr_count = db.query(func.count(FinancialRatio.id)).scalar() if 'financial_ratios' in tables else 0
            table_info.append(('financial_ratios', '재무비율', fr_count, '33개 재무비율 지표'))

            # CorpCodeMap
            cc_count = db.query(func.count(CorpCodeMap.id)).scalar() if 'corp_code_map' in tables else 0
            table_info.append(('corp_code_map', '고유번호 매핑', cc_count, 'ticker ↔ DART corp_code'))

            # Create DataFrame
            table_df = pd.DataFrame(table_info, columns=['테이블명', '설명', '레코드 수', '비고'])
            table_df['레코드 수'] = table_df['레코드 수'].apply(lambda x: f"{x:,}")

            st.dataframe(table_df, use_container_width=True, hide_index=True)

            # Total records
            total_records = sum([sector_count, stock_count, price_count, fs_count, fr_count, cc_count])
            st.metric("총 레코드 수", f"{total_records:,}건")

        finally:
            db.close()

    except Exception as e:
        st.error(f"❌ 오류: {e}")

st.markdown("---")

# Table Details
st.subheader("🔍 테이블 상세 정보")

table_choice = st.selectbox(
    "테이블 선택",
    ["stocks", "daily_prices", "financial_statements", "financial_ratios", "sectors", "corp_code_map"]
)

if st.button("테이블 상세 조회", key="table_detail"):
    try:
        from db.connection import engine
        from sqlalchemy import inspect

        inspector = inspect(engine)

        # Get columns
        columns = inspector.get_columns(table_choice)

        if columns:
            st.markdown(f"#### 📊 `{table_choice}` 테이블 스키마")

            column_info = []
            for col in columns:
                column_info.append({
                    '컬럼명': col['name'],
                    '타입': str(col['type']),
                    'NULL 허용': '❌' if col['nullable'] else '✅',
                    '기본값': str(col.get('default', ''))[:50] if col.get('default') else '-',
                    '설명': col.get('comment', '-') or '-'
                })

            col_df = pd.DataFrame(column_info)
            st.dataframe(col_df, use_container_width=True, hide_index=True)

            # Indexes
            st.markdown("#### 🔑 인덱스")
            indexes = inspector.get_indexes(table_choice)

            if indexes:
                index_info = []
                for idx in indexes:
                    index_info.append({
                        '인덱스명': idx['name'],
                        '컬럼': ', '.join(idx['column_names']),
                        'Unique': '✅' if idx.get('unique', False) else '❌'
                    })

                idx_df = pd.DataFrame(index_info)
                st.dataframe(idx_df, use_container_width=True, hide_index=True)
            else:
                st.info("인덱스 정보가 없습니다")

            # Foreign Keys
            st.markdown("#### 🔗 외래키")
            foreign_keys = inspector.get_foreign_keys(table_choice)

            if foreign_keys:
                fk_info = []
                for fk in foreign_keys:
                    fk_info.append({
                        'FK 이름': fk.get('name', 'N/A'),
                        '컬럼': ', '.join(fk['constrained_columns']),
                        '참조 테이블': fk['referred_table'],
                        '참조 컬럼': ', '.join(fk['referred_columns'])
                    })

                fk_df = pd.DataFrame(fk_info)
                st.dataframe(fk_df, use_container_width=True, hide_index=True)
            else:
                st.info("외래키가 없습니다")

        else:
            st.warning(f"테이블 '{table_choice}'를 찾을 수 없습니다")

    except Exception as e:
        st.error(f"❌ 오류: {e}")

st.markdown("---")

# Database Size
st.subheader("💽 데이터베이스 저장 공간")

if st.button("저장 공간 분석", key="db_size"):
    try:
        from db.connection import engine
        from sqlalchemy import text

        with engine.connect() as conn:
            # Database size
            result = conn.execute(text("""
                SELECT pg_size_pretty(pg_database_size(current_database())) as size
            """))
            db_size = result.fetchone()[0]

            st.metric("전체 데이터베이스 크기", db_size)

            # Table sizes
            result = conn.execute(text("""
                SELECT
                    schemaname,
                    tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
                    pg_total_relation_size(schemaname||'.'||tablename) AS size_bytes
                FROM pg_tables
                WHERE schemaname = 'public'
                ORDER BY size_bytes DESC
            """))

            table_sizes = result.fetchall()

            if table_sizes:
                size_info = []
                for ts in table_sizes:
                    size_info.append({
                        '테이블명': ts[1],
                        '크기': ts[2],
                        '크기(bytes)': ts[3]
                    })

                size_df = pd.DataFrame(size_info)
                st.dataframe(size_df[['테이블명', '크기']], use_container_width=True, hide_index=True)

                # Visualization
                import plotly.express as px
                fig = px.pie(size_df, values='크기(bytes)', names='테이블명', title='테이블별 저장 공간 비율')
                st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"❌ 오류: {e}")

st.markdown("---")

# Database Schema Diagram
st.subheader("🗺️ 데이터베이스 스키마 다이어그램")

st.markdown("""
```
📦 stock_portfolio Database

├── 📊 sectors (업종 분류)
│   ├── id (PK)
│   ├── name
│   ├── code
│   └── parent_id (Self-FK) ← 계층 구조
│
├── 📈 stocks (종목 정보)
│   ├── id (PK)
│   ├── ticker (Unique Index)
│   ├── name
│   ├── market (KOSPI/KOSDAQ/KONEX)
│   ├── sector_id (FK → sectors)
│   └── is_active
│
├── 💹 daily_prices (일별 시세)
│   ├── id (PK)
│   ├── stock_id (FK → stocks)
│   ├── date (Composite Index with stock_id)
│   ├── open_price, high_price, low_price, close_price
│   ├── volume
│   └── Unique Index: (stock_id, date)
│
├── 📑 financial_statements (재무제표)
│   ├── id (PK)
│   ├── stock_id (FK → stocks)
│   ├── fiscal_year, fiscal_quarter
│   ├── statement_type (annual/quarterly)
│   ├── balance_sheet (JSONB)
│   ├── income_statement (JSONB)
│   ├── cash_flow (JSONB)
│   └── Unique Index: (stock_id, report_date, statement_type)
│
├── 📊 financial_ratios (재무비율)
│   ├── id (PK)
│   ├── stock_id (FK → stocks)
│   ├── fiscal_year, fiscal_quarter
│   ├── roe, roa, roic (수익성)
│   ├── debt_ratio, current_ratio (안정성)
│   ├── per, pbr, psr (밸류에이션)
│   └── 33개 재무비율 컬럼
│
└── 🔗 corp_code_map (DART 고유번호 매핑)
    ├── id (PK)
    ├── ticker (Unique)
    ├── corp_code (DART 고유번호)
    └── corp_name
```
""")

# Sample Data Preview
st.markdown("---")
st.subheader("👀 샘플 데이터 미리보기")

preview_table = st.selectbox(
    "미리볼 테이블 선택",
    ["stocks", "daily_prices", "financial_statements", "corp_code_map"],
    key="preview_select"
)

if st.button("샘플 데이터 조회 (최근 10건)", key="preview_data"):
    try:
        from db.connection import SessionLocal
        from models import Stock, DailyPrice, FinancialStatement, CorpCodeMap
        from sqlalchemy import desc

        db = SessionLocal()

        try:
            if preview_table == "stocks":
                data = db.query(Stock).limit(10).all()
                if data:
                    df = pd.DataFrame([{
                        'ID': s.id,
                        '티커': s.ticker,
                        '종목명': s.name,
                        '시장': s.market.value if hasattr(s.market, 'value') else str(s.market),
                        '활성': '✅' if s.is_active else '❌'
                    } for s in data])
                    st.dataframe(df, use_container_width=True, hide_index=True)

            elif preview_table == "daily_prices":
                data = db.query(DailyPrice).order_by(desc(DailyPrice.date)).limit(10).all()
                if data:
                    df = pd.DataFrame([{
                        '종목ID': p.stock_id,
                        '날짜': p.date.strftime('%Y-%m-%d'),
                        '시가': f"{float(p.open_price):,.0f}",
                        '고가': f"{float(p.high_price):,.0f}",
                        '저가': f"{float(p.low_price):,.0f}",
                        '종가': f"{float(p.close_price):,.0f}",
                        '거래량': f"{p.volume:,}"
                    } for p in data])
                    st.dataframe(df, use_container_width=True, hide_index=True)

            elif preview_table == "financial_statements":
                data = db.query(FinancialStatement).order_by(desc(FinancialStatement.fiscal_year)).limit(10).all()
                if data:
                    df = pd.DataFrame([{
                        '종목ID': fs.stock_id,
                        '회계연도': fs.fiscal_year,
                        '분기': f"{fs.fiscal_quarter}Q" if fs.fiscal_quarter else '연간',
                        '유형': fs.statement_type.value if hasattr(fs.statement_type, 'value') else str(fs.statement_type),
                        '보고일': fs.report_date.strftime('%Y-%m-%d')
                    } for fs in data])
                    st.dataframe(df, use_container_width=True, hide_index=True)

            elif preview_table == "corp_code_map":
                data = db.query(CorpCodeMap).limit(10).all()
                if data:
                    df = pd.DataFrame([{
                        '티커': cc.ticker,
                        '고유번호': cc.corp_code,
                        '기업명': cc.corp_name
                    } for cc in data])
                    st.dataframe(df, use_container_width=True, hide_index=True)

            if not data:
                st.warning(f"'{preview_table}' 테이블에 데이터가 없습니다")

        finally:
            db.close()

    except Exception as e:
        st.error(f"❌ 오류: {e}")

# Footer
st.markdown("---")
st.info("""
💡 **데이터베이스 관리 팁**

- **테이블 확인**: `psql` 또는 TablePlus를 사용하여 직접 확인 가능
- **백업**: `pg_dump stock_portfolio > backup.sql`
- **복원**: `psql stock_portfolio < backup.sql`
- **진공 청소기**: 정기적으로 `VACUUM ANALYZE`를 실행하여 성능 유지
- **인덱스 최적화**: 대용량 데이터 적재 후 `REINDEX` 고려
""")
