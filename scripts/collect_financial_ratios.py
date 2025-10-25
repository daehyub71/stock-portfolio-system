#!/usr/bin/env python3
"""재무비율 배치 수집 스크립트.

pykrx를 사용하여 전체 종목의 재무비율을 수집합니다.

Features:
- 기간별 일별 재무비율 수집 (PER, PBR, EPS, BPS, DIV, DPS)
- ROE, 배당성향 자동 계산
- 체크포인트 지원 (중단 후 재개 가능)
- 진행 상황 실시간 로깅

Usage:
    # 전체 종목 최근 3년 수집
    python scripts/collect_financial_ratios.py --years 3

    # 특정 기간 수집
    python scripts/collect_financial_ratios.py --start 20200101 --end 20250118

    # 특정 종목만 수집
    python scripts/collect_financial_ratios.py --ticker 005930 --years 5

    # 특정 시장만 수집
    python scripts/collect_financial_ratios.py --market KOSPI --years 3
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta, date
import argparse
import logging
import json
import time

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from collectors.pykrx_ratio_collector import PyKRXRatioCollector
from db.connection import SessionLocal
from models import Stock, MarketType

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class CheckpointManager:
    """체크포인트 관리 클래스."""

    def __init__(self, checkpoint_dir: Path):
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(self, data: dict):
        """체크포인트 저장."""
        checkpoint_path = self.checkpoint_dir / "ratio_collection_checkpoint.json"

        # datetime을 문자열로 변환
        serializable_data = data.copy()
        for key, value in serializable_data.items():
            if isinstance(value, (datetime, date)):
                serializable_data[key] = value.isoformat()

        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(serializable_data, f, ensure_ascii=False, indent=2)

        logger.debug("Checkpoint saved")

    def load_checkpoint(self) -> dict:
        """체크포인트 로드."""
        checkpoint_path = self.checkpoint_dir / "ratio_collection_checkpoint.json"

        if not checkpoint_path.exists():
            return {}

        try:
            with open(checkpoint_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            logger.info(f"Checkpoint loaded: {data.get('current_index', 0)}/{data.get('total_stocks', 0)}")
            return data

        except Exception as e:
            logger.error(f"Error loading checkpoint: {e}")
            return {}

    def clear_checkpoint(self):
        """체크포인트 삭제."""
        checkpoint_path = self.checkpoint_dir / "ratio_collection_checkpoint.json"

        if checkpoint_path.exists():
            checkpoint_path.unlink()
            logger.info("Checkpoint cleared")


def collect_ratios_for_stock(
    stock: Stock,
    start_date: str,
    end_date: str,
    collector: PyKRXRatioCollector
) -> int:
    """단일 종목의 재무비율 수집.

    Args:
        stock: Stock 객체
        start_date: 시작일 (YYYYMMDD)
        end_date: 종료일 (YYYYMMDD)
        collector: PyKRXRatioCollector 인스턴스

    Returns:
        수집된 레코드 수
    """
    try:
        logger.info(f"{stock.ticker} {stock.name}: Collecting ratios...")

        # 데이터 수집 및 저장
        saved = collector.collect_and_save(
            ticker=stock.ticker,
            start_date=start_date,
            end_date=end_date
        )

        if saved > 0:
            logger.info(f"  ✓ Saved {saved} records")
        else:
            logger.warning(f"  ✗ No data collected")

        # Rate limiting (pykrx는 제한 없지만 서버 부하 방지)
        time.sleep(0.1)

        return saved

    except Exception as e:
        logger.error(f"  ✗ Error: {e}")
        return 0


def main():
    """메인 실행 함수."""
    parser = argparse.ArgumentParser(description='재무비율 배치 수집')
    parser.add_argument('--start', type=str, help='시작일 (YYYYMMDD)')
    parser.add_argument('--end', type=str, help='종료일 (YYYYMMDD, 기본: 오늘)')
    parser.add_argument('--years', type=int, help='최근 N년 수집 (start 대신 사용)')
    parser.add_argument('--ticker', type=str, help='특정 종목코드')
    parser.add_argument('--market', type=str, choices=['KOSPI', 'KOSDAQ', 'KONEX', 'ALL'],
                        default='ALL', help='시장 구분')
    parser.add_argument('--resume', action='store_true', help='체크포인트에서 재개')

    args = parser.parse_args()

    # 날짜 설정
    end_date_obj = date.today()
    end_date = args.end if args.end else end_date_obj.strftime("%Y%m%d")

    if args.years:
        start_date_obj = end_date_obj - timedelta(days=args.years * 365)
        start_date = start_date_obj.strftime("%Y%m%d")
    elif args.start:
        start_date = args.start
    else:
        # 기본: 최근 3년
        start_date_obj = end_date_obj - timedelta(days=3 * 365)
        start_date = start_date_obj.strftime("%Y%m%d")

    logger.info("=" * 70)
    logger.info("재무비율 배치 수집 시작")
    logger.info("=" * 70)
    logger.info(f"수집 기간: {start_date} ~ {end_date}")
    logger.info(f"시장: {args.market}")

    # 체크포인트 매니저
    checkpoint_dir = project_root / "data" / "checkpoints"
    checkpoint_mgr = CheckpointManager(checkpoint_dir)

    # 체크포인트 로드
    checkpoint = {}
    if args.resume:
        checkpoint = checkpoint_mgr.load_checkpoint()

    db = SessionLocal()
    total_collected = 0
    total_stocks = 0
    failed_stocks = []

    try:
        # 종목 조회
        query = db.query(Stock).filter(Stock.is_active == True)

        if args.ticker:
            query = query.filter(Stock.ticker == args.ticker)

        if args.market != 'ALL':
            market_type = MarketType[args.market]
            query = query.filter(Stock.market == market_type)

        stocks = query.order_by(Stock.id).all()

        if not stocks:
            logger.warning("수집할 종목이 없습니다")
            return

        logger.info(f"총 {len(stocks)}개 종목")
        logger.info("-" * 70)

        # 재개 지점
        start_index = checkpoint.get('current_index', 0)

        # Collector 초기화
        with PyKRXRatioCollector(db_session=db) as collector:
            for idx in range(start_index, len(stocks)):
                stock = stocks[idx]

                logger.info(f"[{idx+1}/{len(stocks)}] {stock.ticker} {stock.name}")

                # 데이터 수집
                collected = collect_ratios_for_stock(
                    stock=stock,
                    start_date=start_date,
                    end_date=end_date,
                    collector=collector
                )

                if collected > 0:
                    total_collected += collected
                    total_stocks += 1
                else:
                    failed_stocks.append((stock.ticker, stock.name))

                # 체크포인트 저장 (10개마다)
                if (idx + 1) % 10 == 0:
                    checkpoint_mgr.save_checkpoint({
                        'current_index': idx + 1,
                        'total_stocks': len(stocks),
                        'total_collected': total_collected,
                        'successful_stocks': total_stocks,
                        'failed_stocks': len(failed_stocks),
                        'start_date': start_date,
                        'end_date': end_date,
                        'last_update': datetime.now()
                    })

                    logger.info(f"진행: {idx+1}/{len(stocks)} 종목, "
                               f"총 {total_collected:,}건 수집")

        # 완료
        logger.info("=" * 70)
        logger.info("수집 완료")
        logger.info(f"  - 성공: {total_stocks}개 종목")
        logger.info(f"  - 실패: {len(failed_stocks)}개 종목")
        logger.info(f"  - 총 레코드: {total_collected:,}건")

        if failed_stocks:
            logger.warning("실패한 종목:")
            for ticker, name in failed_stocks[:10]:
                logger.warning(f"  - {ticker} {name}")

        # 체크포인트 삭제
        checkpoint_mgr.clear_checkpoint()

        logger.info("=" * 70)

    except KeyboardInterrupt:
        logger.warning("\n중단되었습니다. 체크포인트가 저장되었습니다.")
        logger.info("재개하려면 --resume 옵션을 사용하세요")

    except Exception as e:
        logger.error(f"오류 발생: {e}", exc_info=True)

    finally:
        db.close()


if __name__ == "__main__":
    main()
