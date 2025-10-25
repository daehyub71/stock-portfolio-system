#!/usr/bin/env python3
"""Airflow 설정 스크립트.

airflow.cfg를 프로그래밍 방식으로 수정하여
PostgreSQL 메타 데이터베이스와 연결하고 필요한 설정을 적용합니다.
"""

import os
import sys
from pathlib import Path
from configparser import ConfigParser

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
from dotenv import load_dotenv

load_dotenv()

# Configure logger
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    level="INFO"
)


class AirflowConfigurator:
    """Airflow 설정 관리 클래스."""

    def __init__(self, airflow_home: Path):
        """Initialize Airflow configurator.

        Args:
            airflow_home: Airflow home directory
        """
        self.airflow_home = airflow_home
        self.config_file = airflow_home / 'airflow.cfg'

        if not self.config_file.exists():
            logger.error(f"❌ airflow.cfg not found: {self.config_file}")
            logger.error("먼저 'airflow db init'을 실행하세요.")
            sys.exit(1)

        self.config = ConfigParser()
        self.config.read(self.config_file)

        logger.info(f"Airflow config: {self.config_file}")

    def configure_database(self, use_postgres: bool = True):
        """Configure database connection.

        Args:
            use_postgres: If True, use PostgreSQL. Otherwise use SQLite.
        """
        logger.info("\n" + "=" * 60)
        logger.info("데이터베이스 설정")
        logger.info("=" * 60)

        if use_postgres:
            # PostgreSQL configuration
            db_host = os.getenv("DB_HOST", "localhost")
            db_port = os.getenv("DB_PORT", "5432")
            db_name = "airflow_db"  # Separate DB for Airflow metadata
            db_user = os.getenv("DB_USER", os.getenv("USER"))
            db_password = os.getenv("DB_PASSWORD", "")

            # SQLAlchemy connection string
            if db_password:
                sql_alchemy_conn = f"postgresql+psycopg2://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
            else:
                sql_alchemy_conn = f"postgresql+psycopg2://{db_user}@{db_host}:{db_port}/{db_name}"

            logger.info(f"PostgreSQL 메타 DB: {db_name}")
            logger.info(f"  Host: {db_host}:{db_port}")
            logger.info(f"  User: {db_user}")

            # Update config
            if 'database' not in self.config.sections():
                self.config.add_section('database')

            self.config.set('database', 'sql_alchemy_conn', sql_alchemy_conn)

            logger.info("✅ PostgreSQL 설정 완료")

        else:
            # SQLite configuration (default for development)
            sqlite_path = self.airflow_home / 'airflow.db'
            sql_alchemy_conn = f"sqlite:///{sqlite_path}"

            logger.info(f"SQLite DB: {sqlite_path}")

            if 'database' not in self.config.sections():
                self.config.add_section('database')

            self.config.set('database', 'sql_alchemy_conn', sql_alchemy_conn)

            logger.info("✅ SQLite 설정 완료")

    def configure_core(self):
        """Configure core Airflow settings."""
        logger.info("\n" + "=" * 60)
        logger.info("Core 설정")
        logger.info("=" * 60)

        if 'core' not in self.config.sections():
            self.config.add_section('core')

        # DAGs folder
        dags_folder = self.airflow_home / 'dags'
        self.config.set('core', 'dags_folder', str(dags_folder))
        logger.info(f"DAGs folder: {dags_folder}")

        # Don't load example DAGs
        self.config.set('core', 'load_examples', 'False')
        logger.info("Example DAGs: Disabled")

        # Executor (LocalExecutor for development)
        self.config.set('core', 'executor', 'LocalExecutor')
        logger.info("Executor: LocalExecutor")

        # Default timezone
        self.config.set('core', 'default_timezone', 'Asia/Seoul')
        logger.info("Timezone: Asia/Seoul")

        # Parallelism
        self.config.set('core', 'parallelism', '32')
        self.config.set('core', 'max_active_tasks_per_dag', '16')
        self.config.set('core', 'max_active_runs_per_dag', '16')
        logger.info("Parallelism: 32 (max 16 tasks per DAG)")

        logger.info("✅ Core 설정 완료")

    def configure_webserver(self):
        """Configure webserver settings."""
        logger.info("\n" + "=" * 60)
        logger.info("Webserver 설정")
        logger.info("=" * 60)

        if 'webserver' not in self.config.sections():
            self.config.add_section('webserver')

        # Base URL
        self.config.set('webserver', 'base_url', 'http://localhost:8080')
        logger.info("Base URL: http://localhost:8080")

        # Expose config in UI
        self.config.set('webserver', 'expose_config', 'True')
        logger.info("Expose config: True")

        # Page size
        self.config.set('webserver', 'page_size', '100')
        logger.info("Page size: 100")

        logger.info("✅ Webserver 설정 완료")

    def configure_scheduler(self):
        """Configure scheduler settings."""
        logger.info("\n" + "=" * 60)
        logger.info("Scheduler 설정")
        logger.info("=" * 60)

        if 'scheduler' not in self.config.sections():
            self.config.add_section('scheduler')

        # Catchup by default
        self.config.set('scheduler', 'catchup_by_default', 'False')
        logger.info("Catchup by default: False")

        # DAG run timeout
        self.config.set('scheduler', 'dag_run_timeout', '86400')  # 24 hours
        logger.info("DAG run timeout: 24 hours")

        logger.info("✅ Scheduler 설정 완료")

    def configure_logging(self):
        """Configure logging settings."""
        logger.info("\n" + "=" * 60)
        logger.info("Logging 설정")
        logger.info("=" * 60)

        if 'logging' not in self.config.sections():
            self.config.add_section('logging')

        # Base log folder
        base_log_folder = self.airflow_home / 'logs'
        self.config.set('logging', 'base_log_folder', str(base_log_folder))
        logger.info(f"Log folder: {base_log_folder}")

        # Log level
        self.config.set('logging', 'logging_level', 'INFO')
        logger.info("Log level: INFO")

        logger.info("✅ Logging 설정 완료")

    def save_config(self):
        """Save configuration to file."""
        logger.info("\n" + "=" * 60)
        logger.info("설정 저장")
        logger.info("=" * 60)

        # Backup original config
        backup_file = self.config_file.with_suffix('.cfg.backup')
        if not backup_file.exists():
            import shutil
            shutil.copy2(self.config_file, backup_file)
            logger.info(f"백업 생성: {backup_file}")

        # Save config
        with open(self.config_file, 'w') as f:
            self.config.write(f)

        logger.info(f"✅ 설정 저장 완료: {self.config_file}")

    def create_airflow_db(self):
        """Create Airflow metadata database in PostgreSQL."""
        logger.info("\n" + "=" * 60)
        logger.info("Airflow 메타 DB 생성")
        logger.info("=" * 60)

        import subprocess

        db_name = "airflow_db"

        # Check if database exists
        check_cmd = f"psql -lqt | cut -d \\| -f 1 | grep -qw {db_name}"

        try:
            result = subprocess.run(
                check_cmd,
                shell=True,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                logger.info(f"✅ 데이터베이스 '{db_name}'이(가) 이미 존재합니다.")
            else:
                # Create database
                logger.info(f"데이터베이스 '{db_name}' 생성 중...")
                create_cmd = f"createdb {db_name}"

                result = subprocess.run(
                    create_cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    check=True
                )

                logger.info(f"✅ 데이터베이스 '{db_name}' 생성 완료")

        except subprocess.CalledProcessError as e:
            logger.error(f"❌ 데이터베이스 생성 실패: {e}")
            logger.error(f"stdout: {e.stdout}")
            logger.error(f"stderr: {e.stderr}")
            logger.warning("SQLite를 사용하려면 configure_database(use_postgres=False)를 호출하세요.")

    def initialize_db(self):
        """Initialize Airflow database."""
        logger.info("\n" + "=" * 60)
        logger.info("Airflow DB 초기화")
        logger.info("=" * 60)

        import subprocess

        try:
            # Run airflow db upgrade
            logger.info("airflow db upgrade 실행 중...")

            result = subprocess.run(
                ['airflow', 'db', 'upgrade'],
                capture_output=True,
                text=True,
                check=True
            )

            logger.info("✅ Airflow DB 초기화 완료")

        except subprocess.CalledProcessError as e:
            logger.error(f"❌ DB 초기화 실패: {e}")
            logger.error(f"stdout: {e.stdout}")
            logger.error(f"stderr: {e.stderr}")
            sys.exit(1)


def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Airflow 설정 스크립트'
    )

    parser.add_argument(
        '--postgres',
        action='store_true',
        help='PostgreSQL 메타 DB 사용 (기본값: SQLite)'
    )
    parser.add_argument(
        '--airflow-home',
        type=str,
        help='Airflow home directory (기본값: PROJECT_ROOT/airflow)'
    )

    args = parser.parse_args()

    # Determine Airflow home
    if args.airflow_home:
        airflow_home = Path(args.airflow_home)
    else:
        airflow_home = project_root / 'airflow'

    logger.info("=" * 60)
    logger.info("Airflow 설정 시작")
    logger.info("=" * 60)
    logger.info(f"Airflow Home: {airflow_home}")
    logger.info(f"PostgreSQL: {'Yes' if args.postgres else 'No (SQLite)'}")
    logger.info("")

    # Create configurator
    configurator = AirflowConfigurator(airflow_home)

    # Create PostgreSQL database if needed
    if args.postgres:
        configurator.create_airflow_db()

    # Configure settings
    configurator.configure_database(use_postgres=args.postgres)
    configurator.configure_core()
    configurator.configure_webserver()
    configurator.configure_scheduler()
    configurator.configure_logging()

    # Save configuration
    configurator.save_config()

    # Initialize database
    configurator.initialize_db()

    logger.info("\n" + "=" * 60)
    logger.info("✅ Airflow 설정 완료!")
    logger.info("=" * 60)
    logger.info("\n다음 단계:")
    logger.info("  1. Airflow 시작: ./scripts/start_airflow.sh")
    logger.info("  2. 웹 UI 접속: http://localhost:8080")
    logger.info("  3. Username: admin, Password: admin")
    logger.info("")


if __name__ == '__main__':
    main()
