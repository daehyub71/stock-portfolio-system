"""PostgreSQL 뷰 생성: 일별 + 분기별 재무비율 통합 조회용.

백테스팅 및 분석 시 일별 pykrx 데이터와 분기별 재무제표 계산 데이터를
한 번에 조회할 수 있는 뷰를 생성합니다.

사용법:
    python scripts/create_combined_ratios_view.py
"""

import sys
from pathlib import Path
from sqlalchemy import text
from loguru import logger

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from db.connection import SessionLocal, engine

# Configure logger
logger.add(
    "logs/create_combined_ratios_view_{time}.log",
    rotation="1 day",
    retention="30 days",
    level="INFO"
)

# 뷰 생성 SQL
CREATE_VIEW_SQL = """
CREATE OR REPLACE VIEW vw_daily_combined_ratios AS
SELECT
    -- 기본 정보
    dr.stock_id,
    dr.date,
    s.ticker,
    s.name AS stock_name,
    s.market,

    -- pykrx 일별 지표 (8개)
    dr.per,
    dr.pbr,
    dr.eps,
    dr.bps,
    dr.div AS dividend_yield_pykrx,
    dr.dps,
    dr.roe AS roe_pykrx,
    dr.payout_ratio,

    -- 재무제표 기반 분기별 지표 (10개)
    qr.roa,
    qr.gross_profit_margin,
    qr.operating_profit_margin,
    qr.net_profit_margin,
    qr.debt_ratio,
    qr.debt_to_equity,
    qr.current_ratio,
    qr.equity_ratio,
    qr.asset_turnover,
    qr.revenue_growth,

    -- 분기 정보
    qr.fiscal_year,
    qr.fiscal_quarter,
    qr.report_date AS quarter_report_date

FROM financial_ratios dr
INNER JOIN stocks s ON dr.stock_id = s.id
LEFT JOIN LATERAL (
    -- 해당 날짜 이전 가장 최근 분기 데이터 찾기
    SELECT
        stock_id,
        fiscal_year,
        fiscal_quarter,
        report_date,
        roa,
        gross_profit_margin,
        operating_profit_margin,
        net_profit_margin,
        debt_ratio,
        debt_to_equity,
        current_ratio,
        equity_ratio,
        asset_turnover,
        revenue_growth
    FROM financial_ratios
    WHERE stock_id = dr.stock_id
      AND fiscal_year IS NOT NULL  -- 분기 데이터만
      AND date <= dr.date            -- 해당 날짜 이전
    ORDER BY date DESC
    LIMIT 1
) qr ON TRUE
WHERE dr.fiscal_year IS NULL  -- pykrx 일별 데이터만 (분기 데이터 제외)
ORDER BY dr.stock_id, dr.date;
"""

# 뷰 설명 추가 SQL
COMMENT_VIEW_SQL = """
COMMENT ON VIEW vw_daily_combined_ratios IS
'일별 pykrx 재무비율 + 해당 시점 최신 분기 재무제표 계산 비율 통합 뷰.
백테스팅 및 시계열 분석 시 사용.
- pykrx 일별 지표: PER, PBR, ROE 등 (매일 변동)
- 재무제표 분기 지표: ROA, 부채비율 등 (분기 내 동일)';
"""

# 뷰 삭제 SQL
DROP_VIEW_SQL = """
DROP VIEW IF EXISTS vw_daily_combined_ratios;
"""


def create_view():
    """뷰 생성 실행."""
    db = SessionLocal()

    try:
        logger.info("Creating vw_daily_combined_ratios view...")

        # 기존 뷰 삭제
        logger.info("Dropping existing view if exists...")
        db.execute(text(DROP_VIEW_SQL))
        db.commit()

        # 뷰 생성
        logger.info("Creating new view...")
        db.execute(text(CREATE_VIEW_SQL))
        db.commit()

        # 주석 추가
        logger.info("Adding view comment...")
        db.execute(text(COMMENT_VIEW_SQL))
        db.commit()

        logger.info("✓ View created successfully: vw_daily_combined_ratios")

        # 뷰 테스트
        logger.info("Testing view...")
        result = db.execute(text("""
            SELECT
                ticker,
                stock_name,
                date,
                per,
                pbr,
                roe_pykrx,
                roa,
                debt_ratio,
                fiscal_year,
                fiscal_quarter
            FROM vw_daily_combined_ratios
            LIMIT 5
        """)).fetchall()

        if result:
            logger.info(f"✓ View test successful: {len(result)} rows returned")

            print("\n" + "=" * 80)
            print("뷰 생성 완료 - 샘플 데이터 (5건)")
            print("=" * 80)

            for row in result:
                print(f"\n종목: {row.ticker} {row.stock_name}")
                print(f"날짜: {row.date}")
                print(f"  [pykrx 일별] PER={row.per}, PBR={row.pbr}, ROE={row.roe_pykrx}%")
                print(f"  [분기 계산] ROA={row.roa}%, 부채비율={row.debt_ratio}% "
                      f"({row.fiscal_year or 'N/A'}Q{row.fiscal_quarter or 'N/A'})")

            print("=" * 80 + "\n")
        else:
            logger.warning("View created but no data returned (empty table)")

        # 사용 예시 출력
        print("\n📊 뷰 사용 예시:")
        print("-" * 80)

        print("\n1. 특정 날짜, 특정 종목의 모든 재무비율 조회:")
        print("""
    SELECT * FROM vw_daily_combined_ratios
    WHERE ticker = '005930'
      AND date = '2024-12-31';
        """)

        print("\n2. 시계열 데이터 조회 (6개월):")
        print("""
    SELECT date, per, pbr, roa, debt_ratio, fiscal_quarter
    FROM vw_daily_combined_ratios
    WHERE ticker = '005930'
      AND date BETWEEN '2024-07-01' AND '2024-12-31'
    ORDER BY date;
        """)

        print("\n3. 백테스팅용 필터링 (저PBR + 고ROE + 낮은부채비율):")
        print("""
    SELECT ticker, stock_name, date, pbr, roe_pykrx, debt_ratio
    FROM vw_daily_combined_ratios
    WHERE date = '2024-12-31'
      AND pbr < 1.0
      AND roe_pykrx > 10.0
      AND debt_ratio < 50.0
    ORDER BY roe_pykrx DESC
    LIMIT 20;
        """)

        print("\n4. SQLAlchemy로 뷰 조회:")
        print("""
    from sqlalchemy import text
    from db.connection import SessionLocal

    db = SessionLocal()
    result = db.execute(text('''
        SELECT * FROM vw_daily_combined_ratios
        WHERE ticker = :ticker AND date = :date
    '''), {'ticker': '005930', 'date': '2024-12-31'}).fetchone()

    print(f"PER: {result.per}, ROA: {result.roa}%")
    db.close()
        """)

        print("-" * 80 + "\n")

    except Exception as e:
        db.rollback()
        logger.exception(f"Error creating view: {e}")
        raise
    finally:
        db.close()


def drop_view():
    """뷰 삭제."""
    db = SessionLocal()

    try:
        logger.info("Dropping vw_daily_combined_ratios view...")
        db.execute(text(DROP_VIEW_SQL))
        db.commit()
        logger.info("✓ View dropped successfully")
    except Exception as e:
        db.rollback()
        logger.exception(f"Error dropping view: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PostgreSQL 통합 재무비율 뷰 관리")
    parser.add_argument('--drop', action='store_true', help='뷰 삭제')

    args = parser.parse_args()

    if args.drop:
        drop_view()
    else:
        create_view()
