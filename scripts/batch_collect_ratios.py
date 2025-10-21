#!/usr/bin/env python3
"""그룹 기반 재무비율 배치 수집 스크립트.

create_ratio_groups.py로 생성된 그룹 파일을 읽어 안정적으로 수집합니다.

Features:
- 그룹 단위 수집으로 안정성 향상
- 체크포인트 지원 (그룹 내 재개 가능)
- 상세한 에러 로깅
- 실패한 종목 재시도 로직

Usage:
    # 특정 그룹 수집 (최근 3년)
    python scripts/batch_collect_ratios.py --group-id 1 --years 3

    # 특정 기간 수집
    python scripts/batch_collect_ratios.py --group-id 1 --start 20200101 --end 20250120

    # 중단된 그룹 재개
    python scripts/batch_collect_ratios.py --group-id 1 --years 3 --resume

    # 전체 그룹 순차 수집
    python scripts/batch_collect_ratios.py --all --years 3
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
from models import Stock

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class GroupCheckpointManager:
    """그룹별 체크포인트 관리 클래스."""

    def __init__(self, checkpoint_dir: Path, group_id: int):
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.group_id = group_id

    def get_checkpoint_path(self):
        """체크포인트 파일 경로."""
        return self.checkpoint_dir / f"ratio_group_{self.group_id:03d}_checkpoint.json"

    def save_checkpoint(self, data: dict):
        """체크포인트 저장."""
        checkpoint_path = self.get_checkpoint_path()

        # datetime을 문자열로 변환
        serializable_data = data.copy()
        for key, value in serializable_data.items():
            if isinstance(value, (datetime, date)):
                serializable_data[key] = value.isoformat()

        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(serializable_data, f, ensure_ascii=False, indent=2)

    def load_checkpoint(self) -> dict:
        """체크포인트 로드."""
        checkpoint_path = self.get_checkpoint_path()

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
        checkpoint_path = self.get_checkpoint_path()

        if checkpoint_path.exists():
            checkpoint_path.unlink()
            logger.info("Checkpoint cleared")


def collect_ratios_for_stock(
    stock: Stock,
    start_date: str,
    end_date: str,
    collector: PyKRXRatioCollector,
    retry_count: int = 3
) -> tuple[int, str]:
    """단일 종목의 재무비율 수집 (재시도 로직 포함).

    Args:
        stock: Stock 객체
        start_date: 시작일 (YYYYMMDD)
        end_date: 종료일 (YYYYMMDD)
        collector: PyKRXRatioCollector 인스턴스
        retry_count: 재시도 횟수

    Returns:
        (수집된 레코드 수, 에러 메시지)
    """
    for attempt in range(retry_count):
        try:
            # 데이터 수집 및 저장
            saved = collector.collect_and_save(
                ticker=stock.ticker,
                start_date=start_date,
                end_date=end_date
            )

            # Rate limiting (pykrx는 제한 없지만 서버 부하 방지)
            time.sleep(0.1)

            return saved, ""

        except Exception as e:
            error_msg = str(e)

            if attempt < retry_count - 1:
                logger.warning(f"  Retry {attempt + 1}/{retry_count - 1}: {error_msg}")
                time.sleep(1)  # 재시도 전 대기
            else:
                logger.error(f"  ✗ Failed after {retry_count} attempts: {error_msg}")
                return 0, error_msg

    return 0, "Unknown error"


def load_group_file(group_file: Path) -> dict:
    """그룹 파일 로드.

    Args:
        group_file: 그룹 파일 경로

    Returns:
        그룹 데이터
    """
    if not group_file.exists():
        raise FileNotFoundError(f"Group file not found: {group_file}")

    with open(group_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def collect_group(
    group_id: int,
    start_date: str,
    end_date: str,
    resume: bool = False
):
    """그룹 수집 실행.

    Args:
        group_id: 그룹 ID
        start_date: 시작일 (YYYYMMDD)
        end_date: 종료일 (YYYYMMDD)
        resume: 재개 여부
    """
    # 그룹 파일 로드
    group_dir = project_root / "data" / "ratio_groups"
    group_file = group_dir / f"ratio_group_{group_id:03d}.json"

    logger.info(f"Loading group file: {group_file}")
    group_data = load_group_file(group_file)

    logger.info(f"Group {group_id}: {group_data['stock_count']} stocks")

    # 체크포인트 매니저
    checkpoint_dir = project_root / "data" / "checkpoints"
    checkpoint_mgr = GroupCheckpointManager(checkpoint_dir, group_id)

    # 체크포인트 로드
    checkpoint = {}
    if resume:
        checkpoint = checkpoint_mgr.load_checkpoint()

    db = SessionLocal()
    total_collected = 0
    successful_stocks = 0
    failed_stocks = []

    try:
        # 재개 지점
        start_index = checkpoint.get('current_index', 0)

        # Collector 초기화
        with PyKRXRatioCollector(db_session=db) as collector:
            for idx in range(start_index, len(group_data['tickers'])):
                ticker_info = group_data['tickers'][idx]
                ticker = ticker_info['ticker']
                name = ticker_info['name']

                # Stock 조회
                stock = db.query(Stock).filter(Stock.ticker == ticker).first()

                if not stock:
                    logger.warning(f"[{idx+1}/{group_data['stock_count']}] {ticker} {name}: Stock not found in DB")
                    failed_stocks.append((ticker, name, "Stock not found"))
                    continue

                logger.info(f"[{idx+1}/{group_data['stock_count']}] {ticker} {name}")

                # 데이터 수집
                collected, error = collect_ratios_for_stock(
                    stock=stock,
                    start_date=start_date,
                    end_date=end_date,
                    collector=collector
                )

                if collected > 0:
                    total_collected += collected
                    successful_stocks += 1
                    logger.info(f"  ✓ Saved {collected} records")
                else:
                    failed_stocks.append((ticker, name, error))
                    logger.warning(f"  ✗ No data collected")

                # 체크포인트 저장 (5개마다)
                if (idx + 1) % 5 == 0:
                    checkpoint_mgr.save_checkpoint({
                        'group_id': group_id,
                        'current_index': idx + 1,
                        'total_stocks': group_data['stock_count'],
                        'total_collected': total_collected,
                        'successful_stocks': successful_stocks,
                        'failed_stocks': len(failed_stocks),
                        'start_date': start_date,
                        'end_date': end_date,
                        'last_update': datetime.now()
                    })

                    logger.info(f"  Progress: {idx+1}/{group_data['stock_count']}, "
                               f"Collected: {total_collected:,} records")

        # 완료
        logger.info("=" * 70)
        logger.info(f"Group {group_id} 수집 완료")
        logger.info(f"  - 성공: {successful_stocks}/{group_data['stock_count']} 종목")
        logger.info(f"  - 실패: {len(failed_stocks)} 종목")
        logger.info(f"  - 총 레코드: {total_collected:,}건")

        if failed_stocks:
            logger.warning("\n실패한 종목:")
            for ticker, name, error in failed_stocks[:10]:
                logger.warning(f"  - {ticker} {name}: {error}")

            if len(failed_stocks) > 10:
                logger.warning(f"  ... and {len(failed_stocks) - 10} more")

            # 실패 목록 저장
            failed_file = checkpoint_dir / f"ratio_group_{group_id:03d}_failed.json"
            with open(failed_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'group_id': group_id,
                    'failed_count': len(failed_stocks),
                    'failed_stocks': [
                        {'ticker': t, 'name': n, 'error': e}
                        for t, n, e in failed_stocks
                    ]
                }, f, ensure_ascii=False, indent=2)

            logger.info(f"\n실패 목록 저장: {failed_file}")

        # 체크포인트 삭제
        checkpoint_mgr.clear_checkpoint()

        logger.info("=" * 70)

    except KeyboardInterrupt:
        logger.warning("\n중단되었습니다. 체크포인트가 저장되었습니다.")
        logger.info(f"재개하려면: python scripts/batch_collect_ratios.py --group-id {group_id} --years 3 --resume")

    except Exception as e:
        logger.error(f"오류 발생: {e}", exc_info=True)

    finally:
        db.close()


def main():
    """메인 실행 함수."""
    parser = argparse.ArgumentParser(description='그룹 기반 재무비율 배치 수집')
    parser.add_argument('--group-id', type=int, help='그룹 ID')
    parser.add_argument('--all', action='store_true', help='전체 그룹 순차 수집')
    parser.add_argument('--start', type=str, help='시작일 (YYYYMMDD)')
    parser.add_argument('--end', type=str, help='종료일 (YYYYMMDD, 기본: 오늘)')
    parser.add_argument('--years', type=int, help='최근 N년 수집 (start 대신 사용)')
    parser.add_argument('--resume', action='store_true', help='체크포인트에서 재개')

    args = parser.parse_args()

    if not args.group_id and not args.all:
        parser.error("--group-id 또는 --all 중 하나를 지정해야 합니다")

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
    logger.info("그룹 기반 재무비율 배치 수집")
    logger.info("=" * 70)
    logger.info(f"수집 기간: {start_date} ~ {end_date}")

    if args.all:
        # 전체 그룹 메타데이터 로드
        group_dir = project_root / "data" / "ratio_groups"
        metadata_file = group_dir / "ratio_groups_metadata.json"

        if not metadata_file.exists():
            logger.error(f"메타데이터 파일이 없습니다: {metadata_file}")
            logger.info("먼저 python scripts/create_ratio_groups.py를 실행하세요")
            return

        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata = json.load(f)

        logger.info(f"총 {metadata['total_groups']}개 그룹 순차 수집 시작\n")

        for group_info in metadata['groups']:
            group_id = group_info['group_id']
            logger.info(f"\n{'=' * 70}")
            logger.info(f"Group {group_id}/{metadata['total_groups']} 수집 시작")
            logger.info(f"{'=' * 70}\n")

            collect_group(group_id, start_date, end_date, resume=False)

            # 그룹 간 대기
            if group_id < metadata['total_groups']:
                logger.info(f"\n다음 그룹까지 5초 대기...\n")
                time.sleep(5)

        logger.info("\n" + "=" * 70)
        logger.info("전체 그룹 수집 완료!")
        logger.info("=" * 70)

    else:
        # 단일 그룹 수집
        logger.info(f"그룹 ID: {args.group_id}\n")
        collect_group(args.group_id, start_date, end_date, args.resume)


if __name__ == "__main__":
    main()
