#!/usr/bin/env python3
"""배치 수집 진행 상황 모니터링 대시보드.

전체 그룹의 수집 진행 상황을 한눈에 볼 수 있는 대시보드입니다.

Usage:
    # 전체 그룹 상태 확인
    python scripts/monitoring_dashboard.py

    # 자동 새로고침 (5초마다)
    python scripts/monitoring_dashboard.py --watch --interval 5

    # 상세 모드
    python scripts/monitoring_dashboard.py --detailed
"""

import sys
from pathlib import Path
import argparse
import json
from datetime import datetime, timedelta
import time
from typing import Dict, List, Optional
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Disable SQLAlchemy logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

from db.connection import SessionLocal
from models import FinancialStatement, Stock
from sqlalchemy import func


class Dashboard:
    """모니터링 대시보드 클래스."""

    def __init__(self, detailed: bool = False):
        """Initialize dashboard.

        Args:
            detailed: Show detailed information
        """
        self.detailed = detailed
        self.checkpoint_dir = project_root / 'data' / 'checkpoints'
        self.groups_dir = project_root / 'data' / 'batch_groups'

    def load_checkpoint(self, group_id: int) -> Optional[Dict]:
        """Load checkpoint for a group.

        Args:
            group_id: Group ID

        Returns:
            Checkpoint data or None
        """
        checkpoint_file = self.checkpoint_dir / f'checkpoint_group_{group_id}.json'
        if not checkpoint_file.exists():
            return None

        with open(checkpoint_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def load_group_info(self, group_id: int) -> Optional[Dict]:
        """Load group information.

        Args:
            group_id: Group ID

        Returns:
            Group data or None
        """
        group_file = self.groups_dir / f'group_{group_id}.json'
        if not group_file.exists():
            return None

        with open(group_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def get_database_stats(self) -> Dict:
        """Get database statistics.

        Returns:
            Dictionary with database stats
        """
        db = SessionLocal()

        try:
            # Total financial statements
            total_statements = db.query(FinancialStatement).count()

            # Unique stocks with data
            stocks_with_data = db.query(
                func.count(func.distinct(FinancialStatement.stock_id))
            ).scalar()

            # By year
            by_year = db.query(
                FinancialStatement.fiscal_year,
                func.count(FinancialStatement.id)
            ).group_by(
                FinancialStatement.fiscal_year
            ).order_by(
                FinancialStatement.fiscal_year.desc()
            ).all()

            # Total active stocks
            total_active_stocks = db.query(Stock).filter_by(is_active=True).count()

            return {
                'total_statements': total_statements,
                'stocks_with_data': stocks_with_data,
                'total_active_stocks': total_active_stocks,
                'by_year': {year: count for year, count in by_year},
                'coverage': (stocks_with_data / total_active_stocks * 100) if total_active_stocks > 0 else 0
            }

        finally:
            db.close()

    def get_collected_stocks_for_group(self, group_info: Dict) -> int:
        """Get number of stocks in this group that have financial statements.

        Args:
            group_info: Group information

        Returns:
            Number of stocks with financial statements
        """
        db = SessionLocal()
        try:
            tickers = [s['ticker'] for s in group_info['stocks']]

            # Count stocks that have financial statements
            count = db.query(func.count(func.distinct(FinancialStatement.stock_id))).join(
                Stock, Stock.id == FinancialStatement.stock_id
            ).filter(
                Stock.ticker.in_(tickers)
            ).scalar()

            return count or 0
        finally:
            db.close()

    def get_all_groups_status(self) -> List[Dict]:
        """Get status for all groups.

        Returns:
            List of group status dictionaries
        """
        groups_status = []

        for group_id in range(1, 7):  # Groups 1-6
            group_info = self.load_group_info(group_id)
            if not group_info:
                continue

            checkpoint = self.load_checkpoint(group_id)

            status = {
                'group_id': group_id,
                'size': group_info['size'],
                'start_index': group_info['start_index'],
                'end_index': group_info['end_index']
            }

            # Check actual database status
            collected_count = self.get_collected_stocks_for_group(group_info)

            if checkpoint:
                # In progress (checkpoint exists)
                status['status'] = 'in_progress'
                status['processed'] = checkpoint.get('processed', 0)
                status['success'] = checkpoint.get('success', 0)
                status['failed'] = checkpoint.get('failed', 0)
                status['skipped'] = checkpoint.get('skipped', 0)
                status['progress'] = (checkpoint.get('processed', 0) / group_info['size'] * 100)
                status['success_rate'] = (checkpoint.get('success', 0) / checkpoint.get('processed', 1) * 100)

                # Time estimation
                if 'start_time' in checkpoint:
                    start_time = datetime.fromisoformat(checkpoint['start_time'])
                    now = datetime.now()
                    elapsed = (now - start_time).total_seconds()

                    status['elapsed'] = elapsed
                    status['start_time'] = checkpoint['start_time']

                    if checkpoint.get('processed', 0) > 0:
                        avg_time = elapsed / checkpoint['processed']
                        remaining = group_info['size'] - checkpoint['processed']
                        est_remaining = avg_time * remaining
                        status['eta'] = (now + timedelta(seconds=est_remaining)).isoformat()
                        status['remaining_seconds'] = est_remaining

                # Errors
                if self.detailed and checkpoint.get('errors'):
                    status['recent_errors'] = checkpoint['errors'][-5:]  # Last 5 errors

            elif collected_count > 0:
                # No checkpoint but has data = completed
                status['status'] = 'completed'
                status['processed'] = group_info['size']
                status['success'] = collected_count
                status['failed'] = group_info['size'] - collected_count
                status['skipped'] = 0
                status['progress'] = 100.0
                status['success_rate'] = (collected_count / group_info['size'] * 100)

            else:
                # Not started (no checkpoint and no data)
                status['status'] = 'pending'
                status['processed'] = 0
                status['success'] = 0
                status['failed'] = 0
                status['skipped'] = 0
                status['progress'] = 0.0
                status['success_rate'] = 0.0

            groups_status.append(status)

        return groups_status

    def format_timedelta(self, seconds: float) -> str:
        """Format seconds to human readable string.

        Args:
            seconds: Seconds

        Returns:
            Formatted string
        """
        seconds = int(seconds)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        if hours > 0:
            return f"{hours}시간 {minutes}분 {secs}초"
        elif minutes > 0:
            return f"{minutes}분 {secs}초"
        else:
            return f"{secs}초"

    def print_header(self):
        """Print dashboard header."""
        print("\n")
        print("╔" + "═" * 78 + "╗")
        print("║" + f" {'배치 수집 모니터링 대시보드':^74} " + "║")
        print("╚" + "═" * 78 + "╝")
        print()

    def print_database_stats(self, db_stats: Dict):
        """Print database statistics.

        Args:
            db_stats: Database statistics
        """
        print("📊 데이터베이스 현황")
        print("─" * 80)
        print(f"  총 재무제표 수: {db_stats['total_statements']:,}개")
        print(f"  재무제표 보유 종목: {db_stats['stocks_with_data']:,}개 / {db_stats['total_active_stocks']:,}개")
        print(f"  커버리지: {db_stats['coverage']:.1f}%")

        if db_stats['by_year']:
            print(f"\n  연도별 재무제표:")
            for year in sorted(db_stats['by_year'].keys(), reverse=True):
                count = db_stats['by_year'][year]
                print(f"    - {year}년: {count:,}개")

        print()

    def print_overall_progress(self, groups: List[Dict]):
        """Print overall progress.

        Args:
            groups: List of group status
        """
        total_stocks = sum(g['size'] for g in groups)
        total_processed = sum(g['processed'] for g in groups)
        total_success = sum(g['success'] for g in groups)
        total_failed = sum(g['failed'] for g in groups)

        overall_progress = (total_processed / total_stocks * 100) if total_stocks > 0 else 0
        overall_success_rate = (total_success / total_processed * 100) if total_processed > 0 else 0

        print("📈 전체 진행 상황")
        print("─" * 80)
        print(f"  총 종목 수: {total_stocks:,}개")
        print(f"  처리 완료: {total_processed:,}개 ({overall_progress:.1f}%)")
        print(f"  성공: {total_success:,}개 | 실패: {total_failed:,}개")
        print(f"  성공률: {overall_success_rate:.1f}%")

        # Progress bar
        bar_width = 60
        filled = int(bar_width * overall_progress / 100)
        bar = "█" * filled + "░" * (bar_width - filled)
        print(f"\n  [{bar}] {overall_progress:.1f}%")
        print()

    def print_groups_table(self, groups: List[Dict]):
        """Print groups status table.

        Args:
            groups: List of group status
        """
        print("📋 그룹별 진행 상황")
        print("─" * 80)

        # Header
        print(f"{'그룹':^8} {'상태':^12} {'진행률':^10} {'성공':^8} {'실패':^8} {'성공률':^10} {'상태':^15}")
        print("─" * 80)

        for group in groups:
            group_id = group['group_id']
            status = group['status']

            # Status emoji
            if status == 'completed':
                status_emoji = "✅ 완료"
            elif status == 'in_progress':
                status_emoji = "🔄 진행중"
            else:
                status_emoji = "⏳ 대기중"

            # Status text
            if status == 'pending':
                status_text = "-"
            elif status == 'in_progress' and 'remaining_seconds' in group:
                status_text = f"남음 {self.format_timedelta(group['remaining_seconds'])}"
            elif status == 'completed' and 'total_time' in group:
                status_text = f"완료 {self.format_timedelta(group['total_time'])}"
            else:
                status_text = "-"

            print(f"Group {group_id:>2}  {status_emoji:^12} "
                  f"{group['progress']:>6.1f}%  "
                  f"{group['success']:>6}  "
                  f"{group['failed']:>6}  "
                  f"{group['success_rate']:>7.1f}%  "
                  f"{status_text:^15}")

        print()

    def print_detailed_errors(self, groups: List[Dict]):
        """Print detailed error information.

        Args:
            groups: List of group status
        """
        if not self.detailed:
            return

        print("⚠️  최근 오류 (그룹별)")
        print("─" * 80)

        has_errors = False
        for group in groups:
            if group.get('recent_errors'):
                has_errors = True
                print(f"\nGroup {group['group_id']}:")
                for error in group['recent_errors']:
                    ticker = error.get('ticker', 'N/A')
                    name = error.get('name', 'N/A')
                    error_msg = error.get('error', 'Unknown')
                    print(f"  - {ticker} ({name}): {error_msg}")

        if not has_errors:
            print("  오류 없음")

        print()

    def print_recommendations(self, groups: List[Dict]):
        """Print recommendations.

        Args:
            groups: List of group status
        """
        print("💡 권장 사항")
        print("─" * 80)

        in_progress = [g for g in groups if g['status'] == 'in_progress']
        pending = [g for g in groups if g['status'] == 'pending']
        completed = [g for g in groups if g['status'] == 'completed']

        if in_progress:
            group_ids = ', '.join(f"Group {g['group_id']}" for g in in_progress)
            print(f"  🔄 진행중인 그룹: {group_ids}")
            print(f"     → 모니터링: python scripts/monitor_collection.py --group {in_progress[0]['group_id']}")

        if pending:
            next_group = pending[0]['group_id']
            print(f"\n  ⏳ 다음 그룹: Group {next_group}")
            print(f"     → 시작: python scripts/batch_collect_financials.py --group {next_group} --years 2024 2023")

        if completed and not in_progress and not pending:
            print("  ✅ 모든 그룹 수집 완료!")
            print("     → 데이터 품질 체크: python scripts/data_quality_check.py")

        if len(completed) > 0 and len(pending) > 0:
            total_completed = sum(g['success'] for g in completed)
            print(f"\n  📊 현재까지 {total_completed:,}개 종목의 재무제표 수집 완료")

        print()

    def display(self):
        """Display dashboard."""
        # Clear screen (optional)
        # print("\033[2J\033[H")

        self.print_header()

        # Database stats
        db_stats = self.get_database_stats()
        self.print_database_stats(db_stats)

        # Groups status
        groups = self.get_all_groups_status()

        # Overall progress
        self.print_overall_progress(groups)

        # Groups table
        self.print_groups_table(groups)

        # Detailed errors
        if self.detailed:
            self.print_detailed_errors(groups)

        # Recommendations
        self.print_recommendations(groups)

        # Footer
        print("─" * 80)
        print(f"업데이트 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("─" * 80)


def main():
    """메인 함수."""
    parser = argparse.ArgumentParser(
        description="Monitoring dashboard for batch collection"
    )

    parser.add_argument(
        "--watch",
        action="store_true",
        help="Auto-refresh mode"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Refresh interval in seconds (default: 5)"
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Show detailed error information"
    )

    args = parser.parse_args()

    dashboard = Dashboard(detailed=args.detailed)

    try:
        if args.watch:
            while True:
                dashboard.display()
                print(f"\n다음 업데이트: {args.interval}초 후... (Ctrl+C로 종료)\n")
                time.sleep(args.interval)
        else:
            dashboard.display()

    except KeyboardInterrupt:
        print("\n\n대시보드 종료")


if __name__ == "__main__":
    main()
