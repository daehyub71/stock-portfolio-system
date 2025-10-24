"""빈 손익계산서를 가진 종목 식별.

88.9% 종목의 손익계산서가 비어있는 문제 해결을 위해
재수집이 필요한 종목 목록을 추출합니다.

원인: DART collector가 "IS"만 처리하고 "CIS"를 처리하지 않음
해결: collectors/dart_collector.py 수정 완료 (line 231)

사용법:
    python scripts/get_empty_income_statement_stocks.py
    python scripts/get_empty_income_statement_stocks.py --output stocks_to_recollect.txt
    python scripts/get_empty_income_statement_stocks.py --show-sample 20
"""

import sys
from pathlib import Path
from sqlalchemy import text, func
from loguru import logger

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from db.connection import SessionLocal
from models import Stock, FinancialStatement

# Configure logger
logger.add(
    "logs/get_empty_income_statement_stocks_{time}.log",
    rotation="1 day",
    retention="30 days",
    level="INFO"
)


def get_empty_income_statement_stocks(db_session):
    """빈 손익계산서를 가진 종목 조회.

    Returns:
        List[Dict]: 종목 정보 리스트 (ticker, name, years with empty data)
    """
    logger.info("Querying stocks with empty income statements...")

    # 빈 손익계산서 구조
    empty_is = {"profit": {}, "revenue": {}, "expenses": {}}

    # 빈 손익계산서를 가진 재무제표 조회
    # JSONB 직접 비교
    query = text("""
        SELECT
            s.ticker,
            s.name,
            s.market,
            fs.fiscal_year,
            COUNT(*) as count
        FROM financial_statements fs
        INNER JOIN stocks s ON fs.stock_id = s.id
        WHERE fs.income_statement = '{"profit": {}, "revenue": {}, "expenses": {}}'::jsonb
          AND fs.fiscal_year IS NOT NULL
        GROUP BY s.ticker, s.name, s.market, fs.fiscal_year
        ORDER BY s.ticker, fs.fiscal_year DESC
    """)

    result = db_session.execute(query).fetchall()

    # 종목별로 그룹화
    stocks_dict = {}
    for row in result:
        ticker = row.ticker
        if ticker not in stocks_dict:
            stocks_dict[ticker] = {
                "ticker": ticker,
                "name": row.name,
                "market": row.market,
                "empty_years": []
            }
        stocks_dict[ticker]["empty_years"].append(row.fiscal_year)

    stocks_list = list(stocks_dict.values())
    logger.info(f"Found {len(stocks_list)} stocks with empty income statements")

    return stocks_list


def print_statistics(stocks_list, db_session):
    """통계 출력."""
    print("=" * 80)
    print("📊 빈 손익계산서 종목 통계")
    print("=" * 80)

    # 전체 종목 수
    total_stocks = db_session.query(func.count(Stock.id)).filter(Stock.is_active == True).scalar()

    # 전체 재무제표 수
    total_stmts = db_session.query(func.count(FinancialStatement.id)).filter(
        FinancialStatement.fiscal_year.isnot(None)
    ).scalar()

    # 빈 손익계산서 재무제표 수
    empty_stmts = db_session.execute(
        text("SELECT COUNT(*) FROM financial_statements WHERE income_statement = '{\"profit\": {}, \"revenue\": {}, \"expenses\": {}}'::jsonb")
    ).scalar()

    print(f"\n전체 활성 종목:        {total_stocks:,}개")
    print(f"전체 재무제표:         {total_stmts:,}건")
    print(f"빈 손익계산서:         {empty_stmts:,}건 ({empty_stmts/total_stmts*100:.1f}%)")
    print(f"\n재수집 필요 종목:      {len(stocks_list):,}개")

    # 시장별 분포
    market_dist = {}
    for stock in stocks_list:
        market = stock["market"]
        market_dist[market] = market_dist.get(market, 0) + 1

    print(f"\n시장별 분포:")
    for market, count in sorted(market_dist.items()):
        print(f"  {market}: {count:,}개")

    # 연도별 분포
    year_dist = {}
    for stock in stocks_list:
        for year in stock["empty_years"]:
            year_dist[year] = year_dist.get(year, 0) + 1

    print(f"\n연도별 분포:")
    for year in sorted(year_dist.keys(), reverse=True):
        count = year_dist[year]
        print(f"  {year}: {count:,}건")

    print("=" * 80)


def print_sample(stocks_list, sample_size=20):
    """샘플 출력."""
    print(f"\n📋 샘플 종목 ({sample_size}개)")
    print("-" * 80)

    for i, stock in enumerate(stocks_list[:sample_size], 1):
        years_str = ", ".join(map(str, sorted(stock["empty_years"], reverse=True)))
        print(f"{i:2}. {stock['ticker']:6} {stock['name']:20} {stock['market']:6} | 빈 연도: {years_str}")

    if len(stocks_list) > sample_size:
        print(f"... 외 {len(stocks_list) - sample_size:,}개 종목")

    print("-" * 80)


def save_to_file(stocks_list, output_file):
    """파일로 저장 (ticker만)."""
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        for stock in stocks_list:
            f.write(f"{stock['ticker']}\n")

    logger.info(f"Saved {len(stocks_list)} tickers to {output_path}")
    print(f"\n✓ {len(stocks_list):,}개 종목 티커를 저장했습니다: {output_path}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="빈 손익계산서를 가진 종목 식별")
    parser.add_argument('--output', '-o', help='출력 파일 경로 (티커만 저장)')
    parser.add_argument('--show-sample', type=int, default=20, help='샘플 출력 개수 (default: 20)')
    parser.add_argument('--no-stats', action='store_true', help='통계 출력 생략')

    args = parser.parse_args()

    db = SessionLocal()

    try:
        # 종목 조회
        stocks_list = get_empty_income_statement_stocks(db)

        if not stocks_list:
            print("✓ 빈 손익계산서를 가진 종목이 없습니다!")
            return

        # 통계 출력
        if not args.no_stats:
            print_statistics(stocks_list, db)

        # 샘플 출력
        if args.show_sample > 0:
            print_sample(stocks_list, args.show_sample)

        # 파일 저장
        if args.output:
            save_to_file(stocks_list, args.output)

        # 재수집 안내
        print("\n" + "=" * 80)
        print("🔧 재수집 방법")
        print("=" * 80)
        print("\n1. 전체 종목 재수집:")
        print("   python scripts/batch_collect_financials.py --all-groups")
        print("\n2. 특정 종목 재수집:")
        print("   python scripts/collect_financial_statements.py --ticker <TICKER> --years 2024 2023 2022")
        print("\n3. 티커 목록 파일로 재수집:")
        print("   python scripts/get_empty_income_statement_stocks.py --output stocks_to_recollect.txt")
        print("   # (batch script with --stocks-file support needed)")
        print("=" * 80 + "\n")

    except Exception as e:
        logger.exception(f"Error: {e}")
        print(f"\n❌ Error: {e}")
        return 1
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
