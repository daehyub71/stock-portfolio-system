"""KIS (한국투자증권) 주가 데이터 수집기.

KIS Open API를 사용하여 일별 주가 데이터(OHLCV)를 수집합니다.

Features:
- OAuth 2.0 토큰 기반 인증
- Rate limiting (초당 20건 제한)
- 자동 재시도 및 에러 처리
- 배치 수집 지원
"""

import os
import time
import httpx
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from db.connection import SessionLocal
from models import Stock, DailyPrice
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


class KISPriceCollector:
    """KIS API를 통한 주가 데이터 수집 클래스.

    Features:
    - 일별 OHLCV 데이터 수집
    - Rate limiting (초당 20건)
    - 자동 토큰 갱신
    - 배치 처리
    """

    # API Configuration
    KIS_APP_KEY = os.getenv("KIS_APP_KEY")
    KIS_APP_SECRET = os.getenv("KIS_APP_SECRET")
    KIS_ACCOUNT_TYPE = os.getenv("KIS_ACCOUNT_TYPE", "REAL")

    # Rate limiting: KIS API allows 20 requests per second
    MAX_REQUESTS_PER_SECOND = 20
    REQUEST_INTERVAL = 1.0 / MAX_REQUESTS_PER_SECOND  # 0.05 seconds

    def __init__(self, db_session=None):
        """Initialize KISPriceCollector.

        Args:
            db_session: SQLAlchemy session. If None, creates new session.
        """
        self.db = db_session or SessionLocal()
        self._own_session = db_session is None

        # Set base URL based on account type
        if self.KIS_ACCOUNT_TYPE == "VIRTUAL":
            self.base_url = "https://openapivts.koreainvestment.com:29443"
        else:
            self.base_url = "https://openapi.koreainvestment.com:9443"

        # API endpoints
        self.token_url = f"{self.base_url}/oauth2/tokenP"
        self.daily_price_url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-price"

        # Access token cache
        self._access_token = None
        self._token_expires_at = None

        # Rate limiting
        self._last_request_time = 0

        # Configure logger
        logger.add(
            "logs/kis_collector_{time}.log",
            rotation="1 day",
            retention="30 days",
            level="INFO"
        )

        logger.info(f"KISPriceCollector initialized (Account type: {self.KIS_ACCOUNT_TYPE})")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self._own_session:
            self.db.close()

    def _rate_limit(self):
        """Rate limiting: Ensure we don't exceed API limits."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.REQUEST_INTERVAL:
            time.sleep(self.REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def get_access_token(self, force_refresh: bool = False) -> str:
        """Get or refresh access token.

        Args:
            force_refresh: Force token refresh even if not expired

        Returns:
            Access token string

        Raises:
            Exception if token request fails
        """
        # Return cached token if still valid
        if (
            not force_refresh
            and self._access_token
            and self._token_expires_at
            and datetime.now() < self._token_expires_at
        ):
            return self._access_token

        logger.info("Requesting new access token from KIS API")

        headers = {"content-type": "application/json"}
        data = {
            "grant_type": "client_credentials",
            "appkey": self.KIS_APP_KEY,
            "appsecret": self.KIS_APP_SECRET
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(self.token_url, headers=headers, json=data)
                response.raise_for_status()

                result = response.json()

                if "access_token" in result:
                    self._access_token = result["access_token"]
                    expires_in = int(result.get("expires_in", 86400))  # Default 24 hours
                    self._token_expires_at = datetime.now() + timedelta(seconds=expires_in - 300)  # 5 min buffer

                    logger.info(f"Access token received (expires in {expires_in}s)")
                    return self._access_token
                else:
                    error_msg = result.get("msg1", "Unknown error")
                    logger.error(f"Failed to get access token: {error_msg}")
                    raise Exception(f"Token request failed: {error_msg}")

        except httpx.HTTPError as e:
            logger.error(f"HTTP error during token request: {e}")
            raise
        except Exception as e:
            logger.error(f"Error getting access token: {e}")
            raise

    def fetch_daily_prices(
        self,
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        days: int = 100
    ) -> List[Dict]:
        """특정 종목의 일별 주가 데이터를 가져옵니다.

        Args:
            ticker: 종목코드 (e.g., "005930")
            start_date: 시작일 (YYYYMMDD). None이면 days 파라미터 사용
            end_date: 종료일 (YYYYMMDD). None이면 오늘
            days: start_date가 None일 때 조회할 일수

        Returns:
            List of daily price dictionaries

        Example:
            >>> collector = KISPriceCollector()
            >>> prices = collector.fetch_daily_prices("005930", days=30)
        """
        # Apply rate limiting
        self._rate_limit()

        # Get access token
        access_token = self.get_access_token()

        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {access_token}",
            "appkey": self.KIS_APP_KEY,
            "appsecret": self.KIS_APP_SECRET,
            "tr_id": "FHKST01010400"  # 주식현재가 일자별
        }

        params = {
            "fid_cond_mrkt_div_code": "J",  # 주식
            "fid_input_iscd": ticker,
            "fid_period_div_code": "D",  # 일봉
            "fid_org_adj_prc": "0",  # 수정주가 미반영
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(self.daily_price_url, headers=headers, params=params)
                response.raise_for_status()

                result = response.json()

                if result.get("rt_cd") == "0":  # Success
                    raw_data = result.get("output", [])

                    # Convert to our format
                    prices = []
                    for record in raw_data[:days]:  # Limit to requested days
                        date_str = record.get('stck_bsop_date', '')
                        if not date_str:
                            continue

                        try:
                            prices.append({
                                "ticker": ticker,
                                "date": datetime.strptime(date_str, "%Y%m%d").date(),
                                "open_price": float(record.get('stck_oprc', 0)),
                                "high_price": float(record.get('stck_hgpr', 0)),
                                "low_price": float(record.get('stck_lwpr', 0)),
                                "close_price": float(record.get('stck_clpr', 0)),
                                "volume": int(record.get('acml_vol', 0)),
                                "change_amount": float(record.get('prdy_vrss', 0)),
                                "change_rate": float(record.get('prdy_ctrt', 0)),
                            })
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Failed to parse price record for {ticker}: {e}")
                            continue

                    logger.info(f"Fetched {len(prices)} daily prices for {ticker}")
                    return prices

                else:
                    error_msg = result.get("msg1", "Unknown error")
                    logger.error(f"API error for {ticker}: {error_msg}")
                    return []

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching prices for {ticker}: {e}")
            return []
        except Exception as e:
            logger.error(f"Error fetching prices for {ticker}: {e}")
            return []

    def save_daily_prices(self, prices: List[Dict]) -> int:
        """일별 주가 데이터를 데이터베이스에 저장합니다.

        Args:
            prices: Price dictionaries from fetch_daily_prices()

        Returns:
            Number of records saved/updated

        Example:
            >>> collector = KISPriceCollector()
            >>> prices = collector.fetch_daily_prices("005930")
            >>> count = collector.save_daily_prices(prices)
        """
        if not prices:
            return 0

        saved_count = 0
        updated_count = 0

        for price_data in prices:
            try:
                # Get stock_id from ticker
                stock = self.db.query(Stock).filter_by(
                    ticker=price_data["ticker"]
                ).first()

                if not stock:
                    logger.warning(f"Stock not found: {price_data['ticker']}")
                    continue

                # Check if price record already exists
                existing_price = self.db.query(DailyPrice).filter_by(
                    stock_id=stock.id,
                    date=price_data["date"]
                ).first()

                if existing_price:
                    # Update existing record
                    existing_price.open_price = price_data["open_price"]
                    existing_price.high_price = price_data["high_price"]
                    existing_price.low_price = price_data["low_price"]
                    existing_price.close_price = price_data["close_price"]
                    existing_price.volume = price_data["volume"]
                    existing_price.change_amount = price_data.get("change_amount")
                    existing_price.change_rate = price_data.get("change_rate")
                    updated_count += 1
                else:
                    # Create new record
                    new_price = DailyPrice(
                        stock_id=stock.id,
                        date=price_data["date"],
                        open_price=price_data["open_price"],
                        high_price=price_data["high_price"],
                        low_price=price_data["low_price"],
                        close_price=price_data["close_price"],
                        volume=price_data["volume"],
                        change_amount=price_data.get("change_amount"),
                        change_rate=price_data.get("change_rate"),
                    )
                    self.db.add(new_price)
                    saved_count += 1

                # Commit every 50 records
                if (saved_count + updated_count) % 50 == 0:
                    self.db.commit()

            except Exception as e:
                logger.error(f"Failed to save price data: {e}")
                self.db.rollback()
                continue

        # Final commit
        self.db.commit()

        logger.info(f"Saved {saved_count} new, updated {updated_count} price records")
        return saved_count + updated_count

    def collect_and_save(
        self,
        ticker: str,
        days: int = 100
    ) -> Dict[str, int]:
        """종목의 주가 데이터를 수집하고 저장합니다 (원스텝).

        Args:
            ticker: 종목코드
            days: 조회할 일수

        Returns:
            Dictionary with collection statistics
        """
        logger.info(f"Starting price collection for {ticker} ({days} days)")

        # Fetch prices
        prices = self.fetch_daily_prices(ticker, days=days)

        if not prices:
            logger.warning(f"No prices fetched for {ticker}")
            return {"fetched": 0, "saved": 0, "ticker": ticker}

        # Save to database
        saved_count = self.save_daily_prices(prices)

        result = {
            "fetched": len(prices),
            "saved": saved_count,
            "ticker": ticker
        }

        logger.info(f"Collection complete for {ticker}: {result}")
        return result

    def collect_batch(
        self,
        tickers: List[str],
        days: int = 100
    ) -> Dict:
        """여러 종목의 주가 데이터를 배치로 수집합니다.

        Args:
            tickers: 종목코드 리스트
            days: 각 종목당 조회할 일수

        Returns:
            Dictionary with batch statistics

        Example:
            >>> collector = KISPriceCollector()
            >>> result = collector.collect_batch(["005930", "000660"], days=30)
        """
        logger.info(f"Starting batch collection for {len(tickers)} stocks")

        total_fetched = 0
        total_saved = 0
        success_count = 0
        failed_tickers = []

        for i, ticker in enumerate(tickers, 1):
            logger.info(f"Progress: {i}/{len(tickers)} - {ticker}")

            try:
                result = self.collect_and_save(ticker, days=days)
                total_fetched += result["fetched"]
                total_saved += result["saved"]

                if result["fetched"] > 0:
                    success_count += 1
                else:
                    failed_tickers.append(ticker)

            except Exception as e:
                logger.error(f"Failed to collect {ticker}: {e}")
                failed_tickers.append(ticker)
                continue

        summary = {
            "total_stocks": len(tickers),
            "success_count": success_count,
            "failed_count": len(failed_tickers),
            "failed_tickers": failed_tickers,
            "total_fetched": total_fetched,
            "total_saved": total_saved
        }

        logger.info(f"Batch collection complete: {summary}")
        return summary
