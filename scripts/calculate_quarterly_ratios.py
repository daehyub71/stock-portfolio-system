"""재무제표 기반 분기별 재무비율 계산 스크립트.

DART API로 수집한 재무제표 데이터로부터 10개의 재무비율을 계산하고
financial_ratios 테이블에 저장합니다 (하이브리드 전략).

사용법:
    # 특정 종목의 특정 분기 계산
    python scripts/calculate_quarterly_ratios.py --ticker 005930 --year 2024 --quarter 4

    # 특정 종목의 모든 분기 계산
    python scripts/calculate_quarterly_ratios.py --ticker 005930 --all-quarters

    # 전체 종목의 모든 분기 계산
    python scripts/calculate_quarterly_ratios.py --all-stocks

    # 특정 연도의 모든 종목/분기 계산
    python scripts/calculate_quarterly_ratios.py --all-stocks --year 2024
"""

import sys
from pathlib import Path
from datetime import date
from typing import Optional, List, Dict
import argparse
from loguru import logger
from sqlalchemy import and_, or_, desc

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from db.connection import SessionLocal
from models import Stock, FinancialStatement, FinancialRatio
from calculators.financial_ratio_calculator import FinancialRatioCalculator

# Configure logger
logger.add(
    "logs/calculate_quarterly_ratios_{time}.log",
    rotation="1 day",
    retention="30 days",
    level="INFO"
)


def get_quarter_end_date(fiscal_year: int, fiscal_quarter: Optional[int]) -> date:
    """분기 마지막 날짜 계산.

    Args:
        fiscal_year: 회계연도
        fiscal_quarter: 분기 (1-4, None for annual)

    Returns:
        분기 마지막 날짜 (연간 보고서는 12월 31일)
    """
    # 연간 보고서는 12월 31일
    if fiscal_quarter is None:
        return date(fiscal_year, 12, 31)

    quarter_month_map = {
        1: (3, 31),   # Q1: 3월 31일
        2: (6, 30),   # Q2: 6월 30일
        3: (9, 30),   # Q3: 9월 30일
        4: (12, 31),  # Q4: 12월 31일
    }

    month, day = quarter_month_map.get(fiscal_quarter, (12, 31))
    return date(fiscal_year, month, day)


def get_previous_quarter(fiscal_year: int, fiscal_quarter: Optional[int]) -> tuple:
    """전 분기 계산.

    Args:
        fiscal_year: 회계연도
        fiscal_quarter: 분기 (1-4, None for annual)

    Returns:
        (전년도, 전분기) 튜플
    """
    # 연간 보고서인 경우 전년도 연간 보고서 반환
    if fiscal_quarter is None:
        return (fiscal_year - 1, None)

    if fiscal_quarter == 1:
        return (fiscal_year - 1, 4)
    else:
        return (fiscal_year, fiscal_quarter - 1)


def calculate_ratios_for_quarter(
    db,
    stock_id: int,
    fiscal_year: int,
    fiscal_quarter: Optional[int],
    calculator: FinancialRatioCalculator
) -> Optional[Dict]:
    """특정 종목의 특정 분기 재무비율 계산.

    Args:
        db: Database session
        stock_id: 종목 ID
        fiscal_year: 회계연도
        fiscal_quarter: 분기 (1-4, None for annual)
        calculator: FinancialRatioCalculator 인스턴스

    Returns:
        계산된 재무비율 딕셔너리 또는 None
    """
    # 1. 당기 재무제표 조회
    current_stmt = db.query(FinancialStatement).filter(
        and_(
            FinancialStatement.stock_id == stock_id,
            FinancialStatement.fiscal_year == fiscal_year,
            FinancialStatement.fiscal_quarter == fiscal_quarter
        )
    ).first()

    if not current_stmt:
        quarter_label = f"{fiscal_year}" if fiscal_quarter is None else f"{fiscal_year}Q{fiscal_quarter}"
        logger.warning(f"No financial statement found: stock_id={stock_id}, {quarter_label}")
        return None

    # 2. 전기 재무제표 조회 (성장률 계산용)
    prev_year, prev_quarter = get_previous_quarter(fiscal_year, fiscal_quarter)

    prev_stmt = db.query(FinancialStatement).filter(
        and_(
            FinancialStatement.stock_id == stock_id,
            FinancialStatement.fiscal_year == prev_year,
            FinancialStatement.fiscal_quarter == prev_quarter
        )
    ).first()

    # 3. 재무비율 계산
    ratios = calculator.calculate_all_ratios(
        balance_sheet=current_stmt.balance_sheet,
        income_statement=current_stmt.income_statement,
        prev_balance_sheet=prev_stmt.balance_sheet if prev_stmt else None,
        prev_income_statement=prev_stmt.income_statement if prev_stmt else None
    )

    # 4. 메타데이터 추가
    ratios['report_date'] = current_stmt.report_date
    ratios['quarter_end_date'] = get_quarter_end_date(fiscal_year, fiscal_quarter)

    return ratios


