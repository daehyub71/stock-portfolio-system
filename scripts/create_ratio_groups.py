#!/usr/bin/env python3
"""재무비율 수집을 위한 그룹 생성 스크립트.

전체 종목을 작은 그룹으로 나누어 안정적인 배치 수집을 지원합니다.

Usage:
    # 전체 종목을 50개씩 그룹화
    python scripts/create_ratio_groups.py --group-size 50

    # 미수집 종목만 그룹화
    python scripts/create_ratio_groups.py --uncollected-only

    # 특정 시장만 그룹화
    python scripts/create_ratio_groups.py --market KOSPI --group-size 100
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta, date
import argparse
import json
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from db.connection import SessionLocal
from models import Stock, FinancialRatio, MarketType
from sqlalchemy import func

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def get_uncollected_stocks(db, start_date: str, market: str = 'ALL'):
    """미수집 종목 조회.

    Args:
        db: DB 세션
        start_date: 시작일 (YYYYMMDD)
        market: 시장 구분

    Returns:
        미수집 종목 리스트
    """
    start_date_obj = datetime.strptime(start_date, "%Y%m%d").date()

    # 전체 활성 종목 조회
    query = db.query(Stock).filter(Stock.is_active == True)

    if market != 'ALL':
        market_type = MarketType[market]
        query = query.filter(Stock.market == market_type)

    all_stocks = query.all()

    # 수집된 종목 확인
    uncollected_stocks = []

    for stock in all_stocks:
        # 해당 기간의 재무비율 데이터가 있는지 확인
        ratio_count = db.query(func.count(FinancialRatio.id)).filter(
            FinancialRatio.stock_id == stock.id,
            FinancialRatio.date >= start_date_obj
        ).scalar()

        if ratio_count == 0:
            uncollected_stocks.append(stock)

    return uncollected_stocks


def create_groups(stocks: list, group_size: int, output_dir: Path):
    """종목을 그룹으로 나누어 저장.

    Args:
        stocks: 종목 리스트
        group_size: 그룹당 종목 수
        output_dir: 저장 디렉토리
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    total_stocks = len(stocks)
    total_groups = (total_stocks + group_size - 1) // group_size

    logger.info(f"총 {total_stocks}개 종목을 {total_groups}개 그룹으로 분할 (그룹당 {group_size}개)")

    groups = []

    for group_id in range(total_groups):
        start_idx = group_id * group_size
        end_idx = min((group_id + 1) * group_size, total_stocks)

        group_stocks = stocks[start_idx:end_idx]

        group_data = {
            'group_id': group_id + 1,
            'total_groups': total_groups,
            'stock_count': len(group_stocks),
            'created_at': datetime.now().isoformat(),
            'tickers': [
                {
                    'ticker': s.ticker,
                    'name': s.name,
                    'market': s.market.value
                }
                for s in group_stocks
            ]
        }

        # JSON 파일로 저장
        group_file = output_dir / f"ratio_group_{group_id + 1:03d}.json"
        with open(group_file, 'w', encoding='utf-8') as f:
            json.dump(group_data, f, ensure_ascii=False, indent=2)

        groups.append(group_data)
        logger.info(f"  Group {group_id + 1}/{total_groups}: {len(group_stocks)}개 종목 → {group_file.name}")

    # 그룹 메타데이터 저장
    metadata = {
        'total_stocks': total_stocks,
        'total_groups': total_groups,
        'group_size': group_size,
        'created_at': datetime.now().isoformat(),
        'groups': [
            {
                'group_id': g['group_id'],
                'stock_count': g['stock_count'],
                'file': f"ratio_group_{g['group_id']:03d}.json"
            }
            for g in groups
        ]
    }

    metadata_file = output_dir / "ratio_groups_metadata.json"
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    logger.info(f"\n메타데이터 저장: {metadata_file}")

    return groups


def main():
    """메인 실행 함수."""
    parser = argparse.ArgumentParser(description='재무비율 수집 그룹 생성')
    parser.add_argument('--group-size', type=int, default=50,
                        help='그룹당 종목 수 (기본: 50)')
    parser.add_argument('--market', type=str, choices=['KOSPI', 'KOSDAQ', 'KONEX', 'ALL'],
                        default='ALL', help='시장 구분')
    parser.add_argument('--uncollected-only', action='store_true',
                        help='미수집 종목만 그룹화')
    parser.add_argument('--start-date', type=str,
                        help='미수집 판단 기준 시작일 (YYYYMMDD, 기본: 3년 전)')

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("재무비율 수집 그룹 생성")
    logger.info("=" * 70)

    db = SessionLocal()

    try:
        # 시작일 설정
        if args.uncollected_only:
            if args.start_date:
                start_date = args.start_date
            else:
                # 기본: 3년 전
                start_date_obj = date.today() - timedelta(days=3 * 365)
                start_date = start_date_obj.strftime("%Y%m%d")

            logger.info(f"미수집 종목 조회 (기준일: {start_date})")
            stocks = get_uncollected_stocks(db, start_date, args.market)
            logger.info(f"미수집 종목: {len(stocks)}개")
        else:
            # 전체 활성 종목
            query = db.query(Stock).filter(Stock.is_active == True)

            if args.market != 'ALL':
                market_type = MarketType[args.market]
                query = query.filter(Stock.market == market_type)

            stocks = query.order_by(Stock.id).all()
            logger.info(f"전체 종목: {len(stocks)}개")

        if not stocks:
            logger.warning("그룹화할 종목이 없습니다")
            return

        # 그룹 생성
        output_dir = project_root / "data" / "ratio_groups"
        groups = create_groups(stocks, args.group_size, output_dir)

        logger.info("=" * 70)
        logger.info("그룹 생성 완료!")
        logger.info(f"  - 총 종목: {len(stocks)}개")
        logger.info(f"  - 총 그룹: {len(groups)}개")
        logger.info(f"  - 저장 위치: {output_dir}")
        logger.info("=" * 70)

        logger.info("\n다음 명령어로 그룹별 수집 실행:")
        logger.info(f"  python scripts/batch_collect_ratios.py --group-id 1 --years 3")

    except Exception as e:
        logger.error(f"오류 발생: {e}", exc_info=True)

    finally:
        db.close()


if __name__ == "__main__":
    main()
