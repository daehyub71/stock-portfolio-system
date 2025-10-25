#!/usr/bin/env python3
"""KRX API 테스트 스크립트.

pykrx 라이브러리를 사용하여 KRX (한국거래소) 상장 종목 리스트를 가져옵니다.

pykrx는 KRX 데이터를 쉽게 가져올 수 있는 Python 라이브러리입니다:
- 별도의 API 키 불필요
- KOSPI, KOSDAQ, KONEX 전 종목 지원
- 실시간 시세, 재무 데이터 등 다양한 기능 제공
"""

from pykrx import stock
import pandas as pd
from datetime import datetime


def test_kospi_stock_list():
    """KOSPI 상장 종목 리스트 조회 테스트."""
    print("=" * 70)
    print("Testing pykrx - KOSPI Stock List")
    print("=" * 70)

    try:
        # KOSPI 종목 리스트 조회
        today = datetime.now().strftime("%Y%m%d")
        tickers = stock.get_market_ticker_list(today, market="KOSPI")

        print(f"\n✅ Successfully fetched {len(tickers)} KOSPI stocks\n")

        # 처음 10개 종목의 상세 정보 출력
        print("Sample stocks (first 10):")
        print("-" * 70)
        print(f"{'No':<4} {'Ticker':<8} {'Name':<20} {'Market':<10}")
        print("-" * 70)

        for i, ticker in enumerate(tickers[:10], 1):
            name = stock.get_market_ticker_name(ticker)
            print(f"{i:<4} {ticker:<8} {name:<20} KOSPI")

        print(f"\n... and {len(tickers) - 10} more stocks")

        return True, tickers

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def test_kosdaq_stock_list():
    """KOSDAQ 상장 종목 리스트 조회 테스트."""
    print("\n" + "=" * 70)
    print("Testing pykrx - KOSDAQ Stock List")
    print("=" * 70)

    try:
        # KOSDAQ 종목 리스트 조회
        today = datetime.now().strftime("%Y%m%d")
        tickers = stock.get_market_ticker_list(today, market="KOSDAQ")

        print(f"\n✅ Successfully fetched {len(tickers)} KOSDAQ stocks\n")

        # 처음 10개 종목의 상세 정보 출력
        print("Sample stocks (first 10):")
        print("-" * 70)
        print(f"{'No':<4} {'Ticker':<8} {'Name':<20} {'Market':<10}")
        print("-" * 70)

        for i, ticker in enumerate(tickers[:10], 1):
            name = stock.get_market_ticker_name(ticker)
            print(f"{i:<4} {ticker:<8} {name:<20} KOSDAQ")

        print(f"\n... and {len(tickers) - 10} more stocks")

        return True, tickers

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def test_stock_detail_info():
    """종목 상세 정보 조회 테스트 (삼성전자 예제)."""
    print("\n" + "=" * 70)
    print("Testing Stock Detail Information - 삼성전자 (005930)")
    print("=" * 70)

    try:
        ticker = "005930"  # 삼성전자
        name = stock.get_market_ticker_name(ticker)

        print(f"\n종목명: {name}")
        print(f"종목코드: {ticker}")

        # 오늘 날짜로 시세 조회
        today = datetime.now().strftime("%Y%m%d")

        # 최근 5일 OHLCV 데이터 조회
        from datetime import timedelta
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)

        df = stock.get_market_ohlcv_by_date(
            start_date.strftime("%Y%m%d"),
            end_date.strftime("%Y%m%d"),
            ticker
        )

        if not df.empty:
            print(f"\n최근 {len(df)}일 주가 데이터:")
            print("-" * 70)
            print(df.to_string())
        else:
            print("\n⚠️  최근 주가 데이터가 없습니다 (주말 또는 휴장일일 수 있습니다)")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_available_functions():
    """pykrx에서 사용 가능한 주요 함수들 테스트."""
    print("\n" + "=" * 70)
    print("pykrx Available Functions Overview")
    print("=" * 70)

    print("\n📊 Stock Data Functions:")
    print("-" * 70)

    functions = [
        ("get_market_ticker_list(date, market)", "특정 날짜의 시장별 상장 종목 리스트"),
        ("get_market_ticker_name(ticker)", "종목코드로 종목명 조회"),
        ("get_market_ohlcv_by_date(from, to, ticker)", "일별 OHLCV 시세 조회"),
        ("get_market_cap_by_ticker(date, market)", "시가총액 정보 조회"),
        ("get_market_fundamental_by_ticker(date, market)", "PER, PBR, EPS, BPS 조회"),
    ]

    for func, desc in functions:
        print(f"  • {func:<45} - {desc}")

    print("\n💡 These functions will be used in KRXCollector class")

    return True


def main():
    """메인 함수."""
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 18 + "pykrx API Test Script" + " " * 27 + "║")
    print("╚" + "═" * 68 + "╝")
    print(f"\nTest started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Test 1: KOSPI 종목 리스트
    kospi_success, kospi_tickers = test_kospi_stock_list()

    # Test 2: KOSDAQ 종목 리스트
    kosdaq_success, kosdaq_tickers = test_kosdaq_stock_list()

    # Test 3: 종목 상세 정보
    detail_success = test_stock_detail_info()

    # Test 4: 사용 가능한 함수들
    func_success = test_available_functions()

    # 결과 요약
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)
    print(f"KOSPI Test:        {'✅ PASSED' if kospi_success else '❌ FAILED'}")
    if kospi_success:
        print(f"  - Total stocks: {len(kospi_tickers)}")

    print(f"KOSDAQ Test:       {'✅ PASSED' if kosdaq_success else '❌ FAILED'}")
    if kosdaq_success:
        print(f"  - Total stocks: {len(kosdaq_tickers)}")

    print(f"Detail Info Test:  {'✅ PASSED' if detail_success else '❌ FAILED'}")
    print(f"Functions Test:    {'✅ PASSED' if func_success else '❌ FAILED'}")

    if kospi_success and kosdaq_success:
        total_stocks = len(kospi_tickers) + len(kosdaq_tickers)
        print(f"\n📊 Total stocks available: {total_stocks:,}")
        print(f"   - KOSPI:  {len(kospi_tickers):,}")
        print(f"   - KOSDAQ: {len(kosdaq_tickers):,}")
        print("\n✅ All tests passed! pykrx is working correctly.")
    else:
        print("\n❌ Some tests failed. Please check the error messages above.")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
