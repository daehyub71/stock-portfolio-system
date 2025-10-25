#!/usr/bin/env python3
"""PostgreSQL 데이터베이스 자동 백업 스크립트.

pg_dump를 사용하여 전체 데이터베이스 또는 개별 테이블을 백업합니다.

Features:
- 전체 데이터베이스 백업 (pg_dump)
- 개별 테이블 백업
- 자동 압축 (gzip)
- 백업 파일 보존 정책 (최근 N일)
- 백업 검증
- 백업 메타데이터 관리

Usage:
    # 전체 데이터베이스 백업
    python scripts/backup_database.py

    # 특정 테이블만 백업
    python scripts/backup_database.py --tables stocks daily_prices

    # 압축 없이 백업
    python scripts/backup_database.py --no-compress

    # 보존 기간 지정 (기본 30일)
    python scripts/backup_database.py --retention-days 60

Backup Structure:
    backups/
    ├── db_full/
    │   ├── stock_portfolio_20250124_090000.sql.gz
    │   ├── stock_portfolio_20250123_090000.sql.gz
    │   └── ...
    ├── db_tables/
    │   ├── stocks_20250124_090000.sql.gz
    │   ├── daily_prices_20250124_090000.sql.gz
    │   └── ...
    └── metadata/
        └── backup_metadata.json
"""

import sys
import os
import subprocess
import gzip
import shutil
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import hashlib

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
from dotenv import load_dotenv

load_dotenv()

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
    log_dir / "backup_{time:YYYY-MM-DD}.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    rotation="1 day",
    retention="30 days",
    level="INFO"
)


