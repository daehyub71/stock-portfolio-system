"""KRX (한국거래소) 데이터 수집기.

pykrx 라이브러리를 사용하여 KRX 상장 종목 정보를 수집합니다.
"""

from pykrx import stock
from datetime import datetime, date
from typing import List, Dict, Optional
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from db.connection import SessionLocal
from models import Stock, Sector, MarketType
from loguru import logger


class KRXCollector:
    """KRX 데이터 수집 클래스.

    Features:
    - KOSPI, KOSDAQ, KONEX 상장 종목 리스트 수집
    - 종목 기본 정보 (ticker, name, market) 수집
    - 데이터베이스에 자동 저장
    """

    def __init__(self, db_session=None):
        """Initialize KRXCollector.

        Args:
            db_session: SQLAlchemy session. If None, creates new session.
        """
        self.db = db_session or SessionLocal()
        self._own_session = db_session is None

        # Configure logger
        logger.add(
            "logs/krx_collector_{time}.log",
            rotation="1 day",
            retention="30 days",
            level="INFO"
        )

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self._own_session:
            self.db.close()

    def fetch_stock_list(
        self,
        market: str = "ALL",
        target_date: Optional[str] = None
    ) -> List[Dict]:
        """KRX에서 상장 종목 리스트를 가져옵니다.

        Args:
            market: 시장 구분 ("KOSPI", "KOSDAQ", "KONEX", "ALL")
            target_date: 조회 날짜 (YYYYMMDD). None이면 오늘 날짜 사용.

        Returns:
            List of stock dictionaries with keys: ticker, name, market

        Example:
            >>> collector = KRXCollector()
            >>> stocks = collector.fetch_stock_list(market="KOSPI")
            >>> print(f"Total KOSPI stocks: {len(stocks)}")
        """
        if target_date is None:
            target_date = datetime.now().strftime("%Y%m%d")

        logger.info(f"Fetching stock list from KRX (market={market}, date={target_date})")

        stocks = []

        # Determine which markets to fetch
        markets_to_fetch = []
        if market == "ALL":
            markets_to_fetch = ["KOSPI", "KOSDAQ"]
        else:
            markets_to_fetch = [market]

        # Fetch stocks from each market
        for mkt in markets_to_fetch:
            try:
                tickers = stock.get_market_ticker_list(target_date, market=mkt)
                logger.info(f"Fetched {len(tickers)} stocks from {mkt}")

                for ticker in tickers:
                    try:
                        name = stock.get_market_ticker_name(ticker)

                        stocks.append({
                            "ticker": ticker,
                            "name": name,
                            "market": mkt
                        })
                    except Exception as e:
                        logger.warning(f"Failed to get name for ticker {ticker}: {e}")
                        continue

            except Exception as e:
                logger.error(f"Failed to fetch stocks from {mkt}: {e}")
                continue

        logger.info(f"Total stocks fetched: {len(stocks)}")
        return stocks

    def save_stocks_to_db(
        self,
        stocks: List[Dict],
        sector_name: str = "미분류"
    ) -> int:
        """종목 리스트를 데이터베이스에 저장합니다.

        Args:
            stocks: Stock dictionaries from fetch_stock_list()
            sector_name: Default sector name for stocks without sector

        Returns:
            Number of stocks saved/updated

        Example:
            >>> collector = KRXCollector()
            >>> stocks = collector.fetch_stock_list()
            >>> count = collector.save_stocks_to_db(stocks)
            >>> print(f"Saved {count} stocks")
        """
        logger.info(f"Saving {len(stocks)} stocks to database...")

        # Get or create default sector
        sector = self.db.query(Sector).filter_by(name=sector_name).first()
        if not sector:
            sector = Sector(
                code="UNCLASSIFIED",
                name=sector_name,
                name_en="Unclassified",
                level=1,
                parent_id=None
            )
            self.db.add(sector)
            self.db.commit()
            logger.info(f"Created default sector: {sector_name}")

        saved_count = 0
        updated_count = 0

        for stock_data in stocks:
            try:
                # Check if stock already exists
                existing_stock = self.db.query(Stock).filter_by(
                    ticker=stock_data["ticker"]
                ).first()

                # Map market string to MarketType enum
                market_type = MarketType[stock_data["market"]]

                if existing_stock:
                    # Update existing stock
                    existing_stock.name = stock_data["name"]
                    existing_stock.market = market_type
                    existing_stock.is_active = True
                    updated_count += 1
                else:
                    # Create new stock
                    new_stock = Stock(
                        ticker=stock_data["ticker"],
                        name=stock_data["name"],
                        market=market_type,
                        sector_id=sector.id,
                        is_active=True
                    )
                    self.db.add(new_stock)
                    saved_count += 1

                # Commit every 100 stocks to avoid large transactions
                if (saved_count + updated_count) % 100 == 0:
                    self.db.commit()
                    logger.info(f"Progress: {saved_count + updated_count}/{len(stocks)} stocks processed")

            except Exception as e:
                logger.error(f"Failed to save stock {stock_data['ticker']}: {e}")
                self.db.rollback()
                continue

        # Final commit
        self.db.commit()

        logger.info(f"Database save complete: {saved_count} new, {updated_count} updated")
        return saved_count + updated_count

    def collect_and_save(
        self,
        market: str = "ALL",
        target_date: Optional[str] = None
    ) -> Dict[str, int]:
        """종목 리스트를 수집하고 데이터베이스에 저장합니다 (원스텝 메서드).

        Args:
            market: 시장 구분 ("KOSPI", "KOSDAQ", "KONEX", "ALL")
            target_date: 조회 날짜 (YYYYMMDD)

        Returns:
            Dictionary with collection statistics

        Example:
            >>> collector = KRXCollector()
            >>> result = collector.collect_and_save(market="ALL")
            >>> print(f"Collected: {result['fetched']}, Saved: {result['saved']}")
        """
        logger.info("=" * 70)
        logger.info("Starting KRX stock collection")
        logger.info(f"Market: {market}, Date: {target_date or 'today'}")
        logger.info("=" * 70)

        # Fetch stocks
        stocks = self.fetch_stock_list(market=market, target_date=target_date)

        if not stocks:
            logger.warning("No stocks fetched from KRX")
            return {"fetched": 0, "saved": 0}

        # Save to database
        saved_count = self.save_stocks_to_db(stocks)

        result = {
            "fetched": len(stocks),
            "saved": saved_count,
            "market": market,
            "date": target_date or datetime.now().strftime("%Y%m%d")
        }

        logger.info("=" * 70)
        logger.info("KRX stock collection completed")
        logger.info(f"Results: {result}")
        logger.info("=" * 70)

        return result

    def get_stock_count_by_market(self) -> Dict[str, int]:
        """데이터베이스에 저장된 시장별 종목 수를 반환합니다.

        Returns:
            Dictionary with market counts

        Example:
            >>> collector = KRXCollector()
            >>> counts = collector.get_stock_count_by_market()
            >>> print(f"KOSPI: {counts['KOSPI']}, KOSDAQ: {counts['KOSDAQ']}")
        """
        counts = {}

        for market_type in MarketType:
            count = self.db.query(Stock).filter_by(
                market=market_type,
                is_active=True
            ).count()
            counts[market_type.value] = count

        total = self.db.query(Stock).filter_by(is_active=True).count()
        counts["TOTAL"] = total

        return counts