def save_quarterly_ratios(
    db,
    stock_id: int,
    fiscal_year: int,
    fiscal_quarter: Optional[int],
    ratios: Dict
) -> bool:
    """분기별/연간 재무비율을 데이터베이스에 저장 (하이브리드 전략).

    Args:
        db: Database session
        stock_id: 종목 ID
        fiscal_year: 회계연도
        fiscal_quarter: 분기 (1-4, None for annual)
        ratios: 계산된 재무비율 딕셔너리

    Returns:
        성공 여부
    """
    try:
        quarter_end_date = ratios['quarter_end_date']
        report_date = ratios['report_date']
        quarter_label = f"{fiscal_year}" if fiscal_quarter is None else f"{fiscal_year}Q{fiscal_quarter}"

        # 기존 레코드 확인 (중복 방지)
        existing = db.query(FinancialRatio).filter(
            and_(
                FinancialRatio.stock_id == stock_id,
                FinancialRatio.fiscal_year == fiscal_year,
                FinancialRatio.fiscal_quarter == fiscal_quarter
            )
        ).first()

        if existing:
            # 업데이트
            logger.info(f"Updating existing record: stock_id={stock_id}, {quarter_label}")

            existing.date = quarter_end_date
            existing.report_date = report_date
            existing.roa = ratios.get('roa')
            existing.gross_profit_margin = ratios.get('gross_profit_margin')
            existing.operating_profit_margin = ratios.get('operating_profit_margin')
            existing.net_profit_margin = ratios.get('net_profit_margin')
            existing.debt_ratio = ratios.get('debt_ratio')
            existing.debt_to_equity = ratios.get('debt_to_equity')
            existing.current_ratio = ratios.get('current_ratio')
            existing.equity_ratio = ratios.get('equity_ratio')
            existing.asset_turnover = ratios.get('asset_turnover')
            existing.revenue_growth = ratios.get('revenue_growth')

        else:
            # 신규 생성
            logger.info(f"Creating new record: stock_id={stock_id}, {quarter_label}")

            ratio_record = FinancialRatio(
                stock_id=stock_id,
                date=quarter_end_date,
                report_date=report_date,
                fiscal_year=fiscal_year,
                fiscal_quarter=fiscal_quarter,
                # 분기 계산 지표 (10개)
                roa=ratios.get('roa'),
                gross_profit_margin=ratios.get('gross_profit_margin'),
                operating_profit_margin=ratios.get('operating_profit_margin'),
                net_profit_margin=ratios.get('net_profit_margin'),
                debt_ratio=ratios.get('debt_ratio'),
                debt_to_equity=ratios.get('debt_to_equity'),
                current_ratio=ratios.get('current_ratio'),
                equity_ratio=ratios.get('equity_ratio'),
                asset_turnover=ratios.get('asset_turnover'),
                revenue_growth=ratios.get('revenue_growth'),
                # pykrx 일별 지표는 NULL
                per=None,
                pbr=None,
                eps=None,
                bps=None,
                div=None,
                dps=None,
                roe=None,  # pykrx에서 계산
                payout_ratio=None,
            )
            db.add(ratio_record)

        db.commit()
        return True

    except Exception as e:
        db.rollback()
        quarter_label = f"{fiscal_year}" if fiscal_quarter is None else f"{fiscal_year}Q{fiscal_quarter}"
        logger.error(f"Error saving ratios: stock_id={stock_id}, {quarter_label}, {e}")
        return False