class DatabaseBackup:
    """데이터베이스 백업 관리 클래스."""

    def __init__(
        self,
        backup_dir: Optional[Path] = None,
        compress: bool = True,
        retention_days: int = 30
    ):
        """Initialize database backup.

        Args:
            backup_dir: Backup directory (default: project_root/backups)
            compress: Whether to compress backups with gzip
            retention_days: Number of days to retain backups
        """
        # Database configuration
        self.db_host = os.getenv("DB_HOST", "localhost")
        self.db_port = os.getenv("DB_PORT", "5432")
        self.db_name = os.getenv("DB_NAME", "stock_portfolio")
        self.db_user = os.getenv("DB_USER", os.getenv("USER"))
        self.db_password = os.getenv("DB_PASSWORD", "")

        # Backup configuration
        self.backup_dir = backup_dir or (project_root / 'backups')
        self.compress = compress
        self.retention_days = retention_days

        # Create backup directories
        self.full_backup_dir = self.backup_dir / 'db_full'
        self.table_backup_dir = self.backup_dir / 'db_tables'
        self.metadata_dir = self.backup_dir / 'metadata'

        for dir_path in [self.full_backup_dir, self.table_backup_dir, self.metadata_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # Metadata file
        self.metadata_file = self.metadata_dir / 'backup_metadata.json'

        logger.info("DatabaseBackup initialized")
        logger.info(f"  Database: {self.db_name}")
        logger.info(f"  Backup dir: {self.backup_dir}")
        logger.info(f"  Compression: {self.compress}")
        logger.info(f"  Retention: {self.retention_days} days")

    def _run_pg_dump(
        self,
        output_file: Path,
        tables: Optional[List[str]] = None
    ) -> bool:
        """Run pg_dump command.

        Args:
            output_file: Output SQL file path
            tables: List of tables to backup (None for full backup)

        Returns:
            True if successful, False otherwise
        """
        # Build pg_dump command
        cmd = [
            'pg_dump',
            '-h', self.db_host,
            '-p', self.db_port,
            '-U', self.db_user,
            '-d', self.db_name,
            '-F', 'p',  # Plain text format
            '--no-owner',  # Don't output ownership commands
            '--no-acl',  # Don't output ACL commands
            '-f', str(output_file)
        ]

        # Add table filters if specified
        if tables:
            for table in tables:
                cmd.extend(['-t', table])

        # Set environment for password (if provided)
        env = os.environ.copy()
        if self.db_password:
            env['PGPASSWORD'] = self.db_password

        try:
            logger.info(f"Running pg_dump...")
            logger.debug(f"Command: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                check=True
            )

            logger.info(f"✅ pg_dump completed successfully")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"❌ pg_dump failed: {e}")
            logger.error(f"stdout: {e.stdout}")
            logger.error(f"stderr: {e.stderr}")
            return False
        except FileNotFoundError:
            logger.error("❌ pg_dump command not found. Install PostgreSQL client tools.")
            return False

    def _compress_file(self, file_path: Path) -> Optional[Path]:
        """Compress file with gzip.

        Args:
            file_path: File to compress

        Returns:
            Path to compressed file or None if failed
        """
        try:
            compressed_path = file_path.with_suffix(file_path.suffix + '.gz')

            logger.info(f"Compressing {file_path.name}...")

            with open(file_path, 'rb') as f_in:
                with gzip.open(compressed_path, 'wb', compresslevel=6) as f_out:
                    shutil.copyfileobj(f_in, f_out)

            # Remove original file
            file_path.unlink()

            original_size = file_path.stat().st_size if file_path.exists() else 0
            compressed_size = compressed_path.stat().st_size
            ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0

            logger.info(f"✅ Compressed: {compressed_size:,} bytes (saved {ratio:.1f}%)")

            return compressed_path

        except Exception as e:
            logger.error(f"❌ Compression failed: {e}")
            return None

    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate MD5 checksum of file.

        Args:
            file_path: File to calculate checksum

        Returns:
            MD5 checksum (hex)
        """
        md5 = hashlib.md5()

        # Handle gzipped files
        if file_path.suffix == '.gz':
            with gzip.open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    md5.update(chunk)
        else:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    md5.update(chunk)

        return md5.hexdigest()

    def backup_full_database(self) -> Optional[Dict]:
        """Backup full database.

        Returns:
            Backup metadata dictionary or None if failed
        """
        logger.info("=" * 80)
        logger.info("전체 데이터베이스 백업 시작")
        logger.info("=" * 80)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.db_name}_{timestamp}.sql"
        output_file = self.full_backup_dir / filename

        # Run pg_dump
        if not self._run_pg_dump(output_file):
            return None

        # Get file size
        file_size = output_file.stat().st_size
        logger.info(f"Backup size: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)")

        # Compress if enabled
        final_file = output_file
        if self.compress:
            compressed_file = self._compress_file(output_file)
            if compressed_file:
                final_file = compressed_file
            else:
                logger.warning("Compression failed, keeping uncompressed backup")

        # Calculate checksum
        checksum = self._calculate_checksum(final_file)
        logger.info(f"Checksum (MD5): {checksum}")

        # Create metadata
        metadata = {
            'type': 'full',
            'database': self.db_name,
            'timestamp': timestamp,
            'datetime': datetime.now().isoformat(),
            'filename': final_file.name,
            'filepath': str(final_file),
            'size_bytes': final_file.stat().st_size,
            'compressed': self.compress,
            'checksum': checksum,
            'tables': None  # Full backup includes all tables
        }

        logger.info("=" * 80)
        logger.info("✅ 전체 데이터베이스 백업 완료")
        logger.info(f"파일: {final_file}")
        logger.info("=" * 80)

        return metadata

    def backup_tables(self, tables: List[str]) -> List[Dict]:
        """Backup specific tables.

        Args:
            tables: List of table names

        Returns:
            List of backup metadata dictionaries
        """
        logger.info("=" * 80)
        logger.info(f"테이블 백업 시작: {len(tables)}개")
        logger.info("=" * 80)

        metadata_list = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        for table in tables:
            logger.info(f"\n백업: {table}")

            filename = f"{table}_{timestamp}.sql"
            output_file = self.table_backup_dir / filename

            # Run pg_dump for this table
            if not self._run_pg_dump(output_file, tables=[table]):
                logger.error(f"❌ Failed to backup {table}")
                continue

            # Get file size
            file_size = output_file.stat().st_size
            logger.info(f"  Size: {file_size:,} bytes")

            # Compress if enabled
            final_file = output_file
            if self.compress:
                compressed_file = self._compress_file(output_file)
                if compressed_file:
                    final_file = compressed_file

            # Calculate checksum
            checksum = self._calculate_checksum(final_file)

            # Create metadata
            metadata = {
                'type': 'table',
                'database': self.db_name,
                'timestamp': timestamp,
                'datetime': datetime.now().isoformat(),
                'filename': final_file.name,
                'filepath': str(final_file),
                'size_bytes': final_file.stat().st_size,
                'compressed': self.compress,
                'checksum': checksum,
                'tables': [table]
            }

            metadata_list.append(metadata)
            logger.info(f"  ✅ {table} 백업 완료")

        logger.info("")
        logger.info("=" * 80)
        logger.info(f"✅ 테이블 백업 완료: {len(metadata_list)}/{len(tables)}")
        logger.info("=" * 80)

        return metadata_list

    def save_metadata(self, metadata: Dict):
        """Save backup metadata to JSON file.

        Args:
            metadata: Backup metadata dictionary
        """
        # Load existing metadata
        if self.metadata_file.exists():
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                all_metadata = json.load(f)
        else:
            all_metadata = {'backups': []}

        # Add new metadata
        if isinstance(metadata, list):
            all_metadata['backups'].extend(metadata)
        else:
            all_metadata['backups'].append(metadata)

        # Save
        with open(self.metadata_file, 'w', encoding='utf-8') as f:
            json.dump(all_metadata, f, ensure_ascii=False, indent=2)

        logger.info(f"Metadata saved: {self.metadata_file}")

    def cleanup_old_backups(self):
        """Remove backups older than retention period."""
        logger.info("")
        logger.info("=" * 80)
        logger.info("이전 백업 정리 시작")
        logger.info("=" * 80)

        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        logger.info(f"삭제 기준일: {cutoff_date.strftime('%Y-%m-%d')}")

        removed_count = 0
        total_size_freed = 0

        # Clean full backups
        for backup_file in self.full_backup_dir.glob("*.sql*"):
            # Extract timestamp from filename (format: dbname_YYYYMMDD_HHMMSS.sql[.gz])
            try:
                parts = backup_file.stem.split('_')
                if len(parts) >= 3:
                    timestamp_str = f"{parts[-2]}_{parts[-1]}"
                    file_date = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")

                    if file_date < cutoff_date:
                        file_size = backup_file.stat().st_size
                        backup_file.unlink()
                        removed_count += 1
                        total_size_freed += file_size
                        logger.info(f"  삭제: {backup_file.name}")
            except (ValueError, IndexError) as e:
                logger.warning(f"  건너뛰기: {backup_file.name} - {e}")

        # Clean table backups
        for backup_file in self.table_backup_dir.glob("*.sql*"):
            try:
                parts = backup_file.stem.split('_')
                if len(parts) >= 3:
                    timestamp_str = f"{parts[-2]}_{parts[-1]}"
                    file_date = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")

                    if file_date < cutoff_date:
                        file_size = backup_file.stat().st_size
                        backup_file.unlink()
                        removed_count += 1
                        total_size_freed += file_size
                        logger.info(f"  삭제: {backup_file.name}")
            except (ValueError, IndexError) as e:
                logger.warning(f"  건너뛰기: {backup_file.name} - {e}")

        logger.info("")
        logger.info(f"정리 완료: {removed_count}개 파일 삭제 ({total_size_freed / 1024 / 1024:.2f} MB 확보)")
        logger.info("=" * 80)

    def list_backups(self) -> Dict:
        """List all available backups.

        Returns:
            Dictionary with backup statistics
        """
        full_backups = list(self.full_backup_dir.glob("*.sql*"))
        table_backups = list(self.table_backup_dir.glob("*.sql*"))

        total_size = sum(f.stat().st_size for f in full_backups + table_backups)

        logger.info("")
        logger.info("=" * 80)
        logger.info("백업 현황")
        logger.info("=" * 80)
        logger.info(f"전체 백업: {len(full_backups)}개")
        logger.info(f"테이블 백업: {len(table_backups)}개")
        logger.info(f"총 용량: {total_size / 1024 / 1024:.2f} MB")

        if full_backups:
            logger.info("\n최근 전체 백업:")
            for backup in sorted(full_backups, reverse=True)[:5]:
                size = backup.stat().st_size / 1024 / 1024
                logger.info(f"  - {backup.name} ({size:.2f} MB)")

        logger.info("=" * 80)

        return {
            'full_backups': len(full_backups),
            'table_backups': len(table_backups),
            'total_size_mb': total_size / 1024 / 1024,
            'backup_dir': str(self.backup_dir)
        }


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='PostgreSQL 데이터베이스 백업'
    )

    parser.add_argument(
        '--tables',
        nargs='+',
        help='백업할 테이블 목록 (미지정 시 전체 백업)'
    )
    parser.add_argument(
        '--no-compress',
        action='store_true',
        help='압축하지 않음'
    )
    parser.add_argument(
        '--retention-days',
        type=int,
        default=30,
        help='백업 보존 기간 (일, 기본값: 30)'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='백업 목록 표시'
    )
    parser.add_argument(
        '--cleanup-only',
        action='store_true',
        help='백업 없이 정리만 실행'
    )

    args = parser.parse_args()

    try:
        backup = DatabaseBackup(
            compress=not args.no_compress,
            retention_days=args.retention_days
        )

        if args.list:
            # List backups only
            backup.list_backups()
            return

        if args.cleanup_only:
            # Cleanup only
            backup.cleanup_old_backups()
            return

        # Perform backup
        if args.tables:
            # Backup specific tables
            metadata_list = backup.backup_tables(args.tables)
            if metadata_list:
                backup.save_metadata(metadata_list)
        else:
            # Backup full database
            metadata = backup.backup_full_database()
            if metadata:
                backup.save_metadata(metadata)

        # Cleanup old backups
        backup.cleanup_old_backups()

        # Show backup status
        backup.list_backups()

    except KeyboardInterrupt:
        logger.warning("\n⚠️  사용자에 의해 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
