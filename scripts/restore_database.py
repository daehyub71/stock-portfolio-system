#!/usr/bin/env python3
"""PostgreSQL 데이터베이스 복구 스크립트.

백업 파일로부터 데이터베이스를 복구합니다.

Features:
- 전체 데이터베이스 복구
- 개별 테이블 복구
- 백업 검증 (checksum)
- 복구 전 확인
- 복구 후 검증

Usage:
    # 최신 전체 백업으로 복구
    python scripts/restore_database.py --latest

    # 특정 백업 파일로 복구
    python scripts/restore_database.py --file backups/db_full/stock_portfolio_20250124_090000.sql.gz

    # 확인 없이 복구 (자동화용)
    python scripts/restore_database.py --latest --yes

    # 복구 테스트 (dry-run)
    python scripts/restore_database.py --latest --dry-run

Safety:
    - 복구 전 현재 데이터베이스 자동 백업
    - 복구 확인 프롬프트
    - Checksum 검증
"""

import sys
import os
import subprocess
import gzip
import shutil
import json
import argparse
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict

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
    log_dir / "restore_{time:YYYY-MM-DD}.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    rotation="1 day",
    retention="30 days",
    level="INFO"
)


class DatabaseRestore:
    """데이터베이스 복구 클래스."""

    def __init__(self, backup_dir: Optional[Path] = None):
        """Initialize database restore.

        Args:
            backup_dir: Backup directory (default: project_root/backups)
        """
        # Database configuration
        self.db_host = os.getenv("DB_HOST", "localhost")
        self.db_port = os.getenv("DB_PORT", "5432")
        self.db_name = os.getenv("DB_NAME", "stock_portfolio")
        self.db_user = os.getenv("DB_USER", os.getenv("USER"))
        self.db_password = os.getenv("DB_PASSWORD", "")

        # Backup configuration
        self.backup_dir = backup_dir or (project_root / 'backups')
        self.full_backup_dir = self.backup_dir / 'db_full'
        self.table_backup_dir = self.backup_dir / 'db_tables'
        self.metadata_dir = self.backup_dir / 'metadata'
        self.metadata_file = self.metadata_dir / 'backup_metadata.json'

        logger.info("DatabaseRestore initialized")
        logger.info(f"  Database: {self.db_name}")
        logger.info(f"  Backup dir: {self.backup_dir}")

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

    def verify_backup(self, backup_file: Path, expected_checksum: Optional[str] = None) -> bool:
        """Verify backup file integrity.

        Args:
            backup_file: Backup file to verify
            expected_checksum: Expected MD5 checksum

        Returns:
            True if valid, False otherwise
        """
        logger.info(f"백업 파일 검증: {backup_file.name}")

        if not backup_file.exists():
            logger.error("❌ 백업 파일이 존재하지 않습니다.")
            return False

        # Calculate checksum
        actual_checksum = self._calculate_checksum(backup_file)
        logger.info(f"Checksum: {actual_checksum}")

        # Verify if expected checksum provided
        if expected_checksum:
            if actual_checksum == expected_checksum:
                logger.info("✅ Checksum 검증 성공")
                return True
            else:
                logger.error(f"❌ Checksum 불일치!")
                logger.error(f"  Expected: {expected_checksum}")
                logger.error(f"  Actual:   {actual_checksum}")
                return False

        logger.warning("⚠️  Expected checksum이 없어 검증을 건너뜁니다.")
        return True

    def find_latest_backup(self, backup_type: str = 'full') -> Optional[Path]:
        """Find latest backup file.

        Args:
            backup_type: 'full' or 'table'

        Returns:
            Path to latest backup file or None
        """
        if backup_type == 'full':
            backup_dir = self.full_backup_dir
        else:
            backup_dir = self.table_backup_dir

        backups = sorted(backup_dir.glob("*.sql*"), reverse=True)

        if not backups:
            logger.error(f"❌ {backup_type} 백업을 찾을 수 없습니다.")
            return None

        latest = backups[0]
        logger.info(f"최신 백업: {latest.name}")
        return latest

    def _decompress_if_needed(self, backup_file: Path) -> Path:
        """Decompress backup file if it's gzipped.

        Args:
            backup_file: Backup file (may be compressed)

        Returns:
            Path to decompressed SQL file
        """
        if backup_file.suffix == '.gz':
            logger.info(f"압축 해제 중: {backup_file.name}")

            # Decompress to temporary file
            sql_file = backup_file.with_suffix('')

            with gzip.open(backup_file, 'rb') as f_in:
                with open(sql_file, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)

            logger.info(f"✅ 압축 해제 완료: {sql_file.name}")
            return sql_file
        else:
            return backup_file

    def _run_psql(self, sql_file: Path) -> bool:
        """Run psql command to restore database.

        Args:
            sql_file: SQL file to execute

        Returns:
            True if successful, False otherwise
        """
        cmd = [
            'psql',
            '-h', self.db_host,
            '-p', self.db_port,
            '-U', self.db_user,
            '-d', self.db_name,
            '-f', str(sql_file)
        ]

        # Set environment for password (if provided)
        env = os.environ.copy()
        if self.db_password:
            env['PGPASSWORD'] = self.db_password

        try:
            logger.info(f"Running psql...")

            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                check=True
            )

            logger.info(f"✅ psql completed successfully")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"❌ psql failed: {e}")
            logger.error(f"stdout: {e.stdout}")
            logger.error(f"stderr: {e.stderr}")
            return False
        except FileNotFoundError:
            logger.error("❌ psql command not found. Install PostgreSQL client tools.")
            return False

    def backup_current_database(self) -> Optional[Path]:
        """Backup current database before restore.

        Returns:
            Path to backup file or None if failed
        """
        logger.info("=" * 80)
        logger.info("복구 전 현재 데이터베이스 백업")
        logger.info("=" * 80)

        from scripts.backup_database import DatabaseBackup

        backup = DatabaseBackup()
        metadata = backup.backup_full_database()

        if metadata:
            backup_file = Path(metadata['filepath'])
            logger.info(f"✅ 현재 DB 백업 완료: {backup_file.name}")
            return backup_file
        else:
            logger.error("❌ 현재 DB 백업 실패")
            return None

    def restore_from_file(
        self,
        backup_file: Path,
        verify: bool = True,
        dry_run: bool = False
    ) -> bool:
        """Restore database from backup file.

        Args:
            backup_file: Backup file to restore
            verify: Whether to verify backup before restore
            dry_run: If True, only verify without actual restore

        Returns:
            True if successful, False otherwise
        """
        logger.info("=" * 80)
        logger.info("데이터베이스 복구 시작")
        logger.info("=" * 80)
        logger.info(f"백업 파일: {backup_file}")
        logger.info(f"데이터베이스: {self.db_name}")
        logger.info(f"Dry-run: {dry_run}")
        logger.info("=" * 80)

        # Verify backup file
        if verify:
            # Try to get expected checksum from metadata
            expected_checksum = None
            if self.metadata_file.exists():
                with open(self.metadata_file, 'r') as f:
                    metadata = json.load(f)
                    for backup_meta in metadata.get('backups', []):
                        if Path(backup_meta['filepath']) == backup_file:
                            expected_checksum = backup_meta.get('checksum')
                            break

            if not self.verify_backup(backup_file, expected_checksum):
                logger.error("❌ 백업 검증 실패")
                return False

        if dry_run:
            logger.info("✅ Dry-run 모드: 복구를 건너뜁니다.")
            logger.info("=" * 80)
            return True

        # Decompress if needed
        sql_file = self._decompress_if_needed(backup_file)
        temp_file = sql_file if sql_file != backup_file else None

        try:
            # Run psql restore
            success = self._run_psql(sql_file)

            if success:
                logger.info("")
                logger.info("=" * 80)
                logger.info("✅ 데이터베이스 복구 완료")
                logger.info("=" * 80)
            else:
                logger.error("")
                logger.error("=" * 80)
                logger.error("❌ 데이터베이스 복구 실패")
                logger.error("=" * 80)

            return success

        finally:
            # Clean up temporary decompressed file
            if temp_file and temp_file.exists():
                temp_file.unlink()
                logger.debug(f"Temporary file removed: {temp_file}")

    def verify_restored_database(self) -> bool:
        """Verify restored database integrity.

        Returns:
            True if database is valid, False otherwise
        """
        logger.info("")
        logger.info("=" * 80)
        logger.info("복구된 데이터베이스 검증")
        logger.info("=" * 80)

        # Import here to avoid circular dependency
        from db.connection import SessionLocal
        from models import Stock, DailyPrice, FinancialStatement, FinancialRatio
        from sqlalchemy import func

        try:
            db = SessionLocal()

            # Check table counts
            checks = {
                'stocks': db.query(func.count(Stock.id)).scalar(),
                'daily_prices': db.query(func.count(DailyPrice.id)).scalar(),
                'financial_statements': db.query(func.count(FinancialStatement.id)).scalar(),
                'financial_ratios': db.query(func.count(FinancialRatio.id)).scalar()
            }

            logger.info("테이블 레코드 수:")
            for table, count in checks.items():
                logger.info(f"  - {table}: {count:,}개")

            # Basic sanity checks
            if checks['stocks'] == 0:
                logger.error("❌ 종목 데이터가 없습니다!")
                return False

            logger.info("")
            logger.info("✅ 데이터베이스 검증 완료")
            logger.info("=" * 80)

            return True

        except Exception as e:
            logger.error(f"❌ 검증 실패: {e}")
            return False
        finally:
            db.close()


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='PostgreSQL 데이터베이스 복구'
    )

    parser.add_argument(
        '--file',
        type=str,
        help='복구할 백업 파일 경로'
    )
    parser.add_argument(
        '--latest',
        action='store_true',
        help='최신 백업으로 복구'
    )
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='확인 없이 복구 (자동화용)'
    )
    parser.add_argument(
        '--no-verify',
        action='store_true',
        help='백업 검증 건너뛰기'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='테스트 모드 (실제 복구하지 않음)'
    )
    parser.add_argument(
        '--skip-backup',
        action='store_true',
        help='복구 전 현재 DB 백업 건너뛰기'
    )

    args = parser.parse_args()

    if not args.file and not args.latest:
        logger.error("❌ --file 또는 --latest 옵션이 필요합니다.")
        parser.print_help()
        sys.exit(1)

    try:
        restore = DatabaseRestore()

        # Determine backup file
        if args.latest:
            backup_file = restore.find_latest_backup()
            if not backup_file:
                sys.exit(1)
        else:
            backup_file = Path(args.file)
            if not backup_file.exists():
                logger.error(f"❌ 백업 파일이 존재하지 않습니다: {backup_file}")
                sys.exit(1)

        # Confirmation prompt
        if not args.yes and not args.dry_run:
            logger.warning("")
            logger.warning("⚠️  경고: 데이터베이스를 복구하면 현재 데이터가 손실될 수 있습니다!")
            logger.warning(f"복구할 백업: {backup_file.name}")
            logger.warning("")

            response = input("계속하시겠습니까? (yes/no): ")
            if response.lower() not in ['yes', 'y']:
                logger.info("복구가 취소되었습니다.")
                sys.exit(0)

        # Backup current database (unless skipped or dry-run)
        if not args.skip_backup and not args.dry_run:
            current_backup = restore.backup_current_database()
            if not current_backup:
                logger.error("❌ 현재 DB 백업 실패. 복구를 중단합니다.")
                sys.exit(1)

        # Perform restore
        success = restore.restore_from_file(
            backup_file,
            verify=not args.no_verify,
            dry_run=args.dry_run
        )

        if not success:
            sys.exit(1)

        # Verify restored database
        if not args.dry_run:
            if not restore.verify_restored_database():
                logger.warning("⚠️  복구 후 검증에서 문제가 발견되었습니다.")
                sys.exit(1)

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
