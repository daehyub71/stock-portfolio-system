#!/usr/bin/env python3
"""DART API 테스트 스크립트.

DART OpenAPI를 사용하여 재무제표 조회 기능을 테스트합니다.

Features:
- corp_code 조회 테스트
- 재무제표 조회 테스트 (삼성전자 예제)
- JSONB 파싱 테스트
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from collectors import DARTCollector
from db.connection import SessionLocal
from models import CorpCodeMap

load_dotenv()


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


def test_api_key():
    """Test DART API key availability."""
    print_section("Test 1: DART API Key Check")

    api_key = os.getenv("DART_API_KEY")

    if api_key:
        print(f"✅ DART_API_KEY found: {api_key[:10]}...")
        return True
    else:
        print("❌ DART_API_KEY not found in .env file!")
        print("\nPlease get your free API key from:")
        print("https://opendart.fss.or.kr/")
        print("\nThen add it to your .env file:")
        print("DART_API_KEY=your_api_key_here")
        return False


def test_corp_code_mapping():
    """Test corp_code mapping in database."""
    print_section("Test 2: Corp Code Mapping")

    db = SessionLocal()

    try:
        total_count = db.query(CorpCodeMap).count()
        print(f"Total corp codes in database: {total_count:,}")

        if total_count == 0:
            print("\n⚠️  No corp codes found!")
            print("Please run: python scripts/download_corp_codes.py")
            return False

        # Test with 삼성전자 (005930)
        samsung = db.query(CorpCodeMap).filter_by(ticker="005930").first()

        if samsung:
            print(f"\n✅ Test ticker mapping (삼성전자):")
            print(f"  - Ticker: {samsung.ticker}")
            print(f"  - Corp Code: {samsung.corp_code}")
            print(f"  - Corp Name: {samsung.corp_name}")
            print(f"  - Stock Name: {samsung.stock_name}")
            return True
        else:
            print("\n❌ Samsung Electronics (005930) not found in mapping!")
            return False

    finally:
        db.close()


def test_financial_statement_fetch():
    """Test fetching financial statement from DART API."""
    print_section("Test 3: Financial Statement Fetch (삼성전자)")

    db = SessionLocal()

    try:
        collector = DARTCollector(db_session=db)

        # Get Samsung Electronics corp_code
        corp_code = collector.get_corp_code("005930")

        if not corp_code:
            print("❌ Failed to get corp_code for 005930")
            return False

        print(f"Corp code: {corp_code}")
        print("\nFetching 2023 annual report...")

        # Fetch 2023 annual financial statement
        financial_data = collector.fetch_financial_statement(
            corp_code=corp_code,
            bsns_year="2023",
            reprt_code="11011"  # Annual report
        )

        if financial_data:
            print("\n✅ Financial statement fetched successfully!")

            # Show structure
            print("\nFinancial Statement Structure:")
            print(f"  - Balance Sheet items: {len(financial_data.get('balance_sheet', {}).get('assets', {}).get('current', {}))}")
            print(f"  - Income Statement items: {len(financial_data.get('income_statement', {}).get('revenue', {}))}")
            print(f"  - Cash Flow items: {len(financial_data.get('cash_flow', {}).get('operating', {}))}")
            print(f"  - Raw data items: {len(financial_data.get('raw_data', []))}")

            # Show sample balance sheet data
            print("\nSample Balance Sheet (Current Assets):")
            current_assets = financial_data.get('balance_sheet', {}).get('assets', {}).get('current', {})
            for i, (key, value) in enumerate(list(current_assets.items())[:5]):
                print(f"  {i+1}. {key}: {value:,.0f}")

            # Show sample income statement data
            print("\nSample Income Statement (Revenue):")
            revenue = financial_data.get('income_statement', {}).get('revenue', {})
            for i, (key, value) in enumerate(list(revenue.items())[:5]):
                print(f"  {i+1}. {key}: {value:,.0f}")

            return True
        else:
            print("\n❌ Failed to fetch financial statement")
            print("Possible reasons:")
            print("  - Invalid API key")
            print("  - API rate limit exceeded")
            print("  - Network error")
            return False

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def test_database_save():
    """Test saving financial statement to database."""
    print_section("Test 4: Database Save")

    db = SessionLocal()

    try:
        collector = DARTCollector(db_session=db)

        print("Testing financial statement collection and save...")
        print("Ticker: 005930 (삼성전자)")
        print("Years: [2023]")

        result = collector.collect_and_save(
            ticker="005930",
            years=[2023]
        )

        print(f"\n✅ Collection and save completed!")
        print(f"  - Fetched: {result['fetched']}")
        print(f"  - Saved: {result['saved']}")
        print(f"  - Ticker: {result['ticker']}")

        if result['saved'] > 0:
            print("\n✅ Database save successful!")
            print("\nYou can verify in TablePlus:")
            print("  SELECT * FROM financial_statements WHERE stock_id = (SELECT id FROM stocks WHERE ticker = '005930');")
            return True
        else:
            print("\n⚠️  No data saved (might already exist or API returned no data)")
            return False

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def main():
    """메인 함수."""
    print_header("DART API Test Script")
    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Run tests
    results = []

    # Test 1: API Key
    test1_result = test_api_key()
    results.append(("API Key Check", test1_result))

    if not test1_result:
        print("\n" + "=" * 70)
        print("⚠️  Cannot proceed without DART API key")
        print("=" * 70)
        sys.exit(1)

    # Test 2: Corp Code Mapping
    test2_result = test_corp_code_mapping()
    results.append(("Corp Code Mapping", test2_result))

    if not test2_result:
        print("\n" + "=" * 70)
        print("⚠️  Please run corp_code download script first:")
        print("python scripts/download_corp_codes.py")
        print("=" * 70)
        sys.exit(1)

    # Test 3: Financial Statement Fetch
    test3_result = test_financial_statement_fetch()
    results.append(("Financial Statement Fetch", test3_result))

    # Test 4: Database Save
    test4_result = test_database_save()
    results.append(("Database Save", test4_result))

    # Summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)

    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name:<30} {status}")

    all_passed = all(result for _, result in results)

    if all_passed:
        print("\n✅ All tests passed! DART API integration is working correctly.")
        print("\nNext steps:")
        print("  1. Run: python scripts/collect_financial_statements.py --sample")
        print("  2. Verify data in TablePlus: financial_statements table")
        print("  3. Proceed to Day 6: Financial Ratio Calculation")
    else:
        print("\n❌ Some tests failed. Please check the error messages above.")

    print("=" * 70)


if __name__ == "__main__":
    main()
