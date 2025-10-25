#!/usr/bin/env python3
"""종목 리스트 수집 스크립트.

KRX에서 KOSPI, KOSDAQ 상장 종목 리스트를 수집하여 데이터베이스에 저장합니다.

Usage:
    # 전체 시장 (KOSPI + KOSDAQ) 수집
    python scripts/collect_stocks.py

    # KOSPI만 수집
    python scripts/collect_stocks.py --market KOSPI

    # KOSDAQ만 수집
    python scripts/collect_stocks.py --market KOSDAQ

    # 특정 날짜 기준으로 수집
    python scripts/collect_stocks.py --date 20250101
"""

import sys
from pathlib import Path
import argparse
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from collectors import KRXCollector
from db.connection import test_connection


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


def main():
    """메인 함수."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="KRX 상장 종목 리스트 수집 스크립트"
    )
    parser.add_argument(
        "--market",
        type=str,
        default="ALL",
        choices=["ALL", "KOSPI", "KOSDAQ", "KONEX"],
        help="수집할 시장 (기본값: ALL)"
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="수집 기준 날짜 (YYYYMMDD 형식, 기본값: 오늘)"
    )

    args = parser.parse_args()

    # Print header
    print_header("KRX Stock List Collection")
    print(f"Execution time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Market: {args.market}")
    print(f"Date: {args.date or 'today'}")

    # Step 1: Test database connection
    print_section("Step 1: Testing Database Connection")
    if not test_connection():
        print("\n❌ Database connection failed!")
        print("Please check your .env configuration and ensure PostgreSQL is running.")
        sys.exit(1)

    # Step 2: Collect stocks from KRX
    print_section(f"Step 2: Collecting Stocks from KRX ({args.market})")

    try:
        with KRXCollector() as collector:
            result = collector.collect_and_save(
                market=args.market,
                target_date=args.date
            )

            print(f"\n✅ Collection completed successfully!")
            print(f"   - Fetched from KRX: {result['fetched']:,} stocks")
            print(f"   - Saved to database: {result['saved']:,} stocks")

            # Step 3: Verify database contents
            print_section("Step 3: Verifying Database Contents")

            counts = collector.get_stock_count_by_market()

            print("\nStocks in database by market:")
            print("-" * 70)
            print(f"{'Market':<15} {'Count':>10}")
            print("-" * 70)

            for market, count in sorted(counts.items()):
                if market != "TOTAL":
                    print(f"{market:<15} {count:>10,}")

            print("-" * 70)
            print(f"{'TOTAL':<15} {counts['TOTAL']:>10,}")
            print("-" * 70)

            # Step 4: Show sample stocks
            print_section("Step 4: Sample Stocks from Database")

            from db.connection import SessionLocal
            from models import Stock

            db = SessionLocal()
            try:
                # Show first 10 stocks from database
                sample_stocks = db.query(Stock).filter_by(is_active=True).limit(10).all()

                print(f"\n{'No':<4} {'Ticker':<8} {'Name':<25} {'Market':<10}")
                print("-" * 70)
                for i, stock in enumerate(sample_stocks, 1):
                    print(f"{i:<4} {stock.ticker:<8} {stock.name:<25} {stock.market.value:<10}")

                print(f"\n... and {counts['TOTAL'] - 10:,} more stocks in database")

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
    print("✅ Stock collection process completed successfully!")
    print("=" * 70)
    print("\nNext steps:")
    print("  1. Verify data in TablePlus: stocks table should have records")
    print("  2. Check logs: logs/krx_collector_*.log")
    print("  3. Continue with Day 4: KIS API integration for daily price data")
    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
