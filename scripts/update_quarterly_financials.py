#!/usr/bin/env python3
"""분기 재무제표 업데이트 스크립트.

최신 분기 재무제표만 수집하여 데이터베이스를 업데이트합니다.
매 분기 실적 발표 후 자동 실행을 위한 증분 업데이트 스크립트입니다.

Features:
- 최신 분기 재무제표만 수집 (빠른 업데이트)
- DART API 사용 (분기보고서 수집)
- 자동 분기 판단 (현재 월 기준)
- 실패 재시도 로직
- 재무비율 자동 재계산 트리거

Usage:
    # 최신 분기 재무제표 업데이트 (기본)
    python scripts/update_quarterly_financials.py

    # 특정 분기 업데이트
    python scripts/update_quarterly_financials.py --year 2024 --quarter 3

    # 재무비율 재계산 생략
    python scripts/update_quarterly_financials.py --skip-ratios

    # 특정 시장만 업데이트
    python scripts/update_quarterly_financials.py --market KOSPI

Performance Target:
    - 전체 종목(~2,700개) 업데이트: 2시간 이내
    - DART API rate limit: 5 req/sec
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple
import time

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
from collectors.dart_collector import DARTCollector
from db.connection import SessionLocal
from models import Stock, FinancialStatement, StatementType, MarketType
from sqlalchemy import func, and_, or_

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
    log_dir / "update_quarterly_financials_{time:YYYY-MM-DD}.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    rotation="100 MB",
    retention="30 days",
    level="INFO"
)


class QuarterlyFinancialUpdater:
    """분기 재무제표 업데이트 클래스."""

    # DART report codes
    REPORT_CODES = {
        1: "11013",  # 1분기보고서
        2: "11012",  # 반기보고서 (2분기)
        3: "11014",  # 3분기보고서
        4: "11011",  # 사업보고서 (연간, 4분기)
    }

    def __init__(
        self,
        year: Optional[int] = None,
        quarter: Optional[int] = None,
        market: Optional[str] = None,
        skip_ratios: bool = False,
        retry_failed: bool = True
    ):
        """Initialize quarterly financial updater.

        Args:
            year: Target year. If None, uses current year
            quarter: Target quarter (1-4). If None, auto-detects
            market: Market filter (KOSPI, KOSDAQ, or None for all)
            skip_ratios: Skip financial ratio recalculation
            retry_failed: Whether to retry failed stocks
        """
        self.db = SessionLocal()
        self.collector = DARTCollector(db_session=self.db)

        # Determine target quarter
        if year and quarter:
            self.year = year
            self.quarter = quarter
        else:
            self.year, self.quarter = self._detect_latest_quarter()

        self.market = market
        self.skip_ratios = skip_ratios
        self.retry_failed = retry_failed

        # Get report code for quarter
        self.report_code = self.REPORT_CODES[self.quarter]

        # Get stock list
        self.stocks = self._get_stocks()

        # Statistics
        self.stats = {
            'start_time': datetime.now(),
            'end_time': None,
            'total_stocks': len(self.stocks),
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'updated': 0,
            'failed_stocks': []
        }

        logger.info(f"QuarterlyFinancialUpdater initialized")
        logger.info(f"  Target: {self.year}Q{self.quarter}")
        logger.info(f"  Report code: {self.report_code}")
        logger.info(f"  Market: {self.market or 'ALL'}")
        logger.info(f"  Total stocks: {len(self.stocks)}")
        logger.info(f"  Skip ratios: {self.skip_ratios}")

    def _detect_latest_quarter(self) -> Tuple[int, int]:
        """Detect the latest quarter based on current date.

        Returns:
            Tuple of (year, quarter)

        Note:
            - Q1: Jan-Mar (data available ~May)
            - Q2: Apr-Jun (data available ~Aug)
            - Q3: Jul-Sep (data available ~Nov)
            - Q4: Oct-Dec (data available ~Mar next year)
        """
        today = date.today()
        current_month = today.month
        current_year = today.year

        # Quarter detection with reporting lag (~2 months)
        if current_month <= 4:
            # Jan-Apr: Previous year Q4
            return current_year - 1, 4
        elif current_month <= 7:
            # May-Jul: Current year Q1
            return current_year, 1
        elif current_month <= 10:
            # Aug-Oct: Current year Q2
            return current_year, 2
        else:
            # Nov-Dec: Current year Q3
            return current_year, 3

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
            (Stock.delisting_date == None) |
            (Stock.delisting_date > date(self.year, self.quarter * 3, 1))
        )

        stocks = query.order_by(Stock.ticker).all()
        return stocks

    def _check_existing_data(self, stock_id: int) -> bool:
        """Check if financial statement already exists for target quarter.

        Args:
            stock_id: Stock ID

        Returns:
            True if data exists, False otherwise
        """
        existing = self.db.query(FinancialStatement).filter(
            and_(
                FinancialStatement.stock_id == stock_id,
                FinancialStatement.fiscal_year == self.year,
                FinancialStatement.fiscal_quarter == self.quarter
            )
        ).first()

        return existing is not None

    def update_stock(self, stock: Stock) -> Dict:
        """Update financial statement for a single stock.

        Args:
            stock: Stock object

        Returns:
            Result dictionary with success status
        """
        ticker = stock.ticker
        name = stock.name

        try:
            # Check if data already exists
            if self._check_existing_data(stock.id):
                logger.debug(f"  ⏭️  {ticker} ({name}): Data already exists for {self.year}Q{self.quarter}")
                return {
                    'success': True,
                    'skipped': True,
                    'updated': False
                }

            # Collect financial statement using DART API
            result = self.collector.collect_and_save(
                ticker=ticker,
                years=[self.year],
                quarters=[self.quarter]
            )

            if result.get('saved', 0) > 0:
                logger.info(f"  ✅ {ticker} ({name}): Saved {result['saved']} statements")
                return {
                    'success': True,
                    'skipped': False,
                    'updated': True
                }
            elif result.get('fetched', 0) > 0:
                logger.info(f"  🔄 {ticker} ({name}): Updated existing data")
                return {
                    'success': True,
                    'skipped': False,
                    'updated': True
                }
            else:
                logger.warning(f"  ⚠️  {ticker} ({name}): No data available")
                return {
                    'success': False,
                    'skipped': False,
                    'updated': False
                }

        except Exception as e:
            logger.error(f"  ❌ {ticker} ({name}): {str(e)}")
            return {
                'success': False,
                'skipped': False,
                'updated': False,
                'error': str(e)
            }

    def update_all(self):
        """Update financial statements for all stocks."""
        logger.info("=" * 80)
        logger.info("분기 재무제표 업데이트 시작")
        logger.info("=" * 80)
        logger.info(f"대상 분기: {self.year}Q{self.quarter}")
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
                if result.get('updated'):
                    self.stats['updated'] += 1
            else:
                self.stats['failed'] += 1
                self.stats['failed_stocks'].append({
                    'ticker': ticker,
                    'name': name,
                    'error': result.get('error', 'Unknown error')
                })

            # Progress report every 50 stocks
            if i % 50 == 0:
                self._print_progress(i)

            # DART API rate limiting: ~5 req/sec
            time.sleep(0.25)

        self.stats['end_time'] = datetime.now()

        # Retry failed stocks if enabled
        if self.retry_failed and self.stats['failed'] > 0:
            logger.info("")
            logger.info("=" * 80)
            logger.info(f"재시도: {self.stats['failed']}개 실패 종목")
            logger.info("=" * 80)
            self._retry_failed_stocks()

        # Recalculate financial ratios if enabled
        if not self.skip_ratios and self.stats['updated'] > 0:
            logger.info("")
            logger.info("=" * 80)
            logger.info("재무비율 재계산 시작")
            logger.info("=" * 80)
            self._recalculate_ratios()

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

            # Wait longer before retry
            time.sleep(1.0)

            # Retry update
            result = self.update_stock(stock)

            if result['success']:
                retry_success += 1
                self.stats['success'] += 1
                self.stats['failed'] -= 1
                if result.get('updated'):
                    self.stats['updated'] += 1
            else:
                retry_failed += 1
                self.stats['failed_stocks'].append(failed_stock)

        logger.info("")
        logger.info(f"재시도 완료: 성공 {retry_success}, 실패 {retry_failed}")

    def _recalculate_ratios(self):
        """Recalculate financial ratios for updated stocks.

        Note:
            This triggers the financial ratio calculator for all stocks
            that received new financial data in this update.
        """
        logger.info(f"재계산 대상: {self.stats['updated']}개 종목")

        # Import calculator here to avoid circular imports
        try:
            from calculators.financial_ratio_calculator import FinancialRatioCalculator

            calculator = FinancialRatioCalculator(db_session=self.db)

            # Get stocks that were updated
            updated_stock_ids = []
            for stock in self.stocks:
                if self._check_existing_data(stock.id):
                    updated_stock_ids.append(stock.id)

            if not updated_stock_ids:
                logger.warning("재계산할 종목이 없습니다.")
                return

            # Calculate ratios for each stock
            success_count = 0
            failed_count = 0

            for i, stock_id in enumerate(updated_stock_ids, 1):
                stock = self.db.query(Stock).get(stock_id)
                if not stock:
                    continue

                try:
                    # Calculate ratios for the updated quarter
                    calculator.calculate_and_save(
                        stock_id=stock_id,
                        fiscal_year=self.year,
                        fiscal_quarter=self.quarter
                    )
                    success_count += 1

                    if i % 50 == 0:
                        logger.info(f"  진행: {i}/{len(updated_stock_ids)} ({i/len(updated_stock_ids)*100:.1f}%)")

                except Exception as e:
                    logger.error(f"  ❌ {stock.ticker}: Failed to calculate ratios - {str(e)}")
                    failed_count += 1

            logger.info(f"재무비율 재계산 완료: 성공 {success_count}, 실패 {failed_count}")

        except ImportError:
            logger.warning("⚠️  FinancialRatioCalculator not found - skipping ratio recalculation")
            logger.info("재무비율 계산기를 구현한 후 다시 실행하세요.")

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
        logger.info(f"업데이트됨: {self.stats['updated']}개")
        logger.info(f"처리 속도: {rate:.2f}개/초 | 예상 남은 시간: {int(remaining/60)}분")
        logger.info("─" * 80)
        logger.info("")

    def _print_summary(self):
        """Print final summary."""
        elapsed = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
        elapsed_hours = elapsed / 3600
        elapsed_minutes = elapsed / 60

        logger.info("")
        logger.info("=" * 80)
        logger.info("분기 재무제표 업데이트 완료")
        logger.info("=" * 80)
        logger.info(f"대상 분기: {self.year}Q{self.quarter}")
        logger.info(f"총 종목 수: {self.stats['total_stocks']}")
        logger.info(f"성공: {self.stats['success']}")
        logger.info(f"실패: {self.stats['failed']}")
        logger.info(f"건너뛰기: {self.stats['skipped']}")
        logger.info(f"업데이트됨: {self.stats['updated']}개")
        logger.info("")
        logger.info(f"소요 시간: {elapsed_hours:.2f}시간 ({elapsed_minutes:.1f}분)")
        logger.info(f"처리 속도: {self.stats['total_stocks']/elapsed:.2f}개/초")

        if self.stats['total_stocks'] > 0:
            success_rate = self.stats['success'] / self.stats['total_stocks'] * 100
            logger.info(f"성공률: {success_rate:.1f}%")

        # Performance check
        if elapsed_hours <= 2:
            logger.info(f"✅ 성능 목표 달성: {elapsed_hours:.2f}시간 <= 2시간")
        else:
            logger.warning(f"⚠️  성능 목표 미달: {elapsed_hours:.2f}시간 > 2시간")

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
        description='분기 재무제표 업데이트 (최신 분기만 수집)'
    )

    parser.add_argument(
        '--year',
        type=int,
        help='대상 연도 (미지정시 자동 감지)'
    )
    parser.add_argument(
        '--quarter',
        type=int,
        choices=[1, 2, 3, 4],
        help='대상 분기 (1-4, 미지정시 자동 감지)'
    )
    parser.add_argument(
        '--market',
        type=str,
        choices=['KOSPI', 'KOSDAQ', 'KONEX'],
        help='특정 시장만 업데이트'
    )
    parser.add_argument(
        '--skip-ratios',
        action='store_true',
        help='재무비율 재계산 생략'
    )
    parser.add_argument(
        '--no-retry',
        action='store_true',
        help='실패한 종목 재시도 안함'
    )

    args = parser.parse_args()

    # Validate year and quarter combination
    if (args.year and not args.quarter) or (args.quarter and not args.year):
        logger.error("❌ --year와 --quarter는 함께 지정해야 합니다.")
        sys.exit(1)

    try:
        updater = QuarterlyFinancialUpdater(
            year=args.year,
            quarter=args.quarter,
            market=args.market,
            skip_ratios=args.skip_ratios,
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
