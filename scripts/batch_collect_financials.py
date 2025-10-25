#!/usr/bin/env python3
"""재무제표 배치 수집 스크립트 (Checkpoint 지원).

특정 그룹의 종목에 대해 재무제표를 수집합니다.
Checkpoint 기능으로 중단된 작업을 이어서 실행할 수 있습니다.

Usage:
    # 그룹 1 수집 (처음부터)
    python scripts/batch_collect_financials.py --group 1

    # 그룹 1 수집 (이어서)
    python scripts/batch_collect_financials.py --group 1 --resume

    # 특정 연도만 수집
    python scripts/batch_collect_financials.py --group 1 --years 2024 2023

    # 디버그 모드 (상세 로그)
    python scripts/batch_collect_financials.py --group 1 --debug
"""

import sys
from pathlib import Path
import argparse
import json
from datetime import datetime
import time
from typing import Dict, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
from collectors import DARTCollector
from db.connection import SessionLocal


# Configure logger
log_dir = project_root / 'logs'
log_dir.mkdir(exist_ok=True)

logger.remove()  # Remove default handler
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    level="INFO"
)
logger.add(
    log_dir / "batch_collection.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    rotation="100 MB",
    retention="30 days",
    level="DEBUG"
)


class CheckpointManager:
    """수집 진행 상황을 저장하고 복원하는 매니저."""

    def __init__(self, checkpoint_dir: Path):
        """Initialize checkpoint manager.

        Args:
            checkpoint_dir: Directory to store checkpoint files
        """
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def get_checkpoint_path(self, group_id: int) -> Path:
        """Get checkpoint file path for a group.

        Args:
            group_id: Group ID

        Returns:
            Path to checkpoint file
        """
        return self.checkpoint_dir / f"checkpoint_group_{group_id}.json"

    def save_checkpoint(self, group_id: int, checkpoint_data: Dict):
        """Save checkpoint data.

        Args:
            group_id: Group ID
            checkpoint_data: Checkpoint data to save
        """
        checkpoint_path = self.get_checkpoint_path(group_id)
        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
        logger.debug(f"Checkpoint saved: {checkpoint_path}")

    def load_checkpoint(self, group_id: int) -> Optional[Dict]:
        """Load checkpoint data.

        Args:
            group_id: Group ID

        Returns:
            Checkpoint data if exists, None otherwise
        """
        checkpoint_path = self.get_checkpoint_path(group_id)
        if not checkpoint_path.exists():
            return None

        with open(checkpoint_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def clear_checkpoint(self, group_id: int):
        """Clear checkpoint file.

        Args:
            group_id: Group ID
        """
        checkpoint_path = self.get_checkpoint_path(group_id)
        if checkpoint_path.exists():
            checkpoint_path.unlink()
            logger.info(f"Checkpoint cleared: {checkpoint_path}")


class BatchCollector:
    """배치 재무제표 수집 클래스."""

    def __init__(self, group_id: int, years: List[int], resume: bool = False, debug: bool = False):
        """Initialize batch collector.

        Args:
            group_id: Group ID to collect
            years: List of years to collect
            resume: Whether to resume from checkpoint
            debug: Debug mode flag
        """
        self.group_id = group_id
        self.years = years
        self.resume = resume
        self.debug = debug

        # Load group data
        self.group_file = project_root / 'data' / 'batch_groups' / f'group_{group_id}.json'
        if not self.group_file.exists():
            raise FileNotFoundError(f"Group file not found: {self.group_file}")

        with open(self.group_file, 'r', encoding='utf-8') as f:
            self.group_data = json.load(f)

        self.stocks = self.group_data['stocks']
        self.total_stocks = len(self.stocks)

        # Checkpoint manager
        self.checkpoint_manager = CheckpointManager(project_root / 'data' / 'checkpoints')

        # Statistics
        self.stats = {
            'start_time': datetime.now().isoformat(),
            'group_id': group_id,
            'total_stocks': self.total_stocks,
            'processed': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'errors': []
        }

        # Resume from checkpoint if requested
        if self.resume:
            checkpoint = self.checkpoint_manager.load_checkpoint(group_id)
            if checkpoint:
                self.stats = checkpoint
                logger.info(f"✅ Checkpoint loaded: {self.stats['processed']}/{self.total_stocks} processed")
            else:
                logger.warning("⚠️  No checkpoint found, starting from beginning")
                self.resume = False

    def should_skip_stock(self, ticker: str) -> bool:
        """Check if stock should be skipped.

        Args:
            ticker: Stock ticker

        Returns:
            True if should skip, False otherwise
        """
        if not self.resume:
            return False

        # Skip if already processed
        for error in self.stats.get('errors', []):
            if error.get('ticker') == ticker:
                return True

        # Check if processed count indicates we should skip
        current_index = next(
            (i for i, s in enumerate(self.stocks) if s['ticker'] == ticker),
            -1
        )
        return current_index < self.stats.get('processed', 0)

    def collect_group(self):
        """Collect financial statements for the group."""
        logger.info("=" * 70)
        logger.info(f"배치 수집 시작 - Group {self.group_id}")
        logger.info("=" * 70)
        logger.info(f"종목 수: {self.total_stocks}")
        logger.info(f"수집 연도: {self.years}")
        logger.info(f"Resume 모드: {self.resume}")
        logger.info("=" * 70)

        db = SessionLocal()
        collector = DARTCollector(db_session=db)

        try:
            for i, stock in enumerate(self.stocks, 1):
                ticker = stock['ticker']
                name = stock['name']

                # Skip if already processed (resume mode)
                if self.should_skip_stock(ticker):
                    logger.debug(f"[{i}/{self.total_stocks}] {ticker} ({name}) - SKIPPED (already processed)")
                    self.stats['skipped'] += 1
                    continue

                logger.info(f"[{i}/{self.total_stocks}] Processing {ticker} ({name})...")

                try:
                    # Collect financial statements
                    result = collector.collect_and_save(
                        ticker=ticker,
                        years=self.years
                    )

                    if result['saved'] > 0:
                        logger.info(f"  ✅ {ticker}: Fetched {result['fetched']}, Saved {result['saved']}")
                        self.stats['success'] += 1
                    else:
                        logger.warning(f"  ⚠️  {ticker}: No data saved")
                        self.stats['failed'] += 1
                        self.stats['errors'].append({
                            'ticker': ticker,
                            'name': name,
                            'error': 'No data saved',
                            'timestamp': datetime.now().isoformat()
                        })

                except Exception as e:
                    logger.error(f"  ❌ {ticker}: {str(e)}")
                    self.stats['failed'] += 1
                    self.stats['errors'].append({
                        'ticker': ticker,
                        'name': name,
                        'error': str(e),
                        'timestamp': datetime.now().isoformat()
                    })

                finally:
                    self.stats['processed'] += 1

                    # Save checkpoint every 10 stocks
                    if self.stats['processed'] % 10 == 0:
                        self.checkpoint_manager.save_checkpoint(self.group_id, self.stats)
                        logger.info(f"💾 Checkpoint saved: {self.stats['processed']}/{self.total_stocks}")

                    # Print progress every 50 stocks
                    if self.stats['processed'] % 50 == 0:
                        self._print_progress()

            # Final checkpoint
            self.stats['end_time'] = datetime.now().isoformat()
            self.checkpoint_manager.save_checkpoint(self.group_id, self.stats)

        finally:
            db.close()

        # Print final summary
        self._print_summary()

        # Clear checkpoint if completed successfully
        if self.stats['processed'] == self.total_stocks:
            logger.info("✅ All stocks processed, clearing checkpoint")
            self.checkpoint_manager.clear_checkpoint(self.group_id)

    def _print_progress(self):
        """Print current progress."""
        success_rate = (self.stats['success'] / self.stats['processed'] * 100) if self.stats['processed'] > 0 else 0
        logger.info("─" * 70)
        logger.info(f"진행 상황: {self.stats['processed']}/{self.total_stocks} ({self.stats['processed']/self.total_stocks*100:.1f}%)")
        logger.info(f"성공: {self.stats['success']} | 실패: {self.stats['failed']} | 성공률: {success_rate:.1f}%")
        logger.info("─" * 70)

    def _print_summary(self):
        """Print final summary."""
        logger.info("\n" + "=" * 70)
        logger.info("배치 수집 완료")
        logger.info("=" * 70)

        # Calculate duration
        start_time = datetime.fromisoformat(self.stats['start_time'])
        end_time = datetime.fromisoformat(self.stats.get('end_time', datetime.now().isoformat()))
        duration = end_time - start_time

        logger.info(f"그룹: {self.group_id}")
        logger.info(f"총 종목 수: {self.total_stocks}")
        logger.info(f"처리 완료: {self.stats['processed']}")
        logger.info(f"성공: {self.stats['success']}")
        logger.info(f"실패: {self.stats['failed']}")
        logger.info(f"건너뛰기: {self.stats['skipped']}")
        logger.info(f"소요 시간: {duration}")

        if self.stats['failed'] > 0:
            logger.info(f"\n❌ 실패한 종목 ({self.stats['failed']}):")
            for error in self.stats['errors'][:10]:  # Show first 10
                logger.info(f"  - {error['ticker']} ({error.get('name', 'N/A')}): {error['error']}")
            if self.stats['failed'] > 10:
                logger.info(f"  ... and {self.stats['failed'] - 10} more")

        logger.info("\n다음 단계:")
        if self.stats['processed'] < self.total_stocks:
            logger.info(f"  1. 이어서 수집: python scripts/batch_collect_financials.py --group {self.group_id} --resume")
        else:
            logger.info(f"  1. 다음 그룹 수집: python scripts/batch_collect_financials.py --group {self.group_id + 1}")
        logger.info(f"  2. 로그 확인: cat logs/batch_collection.log")
        logger.info("=" * 70)


def main():
    """메인 함수."""
    parser = argparse.ArgumentParser(
        description="Batch collect financial statements for a group"
    )

    parser.add_argument(
        "--group",
        type=int,
        required=True,
        help="Group ID to collect (1-6)"
    )
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=[2024, 2023, 2022],
        help="Years to collect (default: 2024 2023 2022)"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last checkpoint"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )

    args = parser.parse_args()

    # Validate group ID
    if args.group < 1 or args.group > 6:
        logger.error("❌ Invalid group ID. Must be between 1 and 6.")
        sys.exit(1)

    # Set log level
    if args.debug:
        logger.remove()
        logger.add(
            sys.stdout,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
            level="DEBUG"
        )
        logger.add(
            log_dir / "batch_collection.log",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
            rotation="100 MB",
            retention="30 days",
            level="DEBUG"
        )

    try:
        collector = BatchCollector(
            group_id=args.group,
            years=args.years,
            resume=args.resume,
            debug=args.debug
        )
        collector.collect_group()

    except KeyboardInterrupt:
        logger.warning("\n⚠️  Interrupted by user. Progress saved to checkpoint.")
        logger.info("Resume with: python scripts/batch_collect_financials.py --group {} --resume".format(args.group))
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
