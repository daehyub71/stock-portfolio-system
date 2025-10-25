#!/usr/bin/env python3
"""일일 시세 업데이트 스크립트.

전일(T-1) 주가 데이터만 수집하여 데이터베이스를 업데이트합니다.
매일 자동 실행을 위한 증분 업데이트 스크립트입니다.

Features:
- 전일 데이터만 수집 (빠른 업데이트)
- pykrx 사용 (인증 불필요, rate limit 없음)
- 자동 시장 휴장일 처리
- 실패 재시도 로직

Usage:
    # 전일 데이터 업데이트 (기본)
    python scripts/update_daily_prices.py

    # 특정 날짜 업데이트
    python scripts/update_daily_prices.py --date 20250123

    # 최근 N일 업데이트
    python scripts/update_daily_prices.py --days 5

    # 특정 시장만 업데이트
    python scripts/update_daily_prices.py --market KOSPI

Performance Target:
    - 전체 종목(~2,700개) 업데이트: 30분 이내
    - 평균 처리 속도: ~1.5개/초
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta, date
from typing import List, Dict, Optional
import time

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
from collectors.pykrx_price_collector import PyKRXPriceCollector
from db.connection import SessionLocal
from models import Stock, DailyPrice, MarketType
from sqlalchemy import func

# Configure logger
log_dir = project_root / 'logs'
log_dir.mkdir(exist_ok=True)

logger.remove()  # Remove default handler
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    level="INFO"
)
logger.add(
    log_dir / "update_daily_prices_{time:YYYY-MM-DD}.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    rotation="100 MB",
    retention="30 days",
    level="INFO"
)


class DailyPriceUpdater:
    """일일 시세 업데이트 클래스."""

    def __init__(
        self,
        target_date: Optional[date] = None,
        days: int = 1,
        market: Optional[str] = None,
        retry_failed: bool = True
    ):
        """Initialize daily price updater.

        Args:
            target_date: Target date to update. If None, uses yesterday (T-1)
            days: Number of recent days to update (default: 1)
            market: Market filter (KOSPI, KOSDAQ, or None for all)
            retry_failed: Whether to retry failed stocks
        """
        self.db = SessionLocal()
        self.collector = PyKRXPriceCollector(db_session=self.db)

        # Calculate date range
        if target_date:
            self.end_date = target_date
        else:
            # Default: yesterday (T-1)
            self.end_date = date.today() - timedelta(days=1)

        self.start_date = self.end_date - timedelta(days=days - 1)
        self.market = market

        # Get stock list
        self.stocks = self._get_stocks()
        self.retry_failed = retry_failed

        # Statistics
        self.stats = {
            'start_time': datetime.now(),
            'end_time': None,
            'total_stocks': len(self.stocks),
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'total_records': 0,
            'failed_stocks': []
        }

        logger.info(f"DailyPriceUpdater initialized")
        logger.info(f"  Date range: {self.start_date} ~ {self.end_date}")
        logger.info(f"  Market: {self.market or 'ALL'}")
        logger.info(f"  Total stocks: {len(self.stocks)}")

    def _get_stocks(self) -> List[Stock]:
        """Get list of stocks to update.

        Returns:
            List of Stock objects
        """
        query = self.db.query(Stock)

        # Filter by market if specified
        if self.market:
            market_type = MarketType[self.market.upper()]
            query = query.filter(Stock.market == market_type)

        # Only active stocks (not delisted)
        query = query.filter(
            (Stock.delisting_date == None) | (Stock.delisting_date > self.end_date)
        )

        stocks = query.order_by(Stock.ticker).all()
        return stocks

    def _check_existing_data(self, stock_id: int, check_date: date) -> bool:
        """Check if price data already exists for given date.

        Args:
            stock_id: Stock ID
            check_date: Date to check

        Returns:
            True if data exists, False otherwise
        """
        existing = self.db.query(DailyPrice).filter(
            DailyPrice.stock_id == stock_id,
            DailyPrice.date == check_date
        ).first()

        return existing is not None

    def update_stock(self, stock: Stock) -> Dict:
        """Update price data for a single stock.

        Args:
            stock: Stock object

        Returns:
            Result dictionary with success status and statistics
        """
        ticker = stock.ticker
        name = stock.name

        try:
            # Check if data already exists
            if self._check_existing_data(stock.id, self.end_date):
                logger.debug(f"  ⏭️  {ticker} ({name}): Data already exists for {self.end_date}")
                return {
                    'success': True,
                    'skipped': True,
                    'records': 0
                }

            # Fetch and save price data
            result = self.collector.collect_and_save(
                ticker=ticker,
                start_date=self.start_date,
                end_date=self.end_date
            )

            if result['success']:
                saved = result.get('saved', 0)
                updated = result.get('updated', 0)
                total = saved + updated

                if total > 0:
                    logger.info(f"  ✅ {ticker} ({name}): {total} records (new: {saved}, updated: {updated})")
                else:
                    logger.warning(f"  ⚠️  {ticker} ({name}): No data (possibly market holiday)")

                return {
                    'success': True,
                    'skipped': False,
                    'records': total
                }
            else:
                logger.warning(f"  ⚠️  {ticker} ({name}): No data available")
                return {
                    'success': False,
                    'skipped': False,
                    'records': 0
                }

        except Exception as e:
            logger.error(f"  ❌ {ticker} ({name}): {str(e)}")
            return {
                'success': False,
                'skipped': False,
                'records': 0,
                'error': str(e)
            }

    def update_all(self):
        """Update price data for all stocks."""
        logger.info("=" * 80)
        logger.info("일일 시세 업데이트 시작")
        logger.info("=" * 80)
        logger.info(f"업데이트 기간: {self.start_date} ~ {self.end_date}")
        logger.info(f"시장: {self.market or 'ALL'}")
        logger.info(f"총 종목 수: {self.stats['total_stocks']}")
        logger.info("=" * 80)

        # Process each stock
        for i, stock in enumerate(self.stocks, 1):
            ticker = stock.ticker
            name = stock.name

            logger.info(f"[{i}/{self.stats['total_stocks']}] Processing {ticker} ({name})...")

            # Update stock
            result = self.update_stock(stock)

            # Update statistics
            if result.get('skipped'):
                self.stats['skipped'] += 1
            elif result['success']:
                self.stats['success'] += 1
                self.stats['total_records'] += result['records']
            else:
                self.stats['failed'] += 1
                self.stats['failed_stocks'].append({
                    'ticker': ticker,
                    'name': name,
                    'error': result.get('error', 'Unknown error')
                })

            # Progress report every 100 stocks
            if i % 100 == 0:
                self._print_progress(i)

            # Small delay to be nice to the server
            time.sleep(0.05)

        self.stats['end_time'] = datetime.now()

        # Retry failed stocks if enabled
        if self.retry_failed and self.stats['failed'] > 0:
            logger.info("")
            logger.info("=" * 80)
            logger.info(f"재시도: {self.stats['failed']}개 실패 종목")
            logger.info("=" * 80)
            self._retry_failed_stocks()

        # Print final summary
        self._print_summary()

    def _retry_failed_stocks(self):
        """Retry failed stocks once."""
        failed_stocks = self.stats['failed_stocks'].copy()
        self.stats['failed_stocks'] = []

        retry_success = 0
        retry_failed = 0

        for i, failed_stock in enumerate(failed_stocks, 1):
            ticker = failed_stock['ticker']
            name = failed_stock['name']

            logger.info(f"[Retry {i}/{len(failed_stocks)}] {ticker} ({name})...")

            # Find stock object
            stock = self.db.query(Stock).filter_by(ticker=ticker).first()
            if not stock:
                logger.error(f"  ❌ Stock not found: {ticker}")
                retry_failed += 1
                continue

            # Wait a bit longer before retry
            time.sleep(0.5)

            # Retry update
            result = self.update_stock(stock)

            if result['success']:
                retry_success += 1
                self.stats['success'] += 1
                self.stats['failed'] -= 1
                self.stats['total_records'] += result['records']
            else:
                retry_failed += 1
                self.stats['failed_stocks'].append(failed_stock)

        logger.info("")
        logger.info(f"재시도 완료: 성공 {retry_success}, 실패 {retry_failed}")

    def _print_progress(self, current: int):
        """Print progress update.

        Args:
            current: Current stock index
        """
        elapsed = (datetime.now() - self.stats['start_time']).total_seconds()
        rate = current / elapsed if elapsed > 0 else 0
        remaining = (self.stats['total_stocks'] - current) / rate if rate > 0 else 0

        logger.info("")
        logger.info("─" * 80)
        logger.info(f"진행 상황: {current}/{self.stats['total_stocks']} ({current/self.stats['total_stocks']*100:.1f}%)")
        logger.info(f"성공: {self.stats['success']} | 실패: {self.stats['failed']} | 건너뛰기: {self.stats['skipped']}")
        logger.info(f"총 레코드: {self.stats['total_records']:,}개")
        logger.info(f"처리 속도: {rate:.2f}개/초 | 예상 남은 시간: {int(remaining/60)}분 {int(remaining%60)}초")
        logger.info("─" * 80)
        logger.info("")

    def _print_summary(self):
        """Print final summary."""
        elapsed = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
        elapsed_minutes = elapsed / 60

        logger.info("")
        logger.info("=" * 80)
        logger.info("일일 시세 업데이트 완료")
        logger.info("=" * 80)
        logger.info(f"업데이트 기간: {self.start_date} ~ {self.end_date}")
        logger.info(f"총 종목 수: {self.stats['total_stocks']}")
        logger.info(f"성공: {self.stats['success']}")
        logger.info(f"실패: {self.stats['failed']}")
        logger.info(f"건너뛰기: {self.stats['skipped']}")
        logger.info(f"총 레코드: {self.stats['total_records']:,}개")
        logger.info("")
        logger.info(f"소요 시간: {elapsed_minutes:.1f}분 ({int(elapsed)}초)")
        logger.info(f"처리 속도: {self.stats['total_stocks']/elapsed:.2f}개/초")

        if self.stats['total_stocks'] > 0:
            success_rate = self.stats['success'] / self.stats['total_stocks'] * 100
            logger.info(f"성공률: {success_rate:.1f}%")

        # Performance check
        if elapsed_minutes <= 30:
            logger.info(f"✅ 성능 목표 달성: {elapsed_minutes:.1f}분 <= 30분")
        else:
            logger.warning(f"⚠️  성능 목표 미달: {elapsed_minutes:.1f}분 > 30분")

        logger.info("=" * 80)

        # Print failed stocks if any
        if self.stats['failed_stocks']:
            logger.info("")
            logger.info(f"❌ 실패한 종목 ({len(self.stats['failed_stocks'])}):")
            for stock in self.stats['failed_stocks'][:10]:  # Show first 10
                logger.info(f"  - {stock['ticker']} ({stock['name']}): {stock['error']}")
            if len(self.stats['failed_stocks']) > 10:
                logger.info(f"  ... 외 {len(self.stats['failed_stocks']) - 10}개")

    def close(self):
        """Close database connection."""
        self.db.close()


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='일일 시세 데이터 업데이트 (전일 데이터만 수집)'
    )

    parser.add_argument(
        '--date',
        type=str,
        help='업데이트할 날짜 (YYYYMMDD 형식). 미지정시 전일(T-1)'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=1,
        help='최근 N일 업데이트 (기본값: 1일)'
    )
    parser.add_argument(
        '--market',
        type=str,
        choices=['KOSPI', 'KOSDAQ', 'KONEX'],
        help='특정 시장만 업데이트'
    )
    parser.add_argument(
        '--no-retry',
        action='store_true',
        help='실패한 종목 재시도 안함'
    )

    args = parser.parse_args()

    # Parse target date
    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y%m%d").date()
        except ValueError:
            logger.error(f"❌ Invalid date format: {args.date}. Use YYYYMMDD format.")
            sys.exit(1)

    try:
        updater = DailyPriceUpdater(
            target_date=target_date,
            days=args.days,
            market=args.market,
            retry_failed=not args.no_retry
        )

        updater.update_all()

    except KeyboardInterrupt:
        logger.warning("\n⚠️  사용자에 의해 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if 'updater' in locals():
            updater.close()


if __name__ == '__main__':
    main()