def calculate_stock_all_quarters(
    db,
    stock_id: int,
    ticker: str,
    calculator: FinancialRatioCalculator
) -> Dict[str, int]:
    """특정 종목의 모든 분기 재무비율 계산.

    Args:
        db: Database session
        stock_id: 종목 ID
        ticker: 종목코드
        calculator: FinancialRatioCalculator 인스턴스

    Returns:
        통계 딕셔너리 {total, success, failed}
    """
    stats = {'total': 0, 'success': 0, 'failed': 0}

    # 해당 종목의 모든 재무제표 조회
    statements = db.query(FinancialStatement).filter(
        FinancialStatement.stock_id == stock_id
    ).order_by(
        FinancialStatement.fiscal_year.desc(),
        FinancialStatement.fiscal_quarter.desc()
    ).all()

    if not statements:
        logger.warning(f"{ticker}: No financial statements found")
        return stats

    logger.info(f"{ticker}: Processing {len(statements)} quarters...")

    for stmt in statements:
        stats['total'] += 1

        # 재무비율 계산
        ratios = calculate_ratios_for_quarter(
            db,
            stock_id,
            stmt.fiscal_year,
            stmt.fiscal_quarter,
            calculator
        )

        if ratios:
            # 저장
            success = save_quarterly_ratios(
                db,
                stock_id,
                stmt.fiscal_year,
                stmt.fiscal_quarter,
                ratios
            )

            if success:
                stats['success'] += 1
                quarter_label = f"{stmt.fiscal_year}" if stmt.fiscal_quarter is None else f"{stmt.fiscal_year}Q{stmt.fiscal_quarter}"
                logger.debug(f"  ✓ {quarter_label}: "
                           f"{sum(1 for v in ratios.values() if v is not None)}/10 ratios calculated")
            else:
                stats['failed'] += 1
        else:
            stats['failed'] += 1

    logger.info(f"{ticker}: Completed - {stats['success']}/{stats['total']} quarters successful")
    return stats


