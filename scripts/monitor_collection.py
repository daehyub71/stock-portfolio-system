#!/usr/bin/env python3
"""배치 수집 진행 상황을 모니터링하는 스크립트.

실시간으로 수집 진행 상황, 성공/실패 통계, 예상 완료 시간을 표시합니다.

Usage:
    python scripts/monitor_collection.py --group 1
"""

import sys
from pathlib import Path
import argparse
import json
from datetime import datetime, timedelta
import time

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def print_header(title: str):
    """Print formatted header."""
    print("\n")
    print("╔" + "═" * 68 + "╗")
    print("║" + f" {title:^66} " + "║")
    print("╚" + "═" * 68 + "╝")
    print()


def load_checkpoint(group_id: int) -> dict:
    """Load checkpoint data.

    Args:
        group_id: Group ID

    Returns:
        Checkpoint data or empty dict if not found
    """
    checkpoint_file = project_root / 'data' / 'checkpoints' / f'checkpoint_group_{group_id}.json'

    if not checkpoint_file.exists():
        return {}

    with open(checkpoint_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_group_info(group_id: int) -> dict:
    """Load group information.

    Args:
        group_id: Group ID

    Returns:
        Group data
    """
    group_file = project_root / 'data' / 'batch_groups' / f'group_{group_id}.json'

    if not group_file.exists():
        raise FileNotFoundError(f"Group file not found: {group_file}")

    with open(group_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def estimate_completion_time(checkpoint: dict, total_stocks: int) -> tuple:
    """Estimate completion time.

    Args:
        checkpoint: Checkpoint data
        total_stocks: Total number of stocks

    Returns:
        Tuple of (estimated_completion_time, time_remaining)
    """
    if not checkpoint or checkpoint.get('processed', 0) == 0:
        return None, None

    start_time = datetime.fromisoformat(checkpoint['start_time'])
    now = datetime.now()
    elapsed = (now - start_time).total_seconds()

    processed = checkpoint['processed']
    remaining = total_stocks - processed

    avg_time_per_stock = elapsed / processed
    estimated_remaining_seconds = avg_time_per_stock * remaining

    estimated_completion = now + timedelta(seconds=estimated_remaining_seconds)
    time_remaining = timedelta(seconds=estimated_remaining_seconds)

    return estimated_completion, time_remaining


def format_timedelta(td: timedelta) -> str:
    """Format timedelta to human readable string.

    Args:
        td: Timedelta

    Returns:
        Formatted string
    """
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    if hours > 0:
        return f"{hours}시간 {minutes}분 {seconds}초"
    elif minutes > 0:
        return f"{minutes}분 {seconds}초"
    else:
        return f"{seconds}초"


def print_status(group_id: int, checkpoint: dict, group_info: dict):
    """Print current status.

    Args:
        group_id: Group ID
        checkpoint: Checkpoint data
        group_info: Group information
    """
    total_stocks = group_info['size']

    # Clear screen (optional)
    # print("\033[2J\033[H")

    print_header(f"배치 수집 모니터링 - Group {group_id}")

    if not checkpoint:
        print("⚠️  수집이 아직 시작되지 않았습니다.")
        print(f"\n시작하려면: python scripts/batch_collect_financials.py --group {group_id}")
        return

    # Basic info
    print(f"그룹 정보:")
    print(f"  - 그룹 ID: {group_id}")
    print(f"  - 총 종목 수: {total_stocks:,}")
    print(f"  - 종목 범위: {group_info['start_index']}-{group_info['end_index']}")

    # Progress
    processed = checkpoint.get('processed', 0)
    success = checkpoint.get('success', 0)
    failed = checkpoint.get('failed', 0)
    skipped = checkpoint.get('skipped', 0)

    progress_pct = (processed / total_stocks * 100) if total_stocks > 0 else 0
    success_rate = (success / processed * 100) if processed > 0 else 0

    print(f"\n진행 상황:")
    print(f"  - 처리 완료: {processed:,} / {total_stocks:,} ({progress_pct:.1f}%)")
    print(f"  - 성공: {success:,}")
    print(f"  - 실패: {failed:,}")
    print(f"  - 건너뛰기: {skipped:,}")
    print(f"  - 성공률: {success_rate:.1f}%")

    # Progress bar
    bar_width = 50
    filled = int(bar_width * progress_pct / 100)
    bar = "█" * filled + "░" * (bar_width - filled)
    print(f"\n  [{bar}] {progress_pct:.1f}%")

    # Time info
    start_time = datetime.fromisoformat(checkpoint['start_time'])
    now = datetime.now()
    elapsed = now - start_time

    print(f"\n시간 정보:")
    print(f"  - 시작 시간: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  - 경과 시간: {format_timedelta(elapsed)}")

    # Estimate completion
    est_completion, time_remaining = estimate_completion_time(checkpoint, total_stocks)
    if est_completion:
        print(f"  - 예상 완료: {est_completion.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  - 남은 시간: {format_timedelta(time_remaining)}")

    # Recent errors
    errors = checkpoint.get('errors', [])
    if errors:
        print(f"\n최근 오류 ({len(errors)} 건):")
        for error in errors[-5:]:  # Show last 5
            print(f"  - {error.get('ticker', 'N/A')} ({error.get('name', 'N/A')}): {error.get('error', 'Unknown error')}")

    print("\n" + "=" * 70)


def monitor_loop(group_id: int, interval: int = 10):
    """Continuously monitor collection progress.

    Args:
        group_id: Group ID
        interval: Update interval in seconds
    """
    try:
        group_info = load_group_info(group_id)
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

    try:
        while True:
            checkpoint = load_checkpoint(group_id)
            print_status(group_id, checkpoint, group_info)

            # Check if completed
            if checkpoint and checkpoint.get('processed', 0) >= group_info['size']:
                print("\n✅ 수집 완료!")
                break

            print(f"\n다음 업데이트: {interval}초 후... (Ctrl+C로 종료)")
            time.sleep(interval)
            print("\n" * 3)  # Clear some space

    except KeyboardInterrupt:
        print("\n\n모니터링 종료")


def main():
    """메인 함수."""
    parser = argparse.ArgumentParser(
        description="Monitor batch collection progress"
    )

    parser.add_argument(
        "--group",
        type=int,
        required=True,
        help="Group ID to monitor (1-6)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=10,
        help="Update interval in seconds (default: 10)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Print status once and exit"
    )

    args = parser.parse_args()

    # Validate group ID
    if args.group < 1 or args.group > 6:
        print("❌ Invalid group ID. Must be between 1 and 6.")
        sys.exit(1)

    try:
        group_info = load_group_info(args.group)
        checkpoint = load_checkpoint(args.group)

        if args.once:
            print_status(args.group, checkpoint, group_info)
        else:
            monitor_loop(args.group, args.interval)

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
