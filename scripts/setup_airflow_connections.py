#!/usr/bin/env python3
"""Airflow Connections 설정 스크립트.

PostgreSQL, DART API, KIS API 등의 Connection을 Airflow에 등록합니다.
"""

import os
import sys
from pathlib import Path
import subprocess
import json

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


class AirflowConnectionManager:
    """Airflow Connection 관리 클래스."""

    def __init__(self):
        """Initialize connection manager."""
        self.connections = []

    def add_postgres_connection(self):
        """Add PostgreSQL connection."""
        logger.info("\n1. PostgreSQL Connection 설정")

        db_host = os.getenv("DB_HOST", "localhost")
        db_port = os.getenv("DB_PORT", "5432")
        db_name = os.getenv("DB_NAME", "stock_portfolio")
        db_user = os.getenv("DB_USER", os.getenv("USER"))
        db_password = os.getenv("DB_PASSWORD", "")

        conn_id = "postgres_stock_portfolio"

        # Build connection URI
        if db_password:
            conn_uri = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        else:
            conn_uri = f"postgresql://{db_user}@{db_host}:{db_port}/{db_name}"

        self.connections.append({
            'conn_id': conn_id,
            'conn_type': 'postgres',
            'description': 'Stock Portfolio PostgreSQL Database',
            'host': db_host,
            'port': db_port,
            'schema': db_name,
            'login': db_user,
            'password': db_password,
            'uri': conn_uri
        })

        logger.info(f"  Connection ID: {conn_id}")
        logger.info(f"  Host: {db_host}:{db_port}")
        logger.info(f"  Database: {db_name}")
        logger.info(f"  User: {db_user}")

    def add_dart_api_connection(self):
        """Add DART API connection."""
        logger.info("\n2. DART API Connection 설정")

        dart_api_key = os.getenv("DART_API_KEY", "")

        if not dart_api_key:
            logger.warning("  ⚠️  DART_API_KEY가 .env에 설정되지 않았습니다.")
            logger.warning("  Connection을 수동으로 설정해야 합니다.")
            return

        conn_id = "dart_api"
        base_url = "https://opendart.fss.or.kr/api"

        self.connections.append({
            'conn_id': conn_id,
            'conn_type': 'http',
            'description': 'DART OpenAPI',
            'host': base_url,
            'extra': json.dumps({
                'api_key': dart_api_key
            })
        })

        logger.info(f"  Connection ID: {conn_id}")
        logger.info(f"  Base URL: {base_url}")
        logger.info(f"  API Key: {'*' * 20}")

    def add_kis_api_connection(self):
        """Add KIS API connection."""
        logger.info("\n3. KIS API Connection 설정")

        kis_app_key = os.getenv("KIS_APP_KEY", "")
        kis_app_secret = os.getenv("KIS_APP_SECRET", "")
        kis_account_type = os.getenv("KIS_ACCOUNT_TYPE", "VIRTUAL")

        if not kis_app_key or not kis_app_secret:
            logger.warning("  ⚠️  KIS_APP_KEY 또는 KIS_APP_SECRET이 설정되지 않았습니다.")
            logger.warning("  Connection을 수동으로 설정해야 합니다.")
            return

        conn_id = "kis_api"
        base_url = "https://openapi.koreainvestment.com:9443"

        self.connections.append({
            'conn_id': conn_id,
            'conn_type': 'http',
            'description': 'Korea Investment Securities API',
            'host': base_url,
            'extra': json.dumps({
                'app_key': kis_app_key,
                'app_secret': kis_app_secret,
                'account_type': kis_account_type
            })
        })

        logger.info(f"  Connection ID: {conn_id}")
        logger.info(f"  Base URL: {base_url}")
        logger.info(f"  Account Type: {kis_account_type}")
        logger.info(f"  App Key: {'*' * 20}")

    def create_connections(self):
        """Create all connections in Airflow."""
        logger.info("\n" + "=" * 60)
        logger.info("Airflow Connections 생성")
        logger.info("=" * 60)

        for conn in self.connections:
            self._create_connection(conn)

        logger.info("\n✅ 모든 Connection 생성 완료")

    def _create_connection(self, conn: dict):
        """Create a single connection using Airflow CLI.

        Args:
            conn: Connection dictionary
        """
        conn_id = conn['conn_id']

        # Delete existing connection if exists
        delete_cmd = ['airflow', 'connections', 'delete', conn_id]

        try:
            subprocess.run(
                delete_cmd,
                capture_output=True,
                text=True
            )
        except:
            pass  # Connection doesn't exist, which is fine

        # Create new connection
        add_cmd = ['airflow', 'connections', 'add', conn_id]

        # Add connection parameters
        if 'uri' in conn:
            add_cmd.extend(['--conn-uri', conn['uri']])
        else:
            if 'conn_type' in conn:
                add_cmd.extend(['--conn-type', conn['conn_type']])
            if 'host' in conn:
                add_cmd.extend(['--conn-host', conn['host']])
            if 'port' in conn:
                add_cmd.extend(['--conn-port', str(conn['port'])])
            if 'schema' in conn:
                add_cmd.extend(['--conn-schema', conn['schema']])
            if 'login' in conn:
                add_cmd.extend(['--conn-login', conn['login']])
            if 'password' in conn and conn['password']:
                add_cmd.extend(['--conn-password', conn['password']])
            if 'extra' in conn:
                add_cmd.extend(['--conn-extra', conn['extra']])

        if 'description' in conn:
            add_cmd.extend(['--conn-description', conn['description']])

        try:
            logger.info(f"\n생성 중: {conn_id}")

            result = subprocess.run(
                add_cmd,
                capture_output=True,
                text=True,
                check=True
            )

            logger.info(f"  ✅ {conn_id} 생성 완료")

        except subprocess.CalledProcessError as e:
            logger.error(f"  ❌ {conn_id} 생성 실패")
            logger.error(f"  Error: {e.stderr}")

    def list_connections(self):
        """List all connections in Airflow."""
        logger.info("\n" + "=" * 60)
        logger.info("Airflow Connections 목록")
        logger.info("=" * 60)

        try:
            result = subprocess.run(
                ['airflow', 'connections', 'list', '--output', 'table'],
                capture_output=True,
                text=True,
                check=True
            )

            print(result.stdout)

        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Connection 목록 조회 실패: {e}")


def main():
    """Main function."""
    logger.info("=" * 60)
    logger.info("Airflow Connections 설정 시작")
    logger.info("=" * 60)

    manager = AirflowConnectionManager()

    # Add connections
    manager.add_postgres_connection()
    manager.add_dart_api_connection()
    manager.add_kis_api_connection()

    # Create connections in Airflow
    manager.create_connections()

    # List all connections
    manager.list_connections()

    logger.info("\n" + "=" * 60)
    logger.info("✅ Connections 설정 완료!")
    logger.info("=" * 60)
    logger.info("\nAirflow 웹 UI에서 확인:")
    logger.info("  http://localhost:8080/connection/list/")
    logger.info("")


if __name__ == '__main__':
    main()
