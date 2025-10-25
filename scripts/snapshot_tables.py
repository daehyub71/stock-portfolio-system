#!/usr/bin/env python3
"""테이블 스냅샷 관리 스크립트.

주요 테이블의 스냅샷을 생성하고 관리합니다.
스냅샷은 특정 시점의 데이터 상태를 보존하여 필요시 복원할 수 있습니다.

Features:
- 주요 테이블 스냅샷 생성 (CREATE TABLE AS SELECT)
- 스냅샷 목록 관리
- 스냅샷에서 데이터 복원
- 스냅샷 비교 (diff)
- 자동 정리 (retention policy)

Usage:
    # 전체 테이블 스냅샷 생성
    python scripts/snapshot_tables.py create

    # 특정 테이블만 스냅샷
    python scripts/snapshot_tables.py create --tables stocks daily_prices

    # 스냅샷 목록 보기
    python scripts/snapshot_tables.py list

    # 스냅샷 복원
    python scripts/snapshot_tables.py restore --snapshot stocks_20250124_090000

    # 스냅샷 비교
    python scripts/snapshot_tables.py diff --snapshot stocks_20250124_090000

    # 이전 스냅샷 정리
    python scripts/snapshot_tables.py cleanup --days 7

Snapshot Tables:
    - stocks
    - daily_prices
    - financial_statements
    - financial_ratios
    - sectors
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
from db.connection import SessionLocal, engine
from models import Base
from sqlalchemy import text, inspect, MetaData

# Configure logger
log_dir = project_root / 'logs'
log_dir.mkdir(exist_ok=True)

logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    level="INFO"
)
logger.add(
    log_dir / "snapshot_{time:YYYY-MM-DD}.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    rotation="1 day",
    retention="30 days",
    level="INFO"
)


class TableSnapshot:
    """테이블 스냅샷 관리 클래스."""

    # 스냅샷 대상 테이블
    SNAPSHOT_TABLES = [
        'stocks',
        'daily_prices',
        'financial_statements',
        'financial_ratios',
        'sectors',
        'corp_code_map'
    ]

    def __init__(self):
        """Initialize table snapshot manager."""
        self.db = SessionLocal()
        self.metadata_dir = project_root / 'backups' / 'snapshots'
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.metadata_dir / 'snapshot_metadata.json'

        logger.info("TableSnapshot initialized")

    def _get_snapshot_name(self, table: str, timestamp: str) -> str:
        """Get snapshot table name.

        Args:
            table: Original table name
            timestamp: Timestamp string

        Returns:
            Snapshot table name
        """
        return f"{table}_snapshot_{timestamp}"

    def _get_table_row_count(self, table: str) -> int:
        """Get number of rows in table.

        Args:
            table: Table name

        Returns:
            Row count
        """
        result = self.db.execute(text(f"SELECT COUNT(*) FROM {table}"))
        return result.scalar()

    def create_snapshot(self, tables: Optional[List[str]] = None) -> List[Dict]:
        """Create snapshots for specified tables.

        Args:
            tables: List of tables to snapshot (None for all)

        Returns:
            List of snapshot metadata dictionaries
        """
        logger.info("=" * 80)
        logger.info("테이블 스냅샷 생성")
        logger.info("=" * 80)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        tables_to_snapshot = tables or self.SNAPSHOT_TABLES

        logger.info(f"Timestamp: {timestamp}")
        logger.info(f"대상 테이블: {len(tables_to_snapshot)}개")
        logger.info("")

        snapshots = []

        for table in tables_to_snapshot:
            logger.info(f"스냅샷 생성: {table}")

            try:
                # Get row count before snapshot
                row_count = self._get_table_row_count(table)
                logger.info(f"  레코드 수: {row_count:,}개")

                # Create snapshot table name
                snapshot_name = self._get_snapshot_name(table, timestamp)

                # Drop snapshot if exists
                drop_sql = f"DROP TABLE IF EXISTS {snapshot_name}"
                self.db.execute(text(drop_sql))

                # Create snapshot using CREATE TABLE AS SELECT
                create_sql = f"CREATE TABLE {snapshot_name} AS SELECT * FROM {table}"
                start_time = datetime.now()
                self.db.execute(text(create_sql))
                self.db.commit()
                elapsed = (datetime.now() - start_time).total_seconds()

                logger.info(f"  ✅ 스냅샷 생성 완료: {snapshot_name} ({elapsed:.2f}초)")

                # Create metadata
                metadata = {
                    'snapshot_name': snapshot_name,
                    'original_table': table,
                    'timestamp': timestamp,
                    'datetime': datetime.now().isoformat(),
                    'row_count': row_count,
                    'elapsed_seconds': elapsed
                }

                snapshots.append(metadata)

            except Exception as e:
                logger.error(f"  ❌ 스냅샷 생성 실패: {table} - {e}")
                self.db.rollback()

        logger.info("")
        logger.info("=" * 80)
        logger.info(f"✅ 스냅샷 생성 완료: {len(snapshots)}/{len(tables_to_snapshot)}")
        logger.info("=" * 80)

        # Save metadata
        self._save_metadata(snapshots)

        return snapshots

    def list_snapshots(self) -> List[Dict]:
        """List all available snapshots.

        Returns:
            List of snapshot info dictionaries
        """
        logger.info("=" * 80)
        logger.info("스냅샷 목록")
        logger.info("=" * 80)

        # Query all tables with '_snapshot_' pattern
        query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name LIKE '%_snapshot_%'
        ORDER BY table_name DESC
        """

        result = self.db.execute(text(query))
        snapshot_tables = [row[0] for row in result]

        if not snapshot_tables:
            logger.info("스냅샷이 없습니다.")
            return []

        # Group by timestamp
        snapshots_by_time = {}
        for snapshot_name in snapshot_tables:
            # Extract timestamp from snapshot name
            parts = snapshot_name.split('_snapshot_')
            if len(parts) == 2:
                original_table = parts[0]
                timestamp = parts[1]

                if timestamp not in snapshots_by_time:
                    snapshots_by_time[timestamp] = []

                # Get row count
                row_count = self._get_table_row_count(snapshot_name)

                snapshots_by_time[timestamp].append({
                    'snapshot_name': snapshot_name,
                    'original_table': original_table,
                    'row_count': row_count
                })

        # Display grouped snapshots
        logger.info(f"총 {len(snapshots_by_time)}개 스냅샷 세트")
        logger.info("")

        snapshot_list = []
        for timestamp in sorted(snapshots_by_time.keys(), reverse=True):
            snapshots = snapshots_by_time[timestamp]

            # Parse timestamp
            try:
                dt = datetime.strptime(timestamp, "%Y%m%d_%H%M%S")
                dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                dt_str = timestamp

            logger.info(f"[{dt_str}] ({len(snapshots)}개 테이블)")
            for snap in snapshots:
                logger.info(f"  - {snap['original_table']}: {snap['row_count']:,} rows")

            snapshot_list.append({
                'timestamp': timestamp,
                'datetime': dt_str,
                'tables': snapshots
            })

        logger.info("=" * 80)

        return snapshot_list

    def restore_snapshot(self, snapshot_name: str, confirm: bool = False) -> bool:
        """Restore table from snapshot.

        Args:
            snapshot_name: Snapshot table name
            confirm: Skip confirmation prompt if True

        Returns:
            True if successful, False otherwise
        """
        logger.info("=" * 80)
        logger.info("스냅샷 복원")
        logger.info("=" * 80)

        # Verify snapshot exists
        check_sql = """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = :snapshot_name
        )
        """
        exists = self.db.execute(text(check_sql), {'snapshot_name': snapshot_name}).scalar()

        if not exists:
            logger.error(f"❌ 스냅샷을 찾을 수 없습니다: {snapshot_name}")
            return False

        # Extract original table name
        parts = snapshot_name.split('_snapshot_')
        if len(parts) != 2:
            logger.error(f"❌ 잘못된 스냅샷 이름: {snapshot_name}")
            return False

        original_table = parts[0]
        timestamp = parts[1]

        logger.info(f"스냅샷: {snapshot_name}")
        logger.info(f"원본 테이블: {original_table}")
        logger.info(f"Timestamp: {timestamp}")

        # Get row counts
        snapshot_rows = self._get_table_row_count(snapshot_name)
        current_rows = self._get_table_row_count(original_table)

        logger.info(f"\n현재 레코드 수: {current_rows:,}개")
        logger.info(f"스냅샷 레코드 수: {snapshot_rows:,}개")

        # Confirmation
        if not confirm:
            logger.warning("\n⚠️  경고: 복원하면 현재 데이터가 스냅샷으로 덮어씌워집니다!")
            response = input("\n계속하시겠습니까? (yes/no): ")
            if response.lower() not in ['yes', 'y']:
                logger.info("복원이 취소되었습니다.")
                return False

        try:
            logger.info(f"\n복원 중...")

            # Create backup of current table
            backup_name = f"{original_table}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            backup_sql = f"CREATE TABLE {backup_name} AS SELECT * FROM {original_table}"
            self.db.execute(text(backup_sql))
            logger.info(f"  현재 테이블 백업: {backup_name}")

            # Truncate original table
            truncate_sql = f"TRUNCATE TABLE {original_table} CASCADE"
            self.db.execute(text(truncate_sql))
            logger.info(f"  원본 테이블 비우기: {original_table}")

            # Copy data from snapshot
            insert_sql = f"INSERT INTO {original_table} SELECT * FROM {snapshot_name}"
            self.db.execute(text(insert_sql))
            logger.info(f"  스냅샷 데이터 복사: {snapshot_rows:,}개 레코드")

            self.db.commit()

            # Verify
            restored_rows = self._get_table_row_count(original_table)
            logger.info(f"  복원 후 레코드 수: {restored_rows:,}개")

            if restored_rows == snapshot_rows:
                logger.info("")
                logger.info("=" * 80)
                logger.info("✅ 스냅샷 복원 완료")
                logger.info(f"백업 테이블: {backup_name} (복원 실패 시 사용)")
                logger.info("=" * 80)
                return True
            else:
                logger.error("❌ 복원 후 레코드 수가 일치하지 않습니다!")
                return False

        except Exception as e:
            logger.error(f"❌ 복원 실패: {e}")
            self.db.rollback()
            return False

    def diff_snapshot(self, snapshot_name: str) -> Dict:
        """Compare snapshot with current table.

        Args:
            snapshot_name: Snapshot table name

        Returns:
            Diff statistics dictionary
        """
        logger.info("=" * 80)
        logger.info("스냅샷 비교")
        logger.info("=" * 80)

        # Extract original table name
        parts = snapshot_name.split('_snapshot_')
        if len(parts) != 2:
            logger.error(f"❌ 잘못된 스냅샷 이름: {snapshot_name}")
            return {}

        original_table = parts[0]

        logger.info(f"원본 테이블: {original_table}")
        logger.info(f"스냅샷: {snapshot_name}")
        logger.info("")

        # Get row counts
        snapshot_rows = self._get_table_row_count(snapshot_name)
        current_rows = self._get_table_row_count(original_table)

        diff = current_rows - snapshot_rows
        diff_pct = (diff / snapshot_rows * 100) if snapshot_rows > 0 else 0

        logger.info(f"스냅샷 레코드: {snapshot_rows:,}개")
        logger.info(f"현재 레코드:   {current_rows:,}개")
        logger.info(f"차이:          {diff:+,}개 ({diff_pct:+.2f}%)")

        result = {
            'original_table': original_table,
            'snapshot_name': snapshot_name,
            'snapshot_rows': snapshot_rows,
            'current_rows': current_rows,
            'diff': diff,
            'diff_percent': diff_pct
        }

        logger.info("=" * 80)

        return result

    def cleanup_old_snapshots(self, retention_days: int = 7):
        """Remove snapshots older than retention period.

        Args:
            retention_days: Number of days to retain snapshots
        """
        logger.info("=" * 80)
        logger.info("이전 스냅샷 정리")
        logger.info("=" * 80)

        cutoff_date = datetime.now() - timedelta(days=retention_days)
        logger.info(f"삭제 기준일: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")

        # Get all snapshot tables
        query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name LIKE '%_snapshot_%'
        """

        result = self.db.execute(text(query))
        snapshot_tables = [row[0] for row in result]

        removed_count = 0

        for snapshot_name in snapshot_tables:
            # Extract timestamp
            parts = snapshot_name.split('_snapshot_')
            if len(parts) != 2:
                continue

            timestamp = parts[1]

            try:
                snapshot_date = datetime.strptime(timestamp, "%Y%m%d_%H%M%S")

                if snapshot_date < cutoff_date:
                    # Drop snapshot table
                    drop_sql = f"DROP TABLE IF EXISTS {snapshot_name}"
                    self.db.execute(text(drop_sql))
                    self.db.commit()

                    removed_count += 1
                    logger.info(f"  삭제: {snapshot_name}")

            except ValueError:
                logger.warning(f"  건너뛰기: {snapshot_name} (잘못된 timestamp)")

        logger.info("")
        logger.info(f"정리 완료: {removed_count}개 스냅샷 삭제")
        logger.info("=" * 80)

    def _save_metadata(self, snapshots: List[Dict]):
        """Save snapshot metadata to JSON file.

        Args:
            snapshots: List of snapshot metadata dictionaries
        """
        # Load existing metadata
        if self.metadata_file.exists():
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                all_metadata = json.load(f)
        else:
            all_metadata = {'snapshots': []}

        # Add new metadata
        all_metadata['snapshots'].extend(snapshots)

        # Save
        with open(self.metadata_file, 'w', encoding='utf-8') as f:
            json.dump(all_metadata, f, ensure_ascii=False, indent=2)

        logger.debug(f"Metadata saved: {self.metadata_file}")

    def close(self):
        """Close database connection."""
        self.db.close()


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='테이블 스냅샷 관리'
    )

    subparsers = parser.add_subparsers(dest='command', help='명령')

    # Create snapshot
    create_parser = subparsers.add_parser('create', help='스냅샷 생성')
    create_parser.add_argument(
        '--tables',
        nargs='+',
        help='스냅샷할 테이블 목록 (미지정 시 전체)'
    )

    # List snapshots
    subparsers.add_parser('list', help='스냅샷 목록')

    # Restore snapshot
    restore_parser = subparsers.add_parser('restore', help='스냅샷 복원')
    restore_parser.add_argument(
        '--snapshot',
        required=True,
        help='복원할 스냅샷 이름'
    )
    restore_parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='확인 없이 복원'
    )

    # Diff snapshot
    diff_parser = subparsers.add_parser('diff', help='스냅샷 비교')
    diff_parser.add_argument(
        '--snapshot',
        required=True,
        help='비교할 스냅샷 이름'
    )

    # Cleanup snapshots
    cleanup_parser = subparsers.add_parser('cleanup', help='이전 스냅샷 정리')
    cleanup_parser.add_argument(
        '--days',
        type=int,
        default=7,
        help='보존 기간 (일, 기본값: 7)'
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        snapshot = TableSnapshot()

        if args.command == 'create':
            snapshot.create_snapshot(args.tables)

        elif args.command == 'list':
            snapshot.list_snapshots()

        elif args.command == 'restore':
            snapshot.restore_snapshot(args.snapshot, confirm=args.yes)

        elif args.command == 'diff':
            snapshot.diff_snapshot(args.snapshot)

        elif args.command == 'cleanup':
            snapshot.cleanup_old_snapshots(args.days)

    except KeyboardInterrupt:
        logger.warning("\n⚠️  사용자에 의해 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if 'snapshot' in locals():
            snapshot.close()


if __name__ == '__main__':
    main()
