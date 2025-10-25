#!/usr/bin/env python3
"""주가 데이터 수집 스크립트.

KIS API를 사용하여 종목별 일별 주가 데이터(OHLCV)를 수집합니다.

Usage:
    # 샘플 10개 종목 수집
    python scripts/collect_prices.py --sample

    # 특정 종목 수집
    python scripts/collect_prices.py --ticker 005930

    # 여러 종목 수집
    python scripts/collect_prices.py --tickers 005930,000660,035720

    # 모든 KOSPI 종목 수집 (주의: 시간이 오래 걸림)
    python scripts/collect_prices.py --market KOSPI

    # 기간 지정 (기본 100일)
    python scripts/collect_prices.py --sample --days 30
"""

import sys
from pathlib import Path
import argparse
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from collectors import KISPriceCollector
from db.connection import SessionLocal, test_connection
from models import Stock


def print_header(title: str):
    """Print formatted header."""
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + f" {title:^66} " + "║")
    print("╚" + "═" * 68 + "╝")
    print()


def print_section(title: str):
    """Print section separator."""
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def get_sample_stocks(db, count: int = 10) -> list:
    """Get sample stocks for testing.

    Args:
        db: Database session
        count: Number of stocks to return

    Returns:
        List of stock tickers
    """
    # Get top stocks by market cap (major stocks)
    sample_tickers = [
        "005930",  # 삼성전자
        "000660",  # SK하이닉스
        "035720",  # 카카오
        "005380",  # 현대차
        "051910",  # LG화학
        "006400",  # 삼성SDI
        "035420",  # NAVER
        "000270",  # 기아
        "068270",  # 셀트리온
        "105560",  # KB금융
    ]

    # Verify stocks exist in database
    existing_tickers = []
    for ticker in sample_tickers[:count]:
        stock = db.query(Stock).filter_by(ticker=ticker).first()
        if stock:
            existing_tickers.append((ticker, stock.name))
        else:
            print(f"⚠️  Stock {ticker} not found in database")

    return existing_tickers


def main():
    """메인 함수."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="KIS API를 사용한 주가 데이터 수집 스크립트"
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="샘플 10개 종목 수집"
    )
    parser.add_argument(
        "--ticker",
        type=str,
        help="단일 종목 코드 (e.g., 005930)"
    )
    parser.add_argument(
        "--tickers",
        type=str,
        help="여러 종목 코드 (쉼표로 구분, e.g., 005930,000660)"
    )
    parser.add_argument(
        "--market",
        type=str,
        choices=["KOSPI", "KOSDAQ"],
        help="시장별 전체 수집 (주의: 시간이 오래 걸림)"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=100,
        help="수집할 일수 (기본값: 100일)"
    )

    args = parser.parse_args()

    # Validate arguments
    if not any([args.sample, args.ticker, args.tickers, args.market]):
        parser.error("--sample, --ticker, --tickers, 또는 --market 중 하나를 선택해야 합니다")

    # Print header
    print_header("KIS Price Data Collection")
    print(f"Execution time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Days to collect: {args.days}")

    # Step 1: Test database connection
    print_section("Step 1: Testing Database Connection")
    if not test_connection():
        print("\n❌ Database connection failed!")
        print("Please check your .env configuration and ensure PostgreSQL is running.")
        sys.exit(1)

    # Step 2: Determine which stocks to collect
    print_section("Step 2: Selecting Stocks")

    db = SessionLocal()
    tickers_to_collect = []

    try:
        if args.sample:
            print("Using sample stocks (top 10 major stocks)")
            stock_list = get_sample_stocks(db, count=10)
            tickers_to_collect = [ticker for ticker, name in stock_list]

            print(f"\n{'Ticker':<10} {'Name':<25}")
            print("-" * 70)
            for ticker, name in stock_list:
                print(f"{ticker:<10} {name:<25}")

        elif args.ticker:
            stock = db.query(Stock).filter_by(ticker=args.ticker).first()
            if stock:
                tickers_to_collect = [args.ticker]
                print(f"Single stock: {args.ticker} ({stock.name})")
            else:
                print(f"❌ Stock {args.ticker} not found in database")
                sys.exit(1)

        elif args.tickers:
            ticker_list = [t.strip() for t in args.tickers.split(",")]
            for ticker in ticker_list:
                stock = db.query(Stock).filter_by(ticker=ticker).first()
                if stock:
                    tickers_to_collect.append(ticker)
                    print(f"  ✓ {ticker} ({stock.name})")
                else:
                    print(f"  ⚠️  {ticker} not found in database")

        elif args.market:
            from models import MarketType
            market_type = MarketType[args.market]
            stocks = db.query(Stock).filter_by(
                market=market_type,
                is_active=True
            ).limit(100).all()  # Limit to 100 for safety

            tickers_to_collect = [stock.ticker for stock in stocks]
            print(f"Selected {len(tickers_to_collect)} stocks from {args.market}")
            print(f"(Limited to 100 stocks for this test)")

    finally:
        db.close()

    if not tickers_to_collect:
        print("\n❌ No stocks to collect!")
        sys.exit(1)

    print(f"\n📊 Total stocks to collect: {len(tickers_to_collect)}")

    # Step 3: Collect price data
    print_section(f"Step 3: Collecting Price Data ({args.days} days)")

    try:
        with KISPriceCollector() as collector:
            result = collector.collect_batch(
                tickers=tickers_to_collect,
                days=args.days
            )

            print(f"\n✅ Collection completed!")
            print(f"\n{'Metric':<30} {'Value':>15}")
            print("-" * 70)
            print(f"{'Total stocks attempted':<30} {result['total_stocks']:>15,}")
            print(f"{'Successfully collected':<30} {result['success_count']:>15,}")
            print(f"{'Failed':<30} {result['failed_count']:>15,}")
            print(f"{'Total records fetched':<30} {result['total_fetched']:>15,}")
            print(f"{'Total records saved':<30} {result['total_saved']:>15,}")

            if result['failed_tickers']:
                print(f"\n⚠️  Failed tickers: {', '.join(result['failed_tickers'])}")

            # Step 4: Verify database contents
            print_section("Step 4: Verifying Database Contents")

            from models import DailyPrice

            db = SessionLocal()
            try:
                # Count total daily_prices records
                total_prices = db.query(DailyPrice).count()
                print(f"\nTotal price records in database: {total_prices:,}")

                # Show sample records
                sample_prices = db.query(DailyPrice).limit(5).all()

                print(f"\n{'Ticker':<10} {'Date':<12} {'Open':>10} {'High':>10} {'Low':>10} {'Close':>10} {'Volume':>12}")
                print("-" * 90)

                for price in sample_prices:
                    stock = db.query(Stock).filter_by(id=price.stock_id).first()
                    ticker = stock.ticker if stock else "N/A"

                    print(
                        f"{ticker:<10} {price.date.strftime('%Y-%m-%d'):<12} "
                        f"{price.open_price:>10,.0f} {price.high_price:>10,.0f} "
                        f"{price.low_price:>10,.0f} {price.close_price:>10,.0f} "
                        f"{price.volume:>12,}"
                    )

                print(f"\n... and {total_prices - 5:,} more records")

            finally:
                db.close()

    except Exception as e:
        print(f"\n❌ Error occurred during collection:")
        print(f"   {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Success summary
    print("\n" + "=" * 70)
    print("✅ Price collection process completed successfully!")
    print("=" * 70)
    print("\nNext steps:")
    print("  1. Verify data in TablePlus: daily_prices table should have records")
    print("  2. Check logs: logs/kis_collector_*.log")
    print("  3. Continue with Day 5: DART API integration for financial data")
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