def main():
    """메인 실행 함수."""
    parser = argparse.ArgumentParser(
        description="재무제표 기반 분기별 재무비율 계산",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # 삼성전자 2024Q4 계산
  python scripts/calculate_quarterly_ratios.py --ticker 005930 --year 2024 --quarter 4

  # 삼성전자 전체 분기 계산
  python scripts/calculate_quarterly_ratios.py --ticker 005930 --all-quarters

  # 전체 종목 2024년 분기 계산
  python scripts/calculate_quarterly_ratios.py --all-stocks --year 2024

  # 전체 종목 전체 분기 계산 (시간 소요)
  python scripts/calculate_quarterly_ratios.py --all-stocks
        """
    )

    parser.add_argument('--ticker', type=str, help='종목코드 (예: 005930)')
    parser.add_argument('--year', type=int, help='회계연도 (예: 2024)')
    parser.add_argument('--quarter', type=int, choices=[1, 2, 3, 4], help='분기 (1-4)')
    parser.add_argument('--all-quarters', action='store_true', help='모든 분기 계산')
    parser.add_argument('--all-stocks', action='store_true', help='전체 종목 계산')
    parser.add_argument('--limit', type=int, help='처리할 최대 종목 수 (테스트용)')

    args = parser.parse_args()

    # 인자 검증
    if not args.all_stocks and not args.ticker:
        parser.error("--ticker 또는 --all-stocks 중 하나는 필수입니다.")

    if args.ticker and args.all_stocks:
        parser.error("--ticker와 --all-stocks는 동시에 사용할 수 없습니다.")

    if args.ticker and not args.all_quarters and (not args.year or not args.quarter):
        parser.error("--ticker 사용 시 --all-quarters 또는 --year, --quarter가 필요합니다.")

    # 데이터베이스 연결
    db = SessionLocal()
    calculator = FinancialRatioCalculator()

    try:
        # 단일 종목, 단일 분기
        if args.ticker and args.year and args.quarter:
            stock = db.query(Stock).filter(Stock.ticker == args.ticker).first()
            if not stock:
                logger.error(f"Stock not found: {args.ticker}")
                return

            logger.info(f"Calculating {args.ticker} {args.year}Q{args.quarter}...")

            ratios = calculate_ratios_for_quarter(
                db,
                stock.id,
                args.year,
                args.quarter,
                calculator
            )

            if ratios:
                success = save_quarterly_ratios(
                    db,
                    stock.id,
                    args.year,
                    args.quarter,
                    ratios
                )

                if success:
                    non_null_count = sum(1 for k, v in ratios.items()
                                        if k not in ['report_date', 'quarter_end_date'] and v is not None)
                    logger.info(f"✓ Successfully calculated {non_null_count}/10 ratios")

                    # 결과 출력
                    print("\n" + "=" * 60)
                    print(f"{args.ticker} {args.year}Q{args.quarter} 재무비율 계산 결과")
                    print("=" * 60)
                    print(f"\n보고일: {ratios['report_date']}")
                    print(f"분기말: {ratios['quarter_end_date']}\n")

                    print("[수익성 지표]")
                    print(f"  ROA:              {ratios['roa'] or 'N/A'}%")
                    print(f"  매출총이익률:      {ratios['gross_profit_margin'] or 'N/A'}%")
                    print(f"  영업이익률:        {ratios['operating_profit_margin'] or 'N/A'}%")
                    print(f"  순이익률:          {ratios['net_profit_margin'] or 'N/A'}%")

                    print("\n[안정성 지표]")
                    print(f"  부채비율:          {ratios['debt_ratio'] or 'N/A'}%")
                    print(f"  부채자본비율:      {ratios['debt_to_equity'] or 'N/A'}%")
                    print(f"  유동비율:          {ratios['current_ratio'] or 'N/A'}%")
                    print(f"  자기자본비율:      {ratios['equity_ratio'] or 'N/A'}%")

                    print("\n[활동성 지표]")
                    print(f"  총자산회전율:      {ratios['asset_turnover'] or 'N/A'}회")

                    print("\n[성장성 지표]")
                    print(f"  매출액 증가율:     {ratios['revenue_growth'] or 'N/A (전기 데이터 없음)'}%")

                    print("=" * 60 + "\n")
                else:
                    logger.error("Failed to save ratios")
            else:
                logger.error("Failed to calculate ratios")

        # 단일 종목, 모든 분기
        elif args.ticker and args.all_quarters:
            stock = db.query(Stock).filter(Stock.ticker == args.ticker).first()
            if not stock:
                logger.error(f"Stock not found: {args.ticker}")
                return

            logger.info(f"Calculating all quarters for {args.ticker} ({stock.name})...")

            stats = calculate_stock_all_quarters(db, stock.id, args.ticker, calculator)

            print("\n" + "=" * 60)
            print(f"{args.ticker} {stock.name} - 전체 분기 계산 완료")
            print("=" * 60)
            print(f"총 분기:     {stats['total']}")
            print(f"성공:       {stats['success']}")
            print(f"실패:       {stats['failed']}")
            print(f"성공률:     {stats['success']/stats['total']*100:.1f}%" if stats['total'] > 0 else "N/A")
            print("=" * 60 + "\n")

        # 전체 종목
        elif args.all_stocks:
            # 재무제표가 있는 종목만 조회
            query = db.query(Stock).join(
                FinancialStatement,
                Stock.id == FinancialStatement.stock_id
            ).filter(
                Stock.is_active == True
            )

            if args.year:
                query = query.filter(FinancialStatement.fiscal_year == args.year)

            stocks = query.distinct().order_by(Stock.ticker).all()

            if args.limit:
                stocks = stocks[:args.limit]

            total_stocks = len(stocks)
            logger.info(f"Processing {total_stocks} stocks...")

            # 전체 통계
            overall_stats = {'total': 0, 'success': 0, 'failed': 0}

            for i, stock in enumerate(stocks, 1):
                logger.info(f"\n[{i}/{total_stocks}] {stock.ticker} {stock.name}")

                stats = calculate_stock_all_quarters(db, stock.id, stock.ticker, calculator)

                overall_stats['total'] += stats['total']
                overall_stats['success'] += stats['success']
                overall_stats['failed'] += stats['failed']

            # 최종 결과
            print("\n" + "=" * 60)
            print("전체 종목 재무비율 계산 완료")
            print("=" * 60)
            print(f"처리 종목:   {total_stocks}개")
            print(f"총 분기:     {overall_stats['total']}개")
            print(f"성공:       {overall_stats['success']}개")
            print(f"실패:       {overall_stats['failed']}개")
            print(f"성공률:     {overall_stats['success']/overall_stats['total']*100:.1f}%"
                  if overall_stats['total'] > 0 else "N/A")
            print("=" * 60 + "\n")

    except KeyboardInterrupt:
        logger.warning("\n사용자에 의해 중단되었습니다.")
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
    finally:
        db.close()
        logger.info("Database connection closed")


if __name__ == "__main__":
    main()
