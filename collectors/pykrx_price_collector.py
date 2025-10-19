"""pykrx 기반 주가 데이터 수집기.

pykrx를 사용하여 KRX 공개 데이터에서 일별 주가 데이터(OHLCV)를 수집합니다.

Features:
- 인증 불필요 (공개 데이터)
- Rate limiting 없음
- 장기간 데이터 수집 가능 (10년+)
- KOSPI, KOSDAQ 전체 종목 지원
"""

import time
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pykrx import stock
import pandas as pd
from db.connection import SessionLocal
from models import Stock, DailyPrice
from loguru import logger

# Configure logger
logger.add(
    "logs/pykrx_collector_{time}.log",
    rotation="1 day",
    retention="30 days",
    level="INFO"
)


class PyKRXPriceCollector:
    """pykrx를 통한 주가 데이터 수집 클래스.

    Features:
    - 일별 OHLCV 데이터 수집
    - 장기간 데이터 수집 (10년+)
    - No authentication required
    - No rate limiting
    """

    def __init__(self, db_session=None):
        """Initialize PyKRXPriceCollector.

        Args:
            db_session: SQLAlchemy session. If None, creates new session.
        """
        self.db = db_session or SessionLocal()
        self._own_session = db_session is None

        logger.info("PyKRXPriceCollector initialized")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self._own_session:
            self.db.close()

    def fetch_daily_prices(
        self,
        ticker: str,
        start_date: date,
        end_date: date
    ) -> List[Dict]:
        """특정 종목의 일별 주가 데이터를 가져옵니다.

        Args:
            ticker: 종목코드 (e.g., "005930")
            start_date: 시작일 (date object)
            end_date: 종료일 (date object)

        Returns:
            List of daily price dictionaries

        Example:
            >>> from datetime import date
            >>> collector = PyKRXPriceCollector()
            >>> prices = collector.fetch_daily_prices(
            ...     "005930",
            ...     date(2024, 1, 1),
            ...     date(2024, 12, 31)
            ... )
        """
        try:
            # Convert dates to string format (YYYYMMDD)
            start_str = start_date.strftime("%Y%m%d")
            end_str = end_date.strftime("%Y%m%d")

            # Get OHLCV data from pykrx
            df = stock.get_market_ohlcv(start_str, end_str, ticker)

            if df is None or df.empty:
                logger.warning(f"No data available for {ticker}")
                return []

            # Convert DataFrame to list of dictionaries
            prices = []
            for date_idx, row in df.iterrows():
                try:
                    # pykrx column names are in Korean
                    # '시가', '고가', '저가', '종가', '거래량', '등락률'
                    prices.append({
                        "ticker": ticker,
                        "date": date_idx.date() if isinstance(date_idx, pd.Timestamp) else date_idx,
                        "open_price": float(row['시가']),
                        "high_price": float(row['고가']),
                        "low_price": float(row['저가']),
                        "close_price": float(row['종가']),
                        "volume": int(row['거래량']),
                        "change_rate": float(row.get('등락률', 0.0)) if '등락률' in row else None,
                    })
                except (ValueError, TypeError, KeyError) as e:
                    logger.warning(f"Failed to parse price record for {ticker} on {date_idx}: {e}")
                    continue

            logger.info(f"Fetched {len(prices)} daily prices for {ticker} ({start_date} ~ {end_date})")
            return prices

        except Exception as e:
            logger.error(f"Error fetching prices for {ticker}: {e}")
            return []

    def save_daily_prices(self, prices: List[Dict]) -> Dict[str, int]:
        """일별 주가 데이터를 데이터베이스에 저장합니다.

        Args:
            prices: Price dictionaries from fetch_daily_prices()

        Returns:
            Dictionary with saved_count and updated_count

        Example:
            >>> collector = PyKRXPriceCollector()
            >>> prices = collector.fetch_daily_prices("005930", ...)
            >>> result = collector.save_daily_prices(prices)
        """
        if not prices:
            return {"saved": 0, "updated": 0}

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
        return {"saved": saved_count, "updated": updated_count}

    def collect_and_save(
        self,
        ticker: str,
        start_date: date,
        end_date: date
    ) -> Dict:
        """종목의 주가 데이터를 수집하고 저장합니다 (원스텝).

        Args:
            ticker: 종목코드
            start_date: 시작일
            end_date: 종료일

        Returns:
            Dictionary with collection statistics including 'success' boolean
        """
        logger.info(f"Starting price collection for {ticker} ({start_date} ~ {end_date})")

        # Fetch prices
        prices = self.fetch_daily_prices(ticker, start_date, end_date)

        if not prices:
            logger.warning(f"No prices fetched for {ticker}")
            return {
                "success": False,
                "fetched": 0,
                "saved": 0,
                "ticker": ticker
            }

        # Save to database
        result = self.save_daily_prices(prices)

        final_result = {
            "success": True,
            "fetched": len(prices),
            "saved": result["saved"],
            "updated": result["updated"],
            "ticker": ticker
        }

        logger.info(f"Collection complete for {ticker}: {final_result}")
        return final_result

    def collect_batch(
        self,
        tickers: List[str],
        start_date: date,
        end_date: date,
        delay: float = 0.1
    ) -> Dict:
        """여러 종목의 주가 데이터를 배치로 수집합니다.

        Args:
            tickers: 종목코드 리스트
            start_date: 시작일
            end_date: 종료일
            delay: 종목 간 대기 시간 (초, 기본값: 0.1)

        Returns:
            Dictionary with batch statistics

        Example:
            >>> from datetime import date
            >>> collector = PyKRXPriceCollector()
            >>> result = collector.collect_batch(
            ...     ["005930", "000660"],
            ...     date(2024, 1, 1),
            ...     date(2024, 12, 31)
            ... )
        """
        logger.info(f"Starting batch collection for {len(tickers)} stocks ({start_date} ~ {end_date})")

        total_fetched = 0
        total_saved = 0
        success_count = 0
        failed_tickers = []

        for i, ticker in enumerate(tickers, 1):
            logger.info(f"Progress: {i}/{len(tickers)} - {ticker}")

            try:
                result = self.collect_and_save(ticker, start_date, end_date)
                total_fetched += result["fetched"]
                total_saved += result["saved"]

                if result["success"]:
                    success_count += 1
                else:
                    failed_tickers.append(ticker)

                # Brief delay between requests (optional, pykrx doesn't require this)
                if i < len(tickers):
                    time.sleep(delay)

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
