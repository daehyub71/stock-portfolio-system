#!/usr/bin/env python3
"""시세 데이터 증분 업데이트 스크립트.

마지막 수집일 이후의 누락된 시세 데이터를 자동으로 수집합니다.

Features:
- 각 종목의 최종 수집일 확인
- 누락된 기간 자동 탐지
- 증분 업데이트 (오늘까지)
- 진행 상황 로깅

Usage:
    # 전체 종목 업데이트
    python scripts/update_incremental_prices.py

    # 특정 종목만 업데이트
    python scripts/update_incremental_prices.py --ticker 005930

    # 특정 시장만 업데이트
    python scripts/update_incremental_prices.py --market KOSPI
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta, date
import argparse
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from collectors.pykrx_price_collector import PyKRXPriceCollector
from db.connection import SessionLocal
from models import Stock, DailyPrice, MarketType
from sqlalchemy import func, and_

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def get_last_collection_date(db, stock_id: int) -> date:
    """종목의 마지막 수집일 조회.

    Args:
        db: Database session
        stock_id: 종목 ID

    Returns:
        마지막 수집일 (없으면 None)
    """
    last_date = db.query(func.max(DailyPrice.date)).filter(
        DailyPrice.stock_id == stock_id
    ).scalar()

    return last_date


def update_stock_prices(
    ticker: str,
    name: str,
    stock_id: int,
    last_date: date,
    end_date: date,
    collector: PyKRXPriceCollector
) -> int:
    """특정 종목의 누락된 시세 업데이트.

    Args:
        ticker: 종목코드
        name: 종목명
        stock_id: 종목 ID
        last_date: 마지막 수집일
        end_date: 업데이트 종료일
        collector: PyKRXPriceCollector 인스턴스

    Returns:
        수집된 레코드 수
    """
    # 수집 시작일 (마지막 수집일 다음날)
    start_date = last_date + timedelta(days=1) if last_date else date(2015, 1, 1)

    # 수집 기간 확인
    if start_date > end_date:
        logger.debug(f"{ticker} {name}: Already up to date")
        return 0

    days_to_collect = (end_date - start_date).days + 1

    logger.info(
        f"{ticker} {name}: Collecting {days_to_collect} days "
        f"({start_date} ~ {end_date})"
    )

    try:
        # 데이터 수집 및 저장 (통합 메서드 사용)
        result = collector.collect_and_save(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date
        )

        collected = result.get('saved', 0)

        if collected > 0:
            logger.info(f"  ✓ Collected {collected} records for {ticker} {name}")
        else:
            logger.warning(f"  ✗ No data collected for {ticker} {name}")

        return collected

    except Exception as e:
        logger.error(f"  ✗ Error collecting {ticker} {name}: {e}")
        return 0


def main():
    """메인 실행 함수."""
    parser = argparse.ArgumentParser(description='시세 데이터 증분 업데이트')
    parser.add_argument('--ticker', type=str, help='특정 종목코드 (예: 005930)')
    parser.add_argument('--market', type=str, choices=['KOSPI', 'KOSDAQ', 'KONEX', 'ALL'],
                        default='ALL', help='시장 구분')
    parser.add_argument('--days', type=int, default=None,
                        help='수집할 최근 N일 (기본: 오늘까지 전체)')

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("시세 데이터 증분 업데이트 시작")
    logger.info("=" * 70)

    # 종료일 설정
    end_date = date.today()

    # days 옵션이 있으면 시작일 제한
    if args.days:
        min_start_date = end_date - timedelta(days=args.days)
        logger.info(f"최근 {args.days}일만 업데이트 ({min_start_date} ~ {end_date})")
    else:
        min_start_date = None
        logger.info(f"전체 누락 데이터 업데이트 (~ {end_date})")

    db = SessionLocal()
    total_collected = 0
    total_stocks = 0
    skipped_stocks = 0

    try:
        # 종목 조회
        query = db.query(Stock).filter(Stock.is_active == True)

        if args.ticker:
            query = query.filter(Stock.ticker == args.ticker)
            logger.info(f"종목 필터: {args.ticker}")

        if args.market != 'ALL':
            market_type = MarketType[args.market]
            query = query.filter(Stock.market == market_type)
            logger.info(f"시장 필터: {args.market}")

        stocks = query.order_by(Stock.id).all()

        if not stocks:
            logger.warning("업데이트할 종목이 없습니다")
            return

        logger.info(f"총 {len(stocks)}개 종목 업데이트 예정")
        logger.info("-" * 70)

        # Collector 초기화
        with PyKRXPriceCollector(db_session=db) as collector:
            for idx, stock in enumerate(stocks, 1):
                # 마지막 수집일 확인
                last_date = get_last_collection_date(db, stock.id)

                if last_date:
                    logger.debug(f"[{idx}/{len(stocks)}] {stock.ticker} {stock.name}: "
                                f"Last date = {last_date}")

                    # days 옵션 적용
                    if min_start_date and last_date < min_start_date:
                        actual_start_date = min_start_date
                    else:
                        actual_start_date = last_date + timedelta(days=1)

                    # 이미 최신 데이터인 경우
                    if actual_start_date > end_date:
                        logger.debug(f"  → Already up to date")
                        skipped_stocks += 1
                        continue
                else:
                    logger.info(f"[{idx}/{len(stocks)}] {stock.ticker} {stock.name}: "
                               f"No data yet")
                    actual_start_date = min_start_date if min_start_date else date(2015, 1, 1)

                # 데이터 수집
                collected = update_stock_prices(
                    ticker=stock.ticker,
                    name=stock.name,
                    stock_id=stock.id,
                    last_date=last_date,
                    end_date=end_date,
                    collector=collector
                )

                total_collected += collected
                total_stocks += 1

                # 진행 상황 출력
                if idx % 10 == 0:
                    logger.info(f"진행: {idx}/{len(stocks)} 종목, "
                               f"총 {total_collected:,}건 수집")

        logger.info("=" * 70)
        logger.info("업데이트 완료")
        logger.info(f"  - 처리된 종목: {total_stocks}개")
        logger.info(f"  - 건너뛴 종목: {skipped_stocks}개 (이미 최신)")
        logger.info(f"  - 수집된 레코드: {total_collected:,}건")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"오류 발생: {e}", exc_info=True)

    finally:
        db.close()


if __name__ == "__main__":
    main()
