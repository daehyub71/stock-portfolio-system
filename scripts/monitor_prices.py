#!/usr/bin/env python3
"""시세 데이터 수집 모니터링 대시보드.

Usage:
    # 전체 그룹 상태 확인
    python scripts/monitor_prices.py

    # 자동 새로고침 (5초마다)
    python scripts/monitor_prices.py --watch --interval 5
"""

import sys
from pathlib import Path
import argparse
import json
from datetime import datetime
import time
from typing import Dict, List, Optional
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Disable SQLAlchemy logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

from db.connection import SessionLocal
from models import DailyPrice, Stock
from sqlalchemy import func


class PriceDashboard:
    """시세 데이터 수집 모니터링 대시보드."""

    def __init__(self):
        self.checkpoint_dir = project_root / 'data' / 'checkpoints'
        self.groups_dir = project_root / 'data' / 'price_groups'

    def load_checkpoint(self, group_id: int) -> Optional[Dict]:
        """체크포인트 로드."""
        checkpoint_file = self.checkpoint_dir / f'price_checkpoint_group_{group_id}.json'
        if not checkpoint_file.exists():
            return None

        with open(checkpoint_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def load_group_info(self, group_id: int) -> Optional[Dict]:
        """그룹 정보 로드."""
        group_file = self.groups_dir / f'price_group_{group_id}.json'
        if not group_file.exists():
            return None

        with open(group_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def get_collected_stocks_for_group(self, group_info: Dict) -> int:
        """그룹에서 이미 수집된 종목 수 확인."""
        db = SessionLocal()
        try:
            tickers = [s['ticker'] for s in group_info['stocks']]

            # 시세 데이터가 있는 종목 수 카운트
            count = db.query(func.count(func.distinct(DailyPrice.stock_id))).join(
                Stock, Stock.id == DailyPrice.stock_id
            ).filter(
                Stock.ticker.in_(tickers)
            ).scalar()

            return count or 0
        finally:
            db.close()

    def get_database_stats(self) -> Dict:
        """데이터베이스 통계."""
        db = SessionLocal()

        try:
            # 총 레코드 수
            total_records = db.query(DailyPrice).count()

            # 데이터가 있는 종목 수
            stocks_with_data = db.query(
                func.count(func.distinct(DailyPrice.stock_id))
            ).scalar()

            # 총 종목 수
            total_stocks = db.query(Stock).count()

            # 평균 레코드 수 (종목당)
            avg_records_per_stock = total_records / stocks_with_data if stocks_with_data > 0 else 0

            return {
                'total_records': total_records,
                'stocks_with_data': stocks_with_data,
                'total_stocks': total_stocks,
                'coverage_pct': (stocks_with_data / total_stocks * 100) if total_stocks > 0 else 0,
                'avg_records_per_stock': avg_records_per_stock
            }
        finally:
            db.close()

    def get_all_groups_status(self) -> List[Dict]:
        """전체 그룹 상태 조회."""
        groups_meta_file = self.groups_dir / 'groups_meta.json'

        if not groups_meta_file.exists():
            return []

        with open(groups_meta_file, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        statuses = []

        for group_id in range(1, meta['num_groups'] + 1):
            group_info = self.load_group_info(group_id)
            if not group_info:
                continue

            checkpoint = self.load_checkpoint(group_id)
            collected_count = self.get_collected_stocks_for_group(group_info)

            status = {
                'group_id': group_id,
                'size': group_info['size'],
                'collected': collected_count,
                'progress': 0.0,
                'status': 'pending',
                'success': 0,
                'failed': 0,
                'total_records': 0
            }

            if checkpoint:
                # 진행 중
                status['status'] = 'in_progress'
                status['collected'] = checkpoint.get('processed', 0)
                status['success'] = checkpoint.get('success', 0)
                status['failed'] = checkpoint.get('failed', 0)
                status['total_records'] = checkpoint.get('total_records', 0)
                status['progress'] = (status['collected'] / group_info['size']) * 100

                # 예상 남은 시간 계산
                if 'start_time' in checkpoint and checkpoint.get('processed', 0) > 0:
                    start_time = datetime.fromisoformat(checkpoint['start_time'])
                    elapsed = (datetime.now() - start_time).total_seconds()
                    avg_time_per_stock = elapsed / checkpoint['processed']
                    remaining_stocks = group_info['size'] - checkpoint['processed']
                    eta_seconds = avg_time_per_stock * remaining_stocks
                    status['eta_minutes'] = eta_seconds / 60
            elif collected_count > 0:
                # 완료됨 (체크포인트는 없지만 데이터는 있음)
                status['status'] = 'completed'
                status['collected'] = collected_count
                status['success'] = collected_count
                status['failed'] = group_info['size'] - collected_count
                status['progress'] = 100.0

            statuses.append(status)

        return statuses

    def print_dashboard(self):
        """대시보드 출력."""
        # Clear screen
        print('\033[2J\033[H', end='')

        print("=" * 100)
        print("시세 데이터 수집 모니터링 대시보드".center(100))
        print("=" * 100)
        print()

        # 데이터베이스 통계
        db_stats = self.get_database_stats()
        print("📊 전체 데이터베이스 통계")
        print("-" * 100)
        print(f"총 레코드 수:        {db_stats['total_records']:>12,}개")
        print(f"데이터 있는 종목:    {db_stats['stocks_with_data']:>12,}개 / {db_stats['total_stocks']:,}개 ({db_stats['coverage_pct']:.1f}%)")
        print(f"종목당 평균 레코드:  {db_stats['avg_records_per_stock']:>12,.0f}개")
        print()

        # 그룹별 진행 상황
        print("📦 그룹별 진행 상황")
        print("-" * 100)
        print(f"{'그룹':>6} | {'종목수':>6} | {'진행':>6} | {'성공':>6} | {'실패':>6} | {'레코드':>12} | {'진행률':>8} | {'상태':^12} | {'예상 남은 시간'}")
        print("-" * 100)

        groups = self.get_all_groups_status()
        total_size = 0
        total_collected = 0
        total_success = 0
        total_failed = 0
        total_records = 0

        for group in groups:
            status_emoji = {
                'pending': '⏸️  대기중',
                'in_progress': '🔄 진행중',
                'completed': '✅ 완료'
            }

            status_str = status_emoji.get(group['status'], group['status'])
            eta_str = ''
            if 'eta_minutes' in group:
                eta_str = f"약 {group['eta_minutes']:.0f}분 남음"

            print(
                f"Group {group['group_id']:>2} | "
                f"{group['size']:>6} | "
                f"{group['collected']:>6} | "
                f"{group['success']:>6} | "
                f"{group['failed']:>6} | "
                f"{group['total_records']:>12,} | "
                f"{group['progress']:>7.1f}% | "
                f"{status_str:^12} | "
                f"{eta_str}"
            )

            total_size += group['size']
            total_collected += group['collected']
            total_success += group['success']
            total_failed += group['failed']
            total_records += group['total_records']

        print("-" * 100)
        overall_progress = (total_collected / total_size * 100) if total_size > 0 else 0
        print(
            f"{'합계':>6} | "
            f"{total_size:>6} | "
            f"{total_collected:>6} | "
            f"{total_success:>6} | "
            f"{total_failed:>6} | "
            f"{total_records:>12,} | "
            f"{overall_progress:>7.1f}%"
        )
        print("=" * 100)
        print()
        print(f"마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()


def main():
    parser = argparse.ArgumentParser(description='시세 데이터 수집 모니터링 대시보드')
    parser.add_argument('--watch', action='store_true', help='자동 새로고침 모드')
    parser.add_argument('--interval', type=int, default=5, help='새로고침 간격 (초)')
    args = parser.parse_args()

    dashboard = PriceDashboard()

    if args.watch:
        try:
            while True:
                dashboard.print_dashboard()
                print(f"({args.interval}초 후 자동 새로고침... Ctrl+C로 종료)")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n\n모니터링 종료")
    else:
        dashboard.print_dashboard()


if __name__ == '__main__':
    main()
