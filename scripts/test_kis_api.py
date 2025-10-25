#!/usr/bin/env python3
"""KIS (한국투자증권) API 테스트 스크립트.

KIS API를 사용하여 주가 데이터를 조회하는 기능을 테스트합니다.

Requirements:
- .env 파일에 KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT_TYPE 설정 필요

API Documentation:
- https://apiportal.koreainvestment.com/
"""

import os
import sys
from pathlib import Path
import httpx
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# KIS API configuration
KIS_APP_KEY = os.getenv("KIS_APP_KEY")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET")
KIS_ACCOUNT_TYPE = os.getenv("KIS_ACCOUNT_TYPE", "REAL")  # REAL or VIRTUAL

# API endpoints
if KIS_ACCOUNT_TYPE == "VIRTUAL":
    KIS_BASE_URL = "https://openapivts.koreainvestment.com:29443"
else:
    KIS_BASE_URL = "https://openapi.koreainvestment.com:9443"

KIS_TOKEN_URL = f"{KIS_BASE_URL}/oauth2/tokenP"
KIS_PRICE_URL = f"{KIS_BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
KIS_DAILY_PRICE_URL = f"{KIS_BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-daily-price"


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


def get_access_token() -> str:
    """KIS API 액세스 토큰 발급.

    Returns:
        Access token string

    Raises:
        Exception if token request fails
    """
    print_section("Step 1: Getting Access Token")

    if not KIS_APP_KEY or not KIS_APP_SECRET:
        raise ValueError(
            "KIS_APP_KEY and KIS_APP_SECRET must be set in .env file.\n"
            "Please get your API credentials from https://apiportal.koreainvestment.com/"
        )

    print(f"API Key: {KIS_APP_KEY[:10]}...")
    print(f"Account Type: {KIS_ACCOUNT_TYPE}")
    print(f"Base URL: {KIS_BASE_URL}")

    headers = {"content-type": "application/json"}
    data = {
        "grant_type": "client_credentials",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(KIS_TOKEN_URL, headers=headers, json=data)
            response.raise_for_status()

            result = response.json()

            if "access_token" in result:
                token = result["access_token"]
                expires_in = result.get("expires_in", "unknown")
                print(f"\n✅ Access token received")
                print(f"   Token: {token[:20]}...")
                print(f"   Expires in: {expires_in} seconds")
                return token
            else:
                print(f"\n❌ Unexpected response: {result}")
                raise Exception("Failed to get access token")

    except httpx.HTTPError as e:
        print(f"\n❌ HTTP Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Response: {e.response.text}")
        raise
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise


def get_current_price(access_token: str, ticker: str = "005930") -> dict:
    """현재가 조회 테스트.

    Args:
        access_token: KIS access token
        ticker: Stock ticker (default: 삼성전자)

    Returns:
        Price data dictionary
    """
    print_section(f"Step 2: Getting Current Price - {ticker}")

    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {access_token}",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
        "tr_id": "FHKST01010100"  # 주식현재가 시세
    }

    params = {
        "fid_cond_mrkt_div_code": "J",  # 시장 구분 (J: 주식)
        "fid_input_iscd": ticker  # 종목코드
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(KIS_PRICE_URL, headers=headers, params=params)
            response.raise_for_status()

            result = response.json()

            if result.get("rt_cd") == "0":  # Success
                data = result["output"]
                print(f"\n✅ Current price data received for {ticker}")
                print(f"\n{'Field':<30} {'Value':>15}")
                print("-" * 70)
                print(f"{'종목명':<30} {data.get('prdt_name', 'N/A'):>15}")
                print(f"{'현재가':<30} {int(data.get('stck_prpr', 0)):>15,}원")
                print(f"{'전일대비':<30} {int(data.get('prdy_vrss', 0)):>15,}원")
                print(f"{'등락률':<30} {float(data.get('prdy_ctrt', 0)):>15.2f}%")
                print(f"{'시가':<30} {int(data.get('stck_oprc', 0)):>15,}원")
                print(f"{'고가':<30} {int(data.get('stck_hgpr', 0)):>15,}원")
                print(f"{'저가':<30} {int(data.get('stck_lwpr', 0)):>15,}원")
                print(f"{'거래량':<30} {int(data.get('acml_vol', 0)):>15,}주")

                return data
            else:
                error_msg = result.get("msg1", "Unknown error")
                print(f"\n❌ API Error: {error_msg}")
                print(f"   Response: {json.dumps(result, indent=2, ensure_ascii=False)}")
                raise Exception(f"API returned error: {error_msg}")

    except httpx.HTTPError as e:
        print(f"\n❌ HTTP Error: {e}")
        raise
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise


def get_daily_prices(
    access_token: str,
    ticker: str = "005930",
    days: int = 30
) -> list:
    """일별 시세 조회 테스트.

    Args:
        access_token: KIS access token
        ticker: Stock ticker
        days: Number of days to fetch

    Returns:
        List of daily price data
    """
    print_section(f"Step 3: Getting Daily Prices - {ticker} ({days} days)")

    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {access_token}",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
        "tr_id": "FHKST01010400"  # 주식현재가 일자별
    }

    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days + 10)  # Add buffer for weekends

    params = {
        "fid_cond_mrkt_div_code": "J",
        "fid_input_iscd": ticker,
        "fid_period_div_code": "D",  # D: 일봉
        "fid_org_adj_prc": "0",  # 0: 수정주가 미반영
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(KIS_DAILY_PRICE_URL, headers=headers, params=params)
            response.raise_for_status()

            result = response.json()

            if result.get("rt_cd") == "0":
                data = result["output"]
                print(f"\n✅ Daily price data received: {len(data)} records")

                # Show first 5 records
                print(f"\n{'Date':<12} {'Open':>10} {'High':>10} {'Low':>10} {'Close':>10} {'Volume':>12}")
                print("-" * 70)

                for record in data[:5]:
                    date = record.get('stck_bsop_date', '')
                    formatted_date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
                    open_price = int(record.get('stck_oprc', 0))
                    high_price = int(record.get('stck_hgpr', 0))
                    low_price = int(record.get('stck_lwpr', 0))
                    close_price = int(record.get('stck_clpr', 0))
                    volume = int(record.get('acml_vol', 0))

                    print(
                        f"{formatted_date:<12} {open_price:>10,} {high_price:>10,} "
                        f"{low_price:>10,} {close_price:>10,} {volume:>12,}"
                    )

                print(f"\n... and {len(data) - 5} more records")

                return data
            else:
                error_msg = result.get("msg1", "Unknown error")
                print(f"\n❌ API Error: {error_msg}")
                raise Exception(f"API returned error: {error_msg}")

    except httpx.HTTPError as e:
        print(f"\n❌ HTTP Error: {e}")
        raise
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise


def main():
    """메인 함수."""
    print_header("KIS API Test Script")
    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        # Test 1: Get access token
        access_token = get_access_token()

        # Test 2: Get current price (삼성전자)
        current_price = get_current_price(access_token, ticker="005930")

        # Test 3: Get daily prices (최근 30일)
        daily_prices = get_daily_prices(access_token, ticker="005930", days=30)

        # Test 4: Test another stock (SK하이닉스)
        print_section("Step 4: Testing Another Stock - SK하이닉스 (000660)")
        current_price_sk = get_current_price(access_token, ticker="000660")

        # Summary
        print("\n" + "=" * 70)
        print("Test Summary")
        print("=" * 70)
        print("✅ Access Token:    PASSED")
        print("✅ Current Price:   PASSED")
        print("✅ Daily Prices:    PASSED")
        print(f"\n📊 Data collected:")
        print(f"   - Stocks tested: 2 (삼성전자, SK하이닉스)")
        print(f"   - Daily records: {len(daily_prices)}")
        print("\n✅ All tests passed! KIS API is working correctly.")

    except Exception as e:
        print("\n" + "=" * 70)
        print("❌ Test failed!")
        print("=" * 70)
        print(f"Error: {str(e)}")
        print("\nPlease check:")
        print("  1. KIS_APP_KEY and KIS_APP_SECRET in .env file")
        print("  2. API credentials are valid and active")
        print("  3. Internet connection")
        sys.exit(1)

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
