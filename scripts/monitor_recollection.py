#!/usr/bin/env python3
"""재수집 진행 상황 모니터링.

빈 손익계산서가 얼마나 수정되었는지 실시간 확인합니다.

Usage:
    python scripts/monitor_recollection.py
    python scripts/monitor_recollection.py --watch  # 5초마다 갱신
"""

import sys
from pathlib import Path
from sqlalchemy import text, func
from datetime import datetime
import time

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from db.connection import SessionLocal
from models import FinancialStatement


def check_progress(db_session):
    """진행 상황 확인."""
    # 전체 재무제표 수
    total_stmts = db_session.query(func.count(FinancialStatement.id)).filter(
        FinancialStatement.fiscal_year.isnot(None)
    ).scalar()

    # 빈 손익계산서 재무제표 수
    empty_stmts = db_session.execute(
        text("SELECT COUNT(*) FROM financial_statements WHERE income_statement = '{\"profit\": {}, \"revenue\": {}, \"expenses\": {}}'::jsonb AND fiscal_year IS NOT NULL")
    ).scalar()

    # 수집 완료된 재무제표 (빈 것이 아닌 것)
    completed_stmts = total_stmts - empty_stmts

    # 최근 업데이트 시각
    recent_update = db_session.execute(
        text("SELECT MAX(updated_at) FROM financial_statements WHERE updated_at > NOW() - INTERVAL '10 minutes'")
    ).scalar()

    return {
        'total': total_stmts,
        'empty': empty_stmts,
        'completed': completed_stmts,
        'completion_rate': (completed_stmts / total_stmts * 100) if total_stmts > 0 else 0,
        'recent_update': recent_update
    }


def print_status(stats):
    """상태 출력."""
    print("=" * 80)
    print(f"📊 재수집 진행 상황 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print(f"전체 재무제표:        {stats['total']:,}건")
    print(f"수집 완료:           {stats['completed']:,}건")
    print(f"빈 손익계산서:       {stats['empty']:,}건")
    print(f"진행률:              {stats['completion_rate']:.1f}%")

    if stats['recent_update']:
        time_diff = datetime.now() - stats['recent_update'].replace(tzinfo=None)
        seconds_ago = int(time_diff.total_seconds())
        print(f"최근 업데이트:       {seconds_ago}초 전")

        if seconds_ago < 60:
            print(f"상태:                ✅ 활발히 진행 중")
        elif seconds_ago < 300:
            print(f"상태:                🔄 진행 중")
        else:
            print(f"상태:                ⏸️  멈춤 또는 완료")
    else:
        print(f"최근 업데이트:       없음")
        print(f"상태:                ⏸️  아직 시작 안함 또는 완료")

    print("=" * 80)

    # Progress bar
    bar_width = 60
    filled = int(bar_width * stats['completion_rate'] / 100)
    bar = '█' * filled + '░' * (bar_width - filled)
    print(f"[{bar}] {stats['completion_rate']:.1f}%")
    print("=" * 80)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="재수집 진행 상황 모니터링")
    parser.add_argument('--watch', '-w', action='store_true', help='5초마다 갱신')
    parser.add_argument('--interval', '-i', type=int, default=5, help='갱신 간격 (초)')

    args = parser.parse_args()

    db = SessionLocal()

    try:
        if args.watch:
            print("📊 실시간 모니터링 시작 (Ctrl+C로 종료)")
            print()

            while True:
                stats = check_progress(db)
                # Clear screen (ANSI escape code)
                print("\033[2J\033[H", end="")
                print_status(stats)

                if stats['empty'] == 0:
                    print("\n🎉 모든 재무제표 수집 완료!")
                    break

                time.sleep(args.interval)
        else:
            stats = check_progress(db)
            print_status(stats)

            if stats['empty'] > 0:
                print("\n💡 실시간 모니터링:")
                print(f"  python scripts/monitor_recollection.py --watch")

    except KeyboardInterrupt:
        print("\n\n모니터링 종료")
    finally:
        db.close()


if __name__ == "__main__":
    main()
