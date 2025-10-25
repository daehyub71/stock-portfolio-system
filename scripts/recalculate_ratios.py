#!/usr/bin/env python3
"""재무비율 재계산 스크립트.

재무제표가 업데이트된 종목들의 재무비율을 재계산합니다.
분기 재무제표 업데이트 후 자동으로 트리거될 수 있습니다.

Features:
- 특정 연도/분기 재무비율 재계산
- 자동으로 전기 데이터와 비교하여 성장률 계산
- 배치 처리 지원

Usage:
    # 최신 분기 재계산 (자동 감지)
    python scripts/recalculate_ratios.py

    # 특정 분기 재계산
    python scripts/recalculate_ratios.py --year 2024 --quarter 3

    # 특정 종목만 재계산
    python scripts/recalculate_ratios.py --ticker 005930

    # 전체 종목 재계산 (모든 분기)
    python scripts/recalculate_ratios.py --all
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple
from decimal import Decimal

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
from db.connection import SessionLocal
from models import Stock, FinancialStatement, FinancialRatio, MarketType
from calculators.financial_ratio_calculator import FinancialRatioCalculator
from sqlalchemy import and_, or_

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
    log_dir / "recalculate_ratios_{time:YYYY-MM-DD}.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    rotation="100 MB",
    retention="30 days",
    level="INFO"
)


class RatioRecalculator:
    """재무비율 재계산 클래스."""

    def __init__(
        self,
        year: Optional[int] = None,
        quarter: Optional[int] = None,
        ticker: Optional[str] = None,
        recalculate_all: bool = False,
        market: Optional[str] = None
    ):
        """Initialize ratio recalculator.

        Args:
            year: Target year (None for auto-detect)
            quarter: Target quarter (None for auto-detect)
            ticker: Specific ticker to recalculate (None for all)
            recalculate_all: Recalculate all periods
            market: Market filter
        """
        self.db = SessionLocal()
        self.calculator = FinancialRatioCalculator()

        self.year = year
        self.quarter = quarter
        self.ticker = ticker
        self.recalculate_all = recalculate_all
        self.market = market

        # Auto-detect latest quarter if not specified
        if not recalculate_all and not year and not quarter:
            self.year, self.quarter = self._detect_latest_quarter()

        # Statistics
        self.stats = {
            'start_time': datetime.now(),
            'end_time': None,
            'total_stocks': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'total_ratios': 0,
            'failed_stocks': []
        }

        logger.info("RatioRecalculator initialized")
        if not recalculate_all:
            logger.info(f"  Target: {self.year}Q{self.quarter}")
        logger.info(f"  Ticker: {self.ticker or 'ALL'}")
        logger.info(f"  Market: {self.market or 'ALL'}")
        logger.info(f"  Recalculate all: {self.recalculate_all}")

    def _detect_latest_quarter(self) -> Tuple[int, int]:
        """Detect the latest quarter based on current date."""
        today = date.today()
        current_month = today.month
        current_year = today.year

        if current_month <= 4:
            return current_year - 1, 4
        elif current_month <= 7:
            return current_year, 1
        elif current_month <= 10:
            return current_year, 2
        else:
            return current_year, 3

    def get_financial_statements(
        self,
        stock_id: int,
        fiscal_year: int,
        fiscal_quarter: int
    ) -> Tuple[Optional[FinancialStatement], Optional[FinancialStatement]]:
        """Get current and previous financial statements.

        Args:
            stock_id: Stock ID
            fiscal_year: Fiscal year
            fiscal_quarter: Fiscal quarter

        Returns:
            Tuple of (current_statement, previous_statement)
        """
        # Get current period statement
        current_stmt = self.db.query(FinancialStatement).filter(
            and_(
                FinancialStatement.stock_id == stock_id,
                FinancialStatement.fiscal_year == fiscal_year,
                FinancialStatement.fiscal_quarter == fiscal_quarter
            )
        ).first()

        if not current_stmt:
            return None, None

        # Get previous period statement (same quarter, previous year)
        prev_year = fiscal_year - 1
        prev_stmt = self.db.query(FinancialStatement).filter(
            and_(
                FinancialStatement.stock_id == stock_id,
                FinancialStatement.fiscal_year == prev_year,
                FinancialStatement.fiscal_quarter == fiscal_quarter
            )
        ).first()

        return current_stmt, prev_stmt

    def calculate_and_save_ratios(
        self,
        stock_id: int,
        fiscal_year: int,
        fiscal_quarter: int
    ) -> Dict:
        """Calculate and save financial ratios for a specific period.

        Args:
            stock_id: Stock ID
            fiscal_year: Fiscal year
            fiscal_quarter: Fiscal quarter

        Returns:
            Result dictionary
        """
        stock = self.db.query(Stock).get(stock_id)
        if not stock:
            return {'success': False, 'error': 'Stock not found'}

        try:
            # Get financial statements
            current_stmt, prev_stmt = self.get_financial_statements(
                stock_id, fiscal_year, fiscal_quarter
            )

            if not current_stmt:
                return {
                    'success': False,
                    'error': f'No financial statement for {fiscal_year}Q{fiscal_quarter}'
                }

            # Extract JSONB data
            balance_sheet = current_stmt.balance_sheet
            income_statement = current_stmt.income_statement

            prev_balance_sheet = prev_stmt.balance_sheet if prev_stmt else None
            prev_income_statement = prev_stmt.income_statement if prev_stmt else None

            # Calculate ratios
            ratios = self.calculator.calculate_all_ratios(
                balance_sheet=balance_sheet,
                income_statement=income_statement,
                prev_balance_sheet=prev_balance_sheet,
                prev_income_statement=prev_income_statement
            )

            # Check if ratio record already exists
            existing_ratio = self.db.query(FinancialRatio).filter(
                and_(
                    FinancialRatio.stock_id == stock_id,
                    FinancialRatio.fiscal_year == fiscal_year,
                    FinancialRatio.fiscal_quarter == fiscal_quarter
                )
            ).first()

            if existing_ratio:
                # Update existing record
                for key, value in ratios.items():
                    if hasattr(existing_ratio, key):
                        setattr(existing_ratio, key, value)
                logger.debug(f"  🔄 Updated ratios for {stock.ticker}")
            else:
                # Create new record
                new_ratio = FinancialRatio(
                    stock_id=stock_id,
                    fiscal_year=fiscal_year,
                    fiscal_quarter=fiscal_quarter,
                    **{k: v for k, v in ratios.items()}
                )
                self.db.add(new_ratio)
                logger.debug(f"  ✅ Created ratios for {stock.ticker}")

            self.db.commit()

            # Count non-None ratios
            calculated_count = sum(1 for v in ratios.values() if v is not None)

            return {
                'success': True,
                'calculated': calculated_count,
                'total': len(ratios)
            }

        except Exception as e:
            self.db.rollback()
            logger.error(f"  ❌ {stock.ticker}: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def recalculate_stock(self, stock: Stock) -> Dict:
        """Recalculate ratios for a stock.

        Args:
            stock: Stock object

        Returns:
            Result dictionary
        """
        ticker = stock.ticker
        name = stock.name

        if self.recalculate_all:
            # Recalculate all periods
            statements = self.db.query(FinancialStatement).filter(
                FinancialStatement.stock_id == stock.id
            ).order_by(
                FinancialStatement.fiscal_year,
                FinancialStatement.fiscal_quarter
            ).all()

            if not statements:
                return {
                    'success': False,
                    'error': 'No financial statements found'
                }

            success_count = 0
            failed_count = 0

            for stmt in statements:
                result = self.calculate_and_save_ratios(
                    stock.id,
                    stmt.fiscal_year,
                    stmt.fiscal_quarter
                )

                if result['success']:
                    success_count += 1
                else:
                    failed_count += 1

            logger.info(f"  ✅ {ticker} ({name}): {success_count} periods (failed: {failed_count})")

            return {
                'success': success_count > 0,
                'periods': success_count,
                'failed': failed_count
            }

        else:
            # Recalculate specific period
            result = self.calculate_and_save_ratios(
                stock.id,
                self.year,
                self.quarter
            )

            if result['success']:
                logger.info(f"  ✅ {ticker} ({name}): {result['calculated']}/{result['total']} ratios")
                return result
            else:
                logger.warning(f"  ⚠️  {ticker} ({name}): {result.get('error', 'Unknown error')}")
                return result

    def recalculate_all_stocks(self):
        """Recalculate ratios for all stocks."""
        logger.info("=" * 80)
        logger.info("재무비율 재계산 시작")
        logger.info("=" * 80)

        if not self.recalculate_all:
            logger.info(f"대상 분기: {self.year}Q{self.quarter}")
        else:
            logger.info("대상: 전체 분기")

        logger.info(f"시장: {self.market or 'ALL'}")
        logger.info("=" * 80)

        # Get stocks to process
        query = self.db.query(Stock)

        if self.ticker:
            query = query.filter(Stock.ticker == self.ticker)

        if self.market:
            market_type = MarketType[self.market.upper()]
            query = query.filter(Stock.market == market_type)

        stocks = query.order_by(Stock.ticker).all()
        self.stats['total_stocks'] = len(stocks)

        if not stocks:
            logger.warning("처리할 종목이 없습니다.")
            return

        logger.info(f"총 종목 수: {len(stocks)}")
        logger.info("")

        # Process each stock
        for i, stock in enumerate(stocks, 1):
            ticker = stock.ticker
            name = stock.name

            logger.info(f"[{i}/{len(stocks)}] Processing {ticker} ({name})...")

            result = self.recalculate_stock(stock)

            if result['success']:
                self.stats['success'] += 1
                if self.recalculate_all:
                    self.stats['total_ratios'] += result.get('periods', 0)
                else:
                    self.stats['total_ratios'] += result.get('calculated', 0)
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

        self.stats['end_time'] = datetime.now()
        self._print_summary()

    def _print_progress(self, current: int):
        """Print progress update."""
        elapsed = (datetime.now() - self.stats['start_time']).total_seconds()
        rate = current / elapsed if elapsed > 0 else 0
        remaining = (self.stats['total_stocks'] - current) / rate if rate > 0 else 0

        logger.info("")
        logger.info("─" * 80)
        logger.info(f"진행 상황: {current}/{self.stats['total_stocks']} ({current/self.stats['total_stocks']*100:.1f}%)")
        logger.info(f"성공: {self.stats['success']} | 실패: {self.stats['failed']}")
        logger.info(f"처리 속도: {rate:.2f}개/초 | 예상 남은 시간: {int(remaining/60)}분")
        logger.info("─" * 80)
        logger.info("")

    def _print_summary(self):
        """Print final summary."""
        elapsed = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
        elapsed_minutes = elapsed / 60

        logger.info("")
        logger.info("=" * 80)
        logger.info("재무비율 재계산 완료")
        logger.info("=" * 80)
        logger.info(f"총 종목 수: {self.stats['total_stocks']}")
        logger.info(f"성공: {self.stats['success']}")
        logger.info(f"실패: {self.stats['failed']}")
        logger.info(f"총 계산된 비율: {self.stats['total_ratios']}")
        logger.info("")
        logger.info(f"소요 시간: {elapsed_minutes:.1f}분 ({int(elapsed)}초)")

        if self.stats['total_stocks'] > 0:
            success_rate = self.stats['success'] / self.stats['total_stocks'] * 100
            logger.info(f"성공률: {success_rate:.1f}%")

        logger.info("=" * 80)

        if self.stats['failed_stocks']:
            logger.info("")
            logger.info(f"❌ 실패한 종목 ({len(self.stats['failed_stocks'])}):")
            for stock in self.stats['failed_stocks'][:10]:
                logger.info(f"  - {stock['ticker']} ({stock['name']}): {stock['error']}")
            if len(self.stats['failed_stocks']) > 10:
                logger.info(f"  ... 외 {len(self.stats['failed_stocks']) - 10}개")

    def close(self):
        """Close database connection."""
        self.db.close()


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='재무비율 재계산'
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
        '--ticker',
        type=str,
        help='특정 종목만 재계산 (예: 005930)'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='전체 분기 재계산'
    )
    parser.add_argument(
        '--market',
        type=str,
        choices=['KOSPI', 'KOSDAQ', 'KONEX'],
        help='특정 시장만 재계산'
    )

    args = parser.parse_args()

    # Validate arguments
    if args.all and (args.year or args.quarter):
        logger.error("❌ --all 옵션은 --year, --quarter와 함께 사용할 수 없습니다.")
        sys.exit(1)

    if (args.year and not args.quarter) or (args.quarter and not args.year):
        logger.error("❌ --year와 --quarter는 함께 지정해야 합니다.")
        sys.exit(1)

    try:
        recalculator = RatioRecalculator(
            year=args.year,
            quarter=args.quarter,
            ticker=args.ticker,
            recalculate_all=args.all,
            market=args.market
        )

        recalculator.recalculate_all_stocks()

    except KeyboardInterrupt:
        logger.warning("\n⚠️  사용자에 의해 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if 'recalculator' in locals():
            recalculator.close()


if __name__ == '__main__':
    main()
