#!/usr/bin/env python3
"""배치 시세 데이터 수집 스크립트.

KIS API를 사용하여 그룹별 종목의 10년치 일별 시세 데이터 수집.
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging
import argparse

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from collectors.pykrx_price_collector import PyKRXPriceCollector
from db.connection import SessionLocal
from models import Stock, DailyPrice

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
        """
        Args:
            checkpoint_dir: 체크포인트 저장 디렉토리
        """
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(self, group_id: int, checkpoint_data: Dict):
        """체크포인트 저장."""
        checkpoint_path = self.checkpoint_dir / f"price_checkpoint_group_{group_id}.json"

        # Convert datetime objects to strings for JSON serialization
        serializable_data = checkpoint_data.copy()
        if 'start_time' in serializable_data and serializable_data['start_time']:
            serializable_data['start_time'] = serializable_data['start_time'].isoformat()
        if 'end_time' in serializable_data and serializable_data['end_time']:
            serializable_data['end_time'] = serializable_data['end_time'].isoformat()

        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(serializable_data, f, ensure_ascii=False, indent=2)

    def load_checkpoint(self, group_id: int) -> Optional[Dict]:
        """체크포인트 로드."""
        checkpoint_path = self.checkpoint_dir / f"price_checkpoint_group_{group_id}.json"
        if checkpoint_path.exists():
            with open(checkpoint_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def clear_checkpoint(self, group_id: int):
        """체크포인트 삭제."""
        checkpoint_path = self.checkpoint_dir / f"price_checkpoint_group_{group_id}.json"
        if checkpoint_path.exists():
            checkpoint_path.unlink()


class BatchPriceCollector:
    """배치 시세 수집 클래스."""

    def __init__(
        self,
        group_id: int,
        years_back: int = 10,
        resume: bool = False
    ):
        """
        Args:
            group_id: 그룹 ID (1-6)
            years_back: 수집할 연도 수 (기본값: 10년)
            resume: 체크포인트에서 재개 여부
        """
        self.group_id = group_id
        self.years_back = years_back
        self.resume = resume

        # 수집 기간 설정 (pykrx는 장기간 데이터 조회 가능)
        self.end_date = datetime.now().date()
        self.start_date = self.end_date - timedelta(days=365 * years_back)
        self.total_days = (self.end_date - self.start_date).days

        # 컴포넌트 초기화
        self.collector = PyKRXPriceCollector()
        self.checkpoint_manager = CheckpointManager(project_root / 'data' / 'checkpoints')

        # 그룹 정보 로드
        self.group_info = self.load_group_info()
        self.stocks = self.group_info['stocks']

        # 통계 초기화
        self.stats = {
            'group_id': group_id,
            'total': len(self.stocks),
            'processed': 0,
            'success': 0,
            'failed': 0,
            'total_records': 0,
            'start_time': None,
            'end_time': None,
            'failed_stocks': []
        }

    def load_group_info(self) -> Dict:
        """그룹 정보 로드."""
        group_file = project_root / 'data' / 'price_groups' / f'price_group_{self.group_id}.json'

        if not group_file.exists():
            raise FileNotFoundError(f"그룹 파일이 없습니다: {group_file}")

        with open(group_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def collect_stock_prices(self, stock_info: Dict) -> Dict:
        """단일 종목 시세 수집.

        pykrx는 장기간 데이터를 한 번에 조회 가능.
        """
        ticker = stock_info['ticker']
        name = stock_info['name']

        try:
            # pykrx로 시세 수집 (전체 기간)
            result = self.collector.collect_and_save(
                ticker=ticker,
                start_date=self.start_date,
                end_date=self.end_date
            )

            if result['success']:
                saved_count = result.get('saved', 0)
                updated_count = result.get('updated', 0)
                total_count = saved_count + updated_count

                logger.info(f"  ✅ {ticker} ({name}): {total_count}개 레코드 (신규: {saved_count}, 갱신: {updated_count})")
                return {
                    'success': True,
                    'records': total_count
                }
            else:
                logger.warning(f"  ⚠️  {ticker} ({name}): 데이터 없음")
                return {
                    'success': False,
                    'records': 0
                }

        except Exception as e:
            logger.error(f"  ❌ {ticker} ({name}): {str(e)}")
            return {
                'success': False,
                'records': 0
            }

    def collect_all(self):
        """전체 그룹 수집."""
        logger.info("=" * 80)
        logger.info(f"배치 시세 수집 시작 - Group {self.group_id}")
        logger.info(f"총 종목 수: {len(self.stocks)}")
        logger.info(f"수집 기간: {self.start_date} ~ {self.end_date} ({self.years_back}년)")
        logger.info(f"데이터 소스: pykrx (KRX 공개 데이터)")
        logger.info("=" * 80)

        self.stats['start_time'] = datetime.now()

        # 체크포인트에서 재개
        start_idx = 0
        if self.resume:
            checkpoint = self.checkpoint_manager.load_checkpoint(self.group_id)
            if checkpoint:
                start_idx = checkpoint.get('processed', 0)
                self.stats.update(checkpoint)
                logger.info(f"체크포인트에서 재개: {start_idx}/{len(self.stocks)}")

        # 순차 수집
        for i in range(start_idx, len(self.stocks)):
            stock_info = self.stocks[i]
            ticker = stock_info['ticker']
            name = stock_info['name']

            logger.info(f"[{i+1}/{len(self.stocks)}] Processing {ticker} ({name})...")

            # 시세 수집
            result = self.collect_stock_prices(stock_info)

            # 통계 업데이트
            self.stats['processed'] += 1

            if result['success']:
                self.stats['success'] += 1
                self.stats['total_records'] += result['records']
            else:
                self.stats['failed'] += 1
                self.stats['failed_stocks'].append({
                    'ticker': ticker,
                    'name': name
                })

            # 체크포인트 저장 (매 10개)
            if (i + 1) % 10 == 0:
                self.checkpoint_manager.save_checkpoint(self.group_id, self.stats)

            # 진행 상황 출력 (매 50개)
            if (i + 1) % 50 == 0:
                elapsed = (datetime.now() - self.stats['start_time']).total_seconds()
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                remaining = (len(self.stocks) - (i + 1)) / rate if rate > 0 else 0

                logger.info("")
                logger.info(f"진행 상황: {i+1}/{len(self.stocks)} ({(i+1)/len(self.stocks)*100:.1f}%)")
                logger.info(f"성공: {self.stats['success']} | 실패: {self.stats['failed']}")
                logger.info(f"총 레코드: {self.stats['total_records']:,}개")
                logger.info(f"처리 속도: {rate:.2f}개/초 | 남은 시간: {int(remaining/60)}분 {int(remaining%60)}초")
                logger.info("")

            # Rate limiting (KIS API: 초당 20건)
            time.sleep(0.05)

        self.stats['end_time'] = datetime.now()

        # 최종 체크포인트 저장
        self.checkpoint_manager.save_checkpoint(self.group_id, self.stats)

        self.print_summary()

    def print_summary(self):
        """최종 결과 출력."""
        elapsed = (self.stats['end_time'] - self.stats['start_time']).total_seconds()

        logger.info("")
        logger.info("=" * 80)
        logger.info("배치 수집 완료")
        logger.info("=" * 80)
        logger.info(f"총 종목 수: {self.stats['total']}")
        logger.info(f"성공: {self.stats['success']}")
        logger.info(f"실패: {self.stats['failed']}")
        logger.info(f"총 레코드: {self.stats['total_records']:,}개")
        logger.info("")
        logger.info(f"소요 시간: {int(elapsed)}초 ({elapsed/60:.1f}분)")
        logger.info(f"성공률: {self.stats['success']/self.stats['total']*100:.1f}%")
        logger.info(f"종목당 평균 레코드: {self.stats['total_records']/self.stats['success']:.0f}개" if self.stats['success'] > 0 else "N/A")
        logger.info("=" * 80)

        # 실패 종목 출력
        if self.stats['failed_stocks']:
            logger.info(f"\n❌ 실패한 종목 ({len(self.stats['failed_stocks'])}):")
            for stock in self.stats['failed_stocks'][:10]:  # 처음 10개만
                logger.info(f"  - {stock['ticker']}: {stock['name']}")
            if len(self.stats['failed_stocks']) > 10:
                logger.info(f"  ... 외 {len(self.stats['failed_stocks']) - 10}개")


def main():
    """메인 실행 함수."""
    parser = argparse.ArgumentParser(description='배치 시세 데이터 수집')
    parser.add_argument(
        '--group',
        type=int,
        required=True,
        choices=range(1, 7),
        help='그룹 ID (1-6)'
    )
    parser.add_argument(
        '--years',
        type=int,
        default=10,
        help='수집할 연도 수 (기본값: 10년)'
    )
    parser.add_argument(
        '--resume',
        action='store_true',
        help='체크포인트에서 재개'
    )

    args = parser.parse_args()

    collector = BatchPriceCollector(
        group_id=args.group,
        years_back=args.years,
        resume=args.resume
    )

    try:
        collector.collect_all()
    except KeyboardInterrupt:
        logger.warning("\n\n사용자에 의해 중단되었습니다.")
        collector.checkpoint_manager.save_checkpoint(collector.group_id, collector.stats)
        logger.info("체크포인트가 저장되었습니다. --resume 옵션으로 재개할 수 있습니다.")
        sys.exit(1)


if __name__ == '__main__':
    main()
