#!/usr/bin/env python3
"""전체 그룹 재무제표 배치 수집 스크립트.

모든 배치 그룹에 대해 순차적으로 재무제표를 수집합니다.
각 그룹은 checkpoint 지원으로 중단 시 재개 가능합니다.

Usage:
    # 전체 그룹 수집 (기본: 2024, 2023, 2022)
    python scripts/batch_collect_all_groups.py

    # 특정 연도만 수집
    python scripts/batch_collect_all_groups.py --years 2024 2023

    # 특정 그룹부터 시작
    python scripts/batch_collect_all_groups.py --start-group 3

    # 각 그룹 완료 후 대기 시간 설정 (초)
    python scripts/batch_collect_all_groups.py --delay 10
"""

import sys
from pathlib import Path
import argparse
import json
import subprocess
from datetime import datetime
import time

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger

# Configure logger
logger.add(
    "logs/batch_collect_all_groups_{time}.log",
    rotation="1 day",
    retention="30 days",
    level="INFO"
)


def load_group_summary():
    """배치 그룹 요약 정보 로드."""
    summary_path = project_root / "data" / "batch_groups" / "batch_groups_summary.json"

    if not summary_path.exists():
        raise FileNotFoundError(f"Group summary not found: {summary_path}")

    with open(summary_path, 'r') as f:
        return json.load(f)


def collect_group(group_id: int, years: list, resume: bool = False):
    """특정 그룹 재무제표 수집.

    Args:
        group_id: 그룹 ID
        years: 수집할 연도 리스트
        resume: checkpoint에서 재개 여부

    Returns:
        bool: 성공 여부
    """
    logger.info(f"{'='*80}")
    logger.info(f"Starting collection for Group {group_id}")
    logger.info(f"{'='*80}")

    cmd = [
        "python",
        str(project_root / "scripts" / "batch_collect_financials.py"),
        "--group", str(group_id),
        "--years"
    ] + [str(y) for y in years]

    if resume:
        cmd.append("--resume")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=False,  # Show output in real-time
            text=True,
            check=True
        )

        logger.success(f"✓ Group {group_id} completed successfully")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"✗ Group {group_id} failed with exit code {e.returncode}")
        return False
    except Exception as e:
        logger.exception(f"✗ Group {group_id} failed with error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Batch collect all groups")
    parser.add_argument(
        '--years',
        type=int,
        nargs='+',
        default=[2024, 2023, 2022],
        help='Years to collect (default: 2024 2023 2022)'
    )
    parser.add_argument(
        '--start-group',
        type=int,
        default=1,
        help='Start from this group (default: 1)'
    )
    parser.add_argument(
        '--end-group',
        type=int,
        default=None,
        help='End at this group (default: last group)'
    )
    parser.add_argument(
        '--delay',
        type=int,
        default=5,
        help='Delay between groups in seconds (default: 5)'
    )
    parser.add_argument(
        '--resume',
        action='store_true',
        help='Resume from checkpoints for each group'
    )

    args = parser.parse_args()

    # Load group summary
    try:
        summary = load_group_summary()
        num_groups = summary['num_groups']
        total_stocks = summary['total_stocks']
    except Exception as e:
        logger.error(f"Failed to load group summary: {e}")
        return 1

    # Determine groups to process
    start_group = args.start_group
    end_group = args.end_group if args.end_group else num_groups

    if start_group < 1 or start_group > num_groups:
        logger.error(f"Invalid start group: {start_group} (must be 1-{num_groups})")
        return 1

    if end_group < start_group or end_group > num_groups:
        logger.error(f"Invalid end group: {end_group} (must be {start_group}-{num_groups})")
        return 1

    groups_to_process = list(range(start_group, end_group + 1))

    # Print summary
    print("=" * 80)
    print("📊 전체 배치 수집 시작")
    print("=" * 80)
    print(f"총 종목 수:       {total_stocks:,}개")
    print(f"총 그룹 수:       {num_groups}개")
    print(f"처리할 그룹:      {start_group} ~ {end_group} ({len(groups_to_process)}개)")
    print(f"수집 연도:        {', '.join(map(str, args.years))}")
    print(f"그룹간 대기:      {args.delay}초")
    print(f"Checkpoint 재개:  {'예' if args.resume else '아니오'}")
    print("=" * 80)
    print()

    # Confirm
    response = input("계속 진행하시겠습니까? (y/N): ").strip().lower()
    if response != 'y':
        print("취소되었습니다.")
        return 0

    print()

    # Process groups
    start_time = datetime.now()
    success_count = 0
    failed_groups = []

    for i, group_id in enumerate(groups_to_process, 1):
        logger.info(f"\n[{i}/{len(groups_to_process)}] Processing Group {group_id}...")

        success = collect_group(group_id, args.years, args.resume)

        if success:
            success_count += 1
        else:
            failed_groups.append(group_id)
            logger.warning(f"Group {group_id} failed - continuing to next group...")

        # Delay between groups (except after last group)
        if i < len(groups_to_process) and args.delay > 0:
            logger.info(f"Waiting {args.delay} seconds before next group...")
            time.sleep(args.delay)

    # Summary
    end_time = datetime.now()
    duration = end_time - start_time

    print()
    print("=" * 80)
    print("📊 전체 배치 수집 완료")
    print("=" * 80)
    print(f"처리한 그룹:      {len(groups_to_process)}개")
    print(f"성공:            {success_count}개")
    print(f"실패:            {len(failed_groups)}개")
    if failed_groups:
        print(f"실패한 그룹:      {', '.join(map(str, failed_groups))}")
    print(f"소요 시간:        {duration}")
    print("=" * 80)

    if failed_groups:
        print()
        print("⚠️  일부 그룹 수집 실패. 다음 명령으로 재시도:")
        for group_id in failed_groups:
            print(f"  python scripts/batch_collect_financials.py --group {group_id} --resume")

    logger.info(f"Total duration: {duration}")
    logger.info(f"Success: {success_count}/{len(groups_to_process)}")

    return 0 if not failed_groups else 1


if __name__ == "__main__":
    sys.exit(main())
