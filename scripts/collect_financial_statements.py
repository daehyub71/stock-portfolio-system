#!/usr/bin/env python3
"""재무제표 수집 스크립트.

DART API를 사용하여 기업의 재무제표를 수집하고 데이터베이스에 저장합니다.

Usage:
    # 샘플 10개 종목의 최근 3년 재무제표 수집
    python scripts/collect_financial_statements.py --sample

    # 특정 종목의 재무제표 수집
    python scripts/collect_financial_statements.py --ticker 005930 --years 2024 2023 2022

    # 여러 종목 수집
    python scripts/collect_financial_statements.py --tickers 005930 000660 035420 --years 2024 2023
"""

import sys
from pathlib import Path
import argparse
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from collectors import DARTCollector
from db.connection import SessionLocal
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


def get_sample_tickers(db, limit: int = 10) -> list:
    """Get sample tickers from database.

    Prioritizes well-known large-cap stocks from KOSPI.

    Args:
        db: Database session
        limit: Number of tickers to return

    Returns:
        List of ticker strings
    """
    # Well-known Korean stocks with DART corp_codes
    priority_tickers = [
        "005930",  # 삼성전자
        "000660",  # SK하이닉스
        "035420",  # NAVER
        "005380",  # 현대차
        "051910",  # LG화학
        "006400",  # 삼성SDI
        "035720",  # 카카오
        "000270",  # 기아
        "068270",  # 셀트리온
        "207940",  # 삼성바이오로직스
    ]

    # Try to get these stocks from DB
    tickers = []
    for ticker in priority_tickers[:limit]:
        stock = db.query(Stock).filter_by(ticker=ticker).first()
        if stock:
            tickers.append(ticker)

    # If we don't have enough, get any active KOSPI stocks
    if len(tickers) < limit:
        additional = db.query(Stock).filter_by(
            is_active=True
        ).limit(limit - len(tickers)).all()

        tickers.extend([s.ticker for s in additional if s.ticker not in tickers])

    return tickers[:limit]


def collect_financial_statements(
    tickers: list,
    years: list,
    db_session=None
):
    """Collect financial statements for given tickers and years.

    Args:
        tickers: List of stock tickers
        years: List of years to collect
        db_session: Database session (optional)
    """
    print_section("Starting Financial Statement Collection")
    print(f"Tickers: {', '.join(tickers)}")
    print(f"Years: {', '.join(map(str, years))}")
    print(f"Total jobs: {len(tickers)} stocks × {len(years)} years = {len(tickers) * len(years)}")

    collector = DARTCollector(db_session=db_session)

    total_fetched = 0
    total_saved = 0
    failed_jobs = []

    for i, ticker in enumerate(tickers, 1):
        print(f"\n[{i}/{len(tickers)}] Processing {ticker}...")

        try:
            result = collector.collect_and_save(
                ticker=ticker,
                years=years
            )

            total_fetched += result["fetched"]
            total_saved += result["saved"]

            print(f"  ✅ {ticker}: Fetched {result['fetched']}, Saved {result['saved']}")

        except Exception as e:
            print(f"  ❌ {ticker}: Failed - {e}")
            failed_jobs.append({"ticker": ticker, "error": str(e)})
            continue

    # Summary
    print_section("Collection Summary")
    print(f"Total financial statements fetched: {total_fetched}")
    print(f"Total financial statements saved: {total_saved}")
    print(f"Success rate: {total_saved}/{len(tickers) * len(years)} jobs")

    if failed_jobs:
        print(f"\n⚠️  Failed jobs ({len(failed_jobs)}):")
        for job in failed_jobs:
            print(f"  - {job['ticker']}: {job['error']}")
    else:
        print("\n✅ All jobs completed successfully!")

    return {
        "fetched": total_fetched,
        "saved": total_saved,
        "failed": len(failed_jobs)
    }


def main():
    """메인 함수."""
    parser = argparse.ArgumentParser(
        description="Collect financial statements from DART API"
    )

    # Ticker selection options
    ticker_group = parser.add_mutually_exclusive_group()
    ticker_group.add_argument(
        "--sample",
        action="store_true",
        help="Collect for 10 sample large-cap stocks"
    )
    ticker_group.add_argument(
        "--ticker",
        type=str,
        help="Single ticker to collect (e.g., 005930)"
    )
    ticker_group.add_argument(
        "--tickers",
        nargs="+",
        help="Multiple tickers to collect (e.g., 005930 000660 035420)"
    )

    # Year selection
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=[2024, 2023, 2022],
        help="Years to collect (default: 2024 2023 2022)"
    )

    args = parser.parse_args()

    print_header("DART Financial Statement Collection")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Determine which tickers to collect
    db = SessionLocal()

    try:
        if args.sample:
            tickers = get_sample_tickers(db, limit=10)
            print(f"\n📊 Sample mode: Selected {len(tickers)} stocks")
        elif args.ticker:
            tickers = [args.ticker]
            print(f"\n📊 Single ticker mode: {args.ticker}")
        elif args.tickers:
            tickers = args.tickers
            print(f"\n📊 Multiple ticker mode: {len(tickers)} stocks")
        else:
            print("\n⚠️  No ticker selection provided!")
            print("Use --sample, --ticker, or --tickers option")
            print("\nExamples:")
            print("  python scripts/collect_financial_statements.py --sample")
            print("  python scripts/collect_financial_statements.py --ticker 005930")
            print("  python scripts/collect_financial_statements.py --tickers 005930 000660")
            sys.exit(1)

        if not tickers:
            print("\n❌ No tickers found in database!")
            print("Please run: python scripts/collect_stocks.py --market ALL")
            sys.exit(1)

        # Collect financial statements
        result = collect_financial_statements(
            tickers=tickers,
            years=args.years,
            db_session=db
        )

        # Final summary
        print("\n" + "=" * 70)
        print("✅ Financial statement collection completed!")
        print("=" * 70)
        print(f"\nResults:")
        print(f"  - Fetched: {result['fetched']}")
        print(f"  - Saved: {result['saved']}")
        print(f"  - Failed: {result['failed']}")
        print(f"\nFinished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("\nNext steps:")
        print("  1. Verify data in TablePlus: financial_statements table")
        print("  2. Check JSONB columns: balance_sheet, income_statement, cash_flow")
        print("  3. Proceed to Day 6: Financial Ratio Calculation")
        print("=" * 70)

    except Exception as e:
        print("\n" + "=" * 70)
        print("❌ Error occurred:")
        print("=" * 70)
        print(str(e))
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
