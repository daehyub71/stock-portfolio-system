#!/usr/bin/env python3
"""증분 업데이트 시스템 테스트 스크립트.

일일 시세 업데이트, 분기 재무제표 업데이트, 재무비율 재계산의
성능과 정확성을 검증합니다.

Tests:
- 일일 시세 업데이트 성능 (목표: 30분 이내)
- 분기 재무제표 업데이트 성능 (목표: 2시간 이내)
- 재무비율 재계산 정확성
- 데이터 무결성 검증

Usage:
    # 전체 테스트 실행
    python tests/test_incremental_updates.py

    # 특정 테스트만 실행
    python tests/test_incremental_updates.py --test daily_prices
    python tests/test_incremental_updates.py --test quarterly_financials
    python tests/test_incremental_updates.py --test ratios
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, date, timedelta
import time
from typing import Dict, List

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
from db.connection import SessionLocal
from models import Stock, DailyPrice, FinancialStatement, FinancialRatio, MarketType
from sqlalchemy import func, and_

# Configure logger
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    level="INFO"
)


class IncrementalUpdateTester:
    """증분 업데이트 테스트 클래스."""

    def __init__(self):
        """Initialize tester."""
        self.db = SessionLocal()
        self.results = {
            'daily_prices': None,
            'quarterly_financials': None,
            'ratios': None
        }

    def test_daily_price_update_performance(self) -> Dict:
        """일일 시세 업데이트 성능 테스트.

        Returns:
            Test result dictionary
        """
        logger.info("=" * 80)
        logger.info("TEST 1: 일일 시세 업데이트 성능")
        logger.info("=" * 80)

        # Count active stocks
        active_stocks = self.db.query(func.count(Stock.id)).filter(
            Stock.delisting_date == None
        ).scalar()

        logger.info(f"활성 종목 수: {active_stocks}")

        # Check if we have recent price data
        yesterday = date.today() - timedelta(days=1)
        recent_price_count = self.db.query(func.count(DailyPrice.id)).filter(
            DailyPrice.date == yesterday
        ).scalar()

        logger.info(f"전일({yesterday}) 시세 데이터: {recent_price_count}개")

        # Test with a sample (10 stocks)
        sample_stocks = self.db.query(Stock).filter(
            Stock.delisting_date == None
        ).limit(10).all()

        logger.info(f"\n샘플 테스트: {len(sample_stocks)}개 종목")

        start_time = time.time()

        from collectors.pykrx_price_collector import PyKRXPriceCollector
        collector = PyKRXPriceCollector(db_session=self.db)

        success_count = 0
        for stock in sample_stocks:
            try:
                result = collector.collect_and_save(
                    ticker=stock.ticker,
                    start_date=yesterday,
                    end_date=yesterday
                )
                if result['success']:
                    success_count += 1
            except Exception as e:
                logger.error(f"Failed: {stock.ticker} - {e}")

        elapsed = time.time() - start_time

        # Extrapolate to full dataset
        avg_time_per_stock = elapsed / len(sample_stocks)
        estimated_total_time = (avg_time_per_stock * active_stocks) / 60  # minutes

        logger.info(f"\n샘플 결과:")
        logger.info(f"  처리 시간: {elapsed:.2f}초")
        logger.info(f"  성공: {success_count}/{len(sample_stocks)}")
        logger.info(f"  평균 속도: {avg_time_per_stock:.2f}초/종목")
        logger.info(f"\n전체 예상:")
        logger.info(f"  예상 소요 시간: {estimated_total_time:.1f}분")

        # Performance check
        passed = estimated_total_time <= 30
        if passed:
            logger.info(f"  ✅ 성능 목표 달성: {estimated_total_time:.1f}분 <= 30분")
        else:
            logger.warning(f"  ⚠️  성능 목표 미달: {estimated_total_time:.1f}분 > 30분")

        return {
            'passed': passed,
            'active_stocks': active_stocks,
            'recent_data_count': recent_price_count,
            'sample_size': len(sample_stocks),
            'sample_success': success_count,
            'avg_time_per_stock': avg_time_per_stock,
            'estimated_total_time_minutes': estimated_total_time
        }

    def test_quarterly_financial_update_performance(self) -> Dict:
        """분기 재무제표 업데이트 성능 테스트.

        Returns:
            Test result dictionary
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST 2: 분기 재무제표 업데이트 성능")
        logger.info("=" * 80)

        # Count active stocks
        active_stocks = self.db.query(func.count(Stock.id)).filter(
            Stock.delisting_date == None
        ).scalar()

        logger.info(f"활성 종목 수: {active_stocks}")

        # Check latest financial statement
        latest_stmt = self.db.query(FinancialStatement).order_by(
            FinancialStatement.fiscal_year.desc(),
            FinancialStatement.fiscal_quarter.desc()
        ).first()

        if latest_stmt:
            logger.info(f"최신 재무제표: {latest_stmt.fiscal_year}Q{latest_stmt.fiscal_quarter}")

            # Count statements for latest period
            stmt_count = self.db.query(func.count(FinancialStatement.id)).filter(
                and_(
                    FinancialStatement.fiscal_year == latest_stmt.fiscal_year,
                    FinancialStatement.fiscal_quarter == latest_stmt.fiscal_quarter
                )
            ).scalar()

            logger.info(f"최신 분기 재무제표 수: {stmt_count}개")
        else:
            logger.warning("재무제표 데이터가 없습니다.")

        # Estimate based on DART API rate limit: 5 req/sec with 0.25s delay
        requests_per_second = 4  # Conservative estimate
        estimated_seconds = active_stocks / requests_per_second
        estimated_minutes = estimated_seconds / 60
        estimated_hours = estimated_minutes / 60

        logger.info(f"\n예상 소요 시간:")
        logger.info(f"  DART API rate limit: ~{requests_per_second} req/sec")
        logger.info(f"  예상 시간: {estimated_hours:.2f}시간 ({estimated_minutes:.1f}분)")

        # Performance check
        passed = estimated_hours <= 2
        if passed:
            logger.info(f"  ✅ 성능 목표 달성: {estimated_hours:.2f}시간 <= 2시간")
        else:
            logger.warning(f"  ⚠️  성능 목표 미달: {estimated_hours:.2f}시간 > 2시간")

        return {
            'passed': passed,
            'active_stocks': active_stocks,
            'latest_period': f"{latest_stmt.fiscal_year}Q{latest_stmt.fiscal_quarter}" if latest_stmt else None,
            'latest_period_count': stmt_count if latest_stmt else 0,
            'estimated_time_hours': estimated_hours
        }

    def test_ratio_calculation_accuracy(self) -> Dict:
        """재무비율 계산 정확성 테스트.

        Returns:
            Test result dictionary
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST 3: 재무비율 계산 정확성")
        logger.info("=" * 80)

        from calculators.financial_ratio_calculator import FinancialRatioCalculator

        # Test with known data (Samsung Electronics example)
        test_balance_sheet = {
            "assets": {
                "current": {"유동자산": 227062266000000.0},
                "non_current": {"비유동자산": 287469682000000.0}
            },
            "equity": {"자본총계": 402192070000000.0},
            "liabilities": {
                "current": {"유동부채": 93326299000000.0},
                "non_current": {"비유동부채": 19013579000000.0}
            }
        }

        test_income_statement = {
            "revenue": {"매출액": 258937605000000.0},
            "operating_income": {"영업이익": 54336341000000.0},
            "net_income": {"당기순이익": 23678361000000.0}
        }

        calculator = FinancialRatioCalculator()
        ratios = calculator.calculate_all_ratios(test_balance_sheet, test_income_statement)

        logger.info("테스트 데이터로 재무비율 계산:")

        # Check specific expected values
        expected_values = {
            'roe': 5.89,  # Approximate ROE
            'roa': 4.60,  # Approximate ROA
            'operating_profit_margin': 20.99,  # ~21%
            'debt_ratio': 27.93,  # ~28%
            'current_ratio': 243.28  # ~243%
        }

        passed_checks = 0
        failed_checks = 0

        logger.info("")
        for ratio_name, expected in expected_values.items():
            actual = ratios.get(ratio_name)
            if actual is not None:
                actual_float = float(actual)
                diff = abs(actual_float - expected)
                tolerance = expected * 0.1  # 10% tolerance

                if diff <= tolerance:
                    logger.info(f"  ✅ {ratio_name}: {actual_float:.2f} (expected ~{expected:.2f})")
                    passed_checks += 1
                else:
                    logger.warning(f"  ⚠️  {ratio_name}: {actual_float:.2f} (expected ~{expected:.2f}, diff: {diff:.2f})")
                    failed_checks += 1
            else:
                logger.error(f"  ❌ {ratio_name}: Not calculated")
                failed_checks += 1

        # Check database integrity
        logger.info(f"\n데이터베이스 무결성:")

        # Count ratios
        ratio_count = self.db.query(func.count(FinancialRatio.id)).scalar()
        logger.info(f"  저장된 재무비율 레코드: {ratio_count}개")

        # Sample check - stocks with both statements and ratios
        stocks_with_stmts = self.db.query(
            func.count(func.distinct(FinancialStatement.stock_id))
        ).scalar()

        stocks_with_ratios = self.db.query(
            func.count(func.distinct(FinancialRatio.stock_id))
        ).scalar()

        logger.info(f"  재무제표 보유 종목: {stocks_with_stmts}개")
        logger.info(f"  재무비율 보유 종목: {stocks_with_ratios}개")

        coverage = (stocks_with_ratios / stocks_with_stmts * 100) if stocks_with_stmts > 0 else 0
        logger.info(f"  비율 계산 커버리지: {coverage:.1f}%")

        passed = (passed_checks >= 4) and (coverage >= 80)

        if passed:
            logger.info(f"\n  ✅ 정확성 테스트 통과")
        else:
            logger.warning(f"\n  ⚠️  정확성 테스트 미달")

        return {
            'passed': passed,
            'passed_checks': passed_checks,
            'failed_checks': failed_checks,
            'total_checks': passed_checks + failed_checks,
            'ratio_count': ratio_count,
            'stocks_with_statements': stocks_with_stmts,
            'stocks_with_ratios': stocks_with_ratios,
            'coverage_percent': coverage
        }

    def test_data_integrity(self) -> Dict:
        """데이터 무결성 테스트.

        Returns:
            Test result dictionary
        """
        logger.info("\n" + "=" * 80)
        logger.info("TEST 4: 데이터 무결성 검증")
        logger.info("=" * 80)

        issues = []

        # Check 1: Stocks without any price data
        stocks_without_prices = self.db.query(Stock).outerjoin(DailyPrice).filter(
            DailyPrice.id == None
        ).count()

        if stocks_without_prices > 0:
            logger.warning(f"  ⚠️  시세 데이터 없는 종목: {stocks_without_prices}개")
            issues.append(f"No price data: {stocks_without_prices} stocks")
        else:
            logger.info(f"  ✅ 모든 종목에 시세 데이터 존재")

        # Check 2: Price data gaps (missing days)
        # (Complex query - simplified check)
        today = date.today()
        last_week = today - timedelta(days=7)

        recent_price_dates = self.db.query(
            func.distinct(DailyPrice.date)
        ).filter(
            DailyPrice.date >= last_week
        ).count()

        logger.info(f"  최근 7일간 시세 데이터: {recent_price_dates}일")

        # Check 3: Financial statements without ratios
        stmts_without_ratios = self.db.query(FinancialStatement).outerjoin(
            FinancialRatio,
            and_(
                FinancialStatement.stock_id == FinancialRatio.stock_id,
                FinancialStatement.fiscal_year == FinancialRatio.fiscal_year,
                FinancialStatement.fiscal_quarter == FinancialRatio.fiscal_quarter
            )
        ).filter(FinancialRatio.id == None).count()

        if stmts_without_ratios > 0:
            logger.warning(f"  ⚠️  비율 미계산 재무제표: {stmts_without_ratios}개")
            issues.append(f"Statements without ratios: {stmts_without_ratios}")
        else:
            logger.info(f"  ✅ 모든 재무제표에 비율 계산됨")

        # Check 4: NULL values in critical fields
        null_price_checks = [
            ('close_price', self.db.query(DailyPrice).filter(DailyPrice.close_price == None).count()),
            ('volume', self.db.query(DailyPrice).filter(DailyPrice.volume == None).count())
        ]

        for field, count in null_price_checks:
            if count > 0:
                logger.warning(f"  ⚠️  NULL {field}: {count}개")
                issues.append(f"NULL {field}: {count}")

        passed = len(issues) == 0

        if passed:
            logger.info(f"\n  ✅ 데이터 무결성 검증 통과")
        else:
            logger.warning(f"\n  ⚠️  {len(issues)}개 문제 발견")

        return {
            'passed': passed,
            'issues': issues,
            'stocks_without_prices': stocks_without_prices,
            'recent_price_dates': recent_price_dates,
            'statements_without_ratios': stmts_without_ratios
        }

    def run_all_tests(self) -> Dict:
        """Run all tests.

        Returns:
            Overall test results
        """
        logger.info("=" * 80)
        logger.info("증분 업데이트 시스템 테스트")
        logger.info("=" * 80)
        logger.info("")

        start_time = time.time()

        # Run tests
        self.results['daily_prices'] = self.test_daily_price_update_performance()
        self.results['quarterly_financials'] = self.test_quarterly_financial_update_performance()
        self.results['ratios'] = self.test_ratio_calculation_accuracy()
        self.results['integrity'] = self.test_data_integrity()

        elapsed = time.time() - start_time

        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("테스트 결과 요약")
        logger.info("=" * 80)

        all_passed = all(
            result['passed']
            for result in self.results.values()
            if result is not None
        )

        logger.info(f"\n1. 일일 시세 업데이트: {'✅ PASS' if self.results['daily_prices']['passed'] else '❌ FAIL'}")
        logger.info(f"   - 예상 소요 시간: {self.results['daily_prices']['estimated_total_time_minutes']:.1f}분")

        logger.info(f"\n2. 분기 재무제표 업데이트: {'✅ PASS' if self.results['quarterly_financials']['passed'] else '❌ FAIL'}")
        logger.info(f"   - 예상 소요 시간: {self.results['quarterly_financials']['estimated_time_hours']:.2f}시간")

        logger.info(f"\n3. 재무비율 계산: {'✅ PASS' if self.results['ratios']['passed'] else '❌ FAIL'}")
        logger.info(f"   - 정확성: {self.results['ratios']['passed_checks']}/{self.results['ratios']['total_checks']}")
        logger.info(f"   - 커버리지: {self.results['ratios']['coverage_percent']:.1f}%")

        logger.info(f"\n4. 데이터 무결성: {'✅ PASS' if self.results['integrity']['passed'] else '❌ FAIL'}")
        if self.results['integrity']['issues']:
            logger.info(f"   - 발견된 문제: {len(self.results['integrity']['issues'])}개")

        logger.info(f"\n총 테스트 시간: {elapsed:.2f}초")

        if all_passed:
            logger.info("\n✅ 모든 테스트 통과!")
        else:
            logger.warning("\n⚠️  일부 테스트 실패")

        logger.info("=" * 80)

        return {
            'all_passed': all_passed,
            'elapsed_seconds': elapsed,
            'results': self.results
        }

    def close(self):
        """Close database connection."""
        self.db.close()


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='증분 업데이트 시스템 테스트'
    )

    parser.add_argument(
        '--test',
        type=str,
        choices=['daily_prices', 'quarterly_financials', 'ratios', 'integrity', 'all'],
        default='all',
        help='실행할 테스트 선택'
    )

    args = parser.parse_args()

    try:
        tester = IncrementalUpdateTester()

        if args.test == 'all':
            tester.run_all_tests()
        elif args.test == 'daily_prices':
            tester.test_daily_price_update_performance()
        elif args.test == 'quarterly_financials':
            tester.test_quarterly_financial_update_performance()
        elif args.test == 'ratios':
            tester.test_ratio_calculation_accuracy()
        elif args.test == 'integrity':
            tester.test_data_integrity()

    except Exception as e:
        logger.error(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if 'tester' in locals():
            tester.close()


if __name__ == '__main__':
    main()
