"""테스트 DAG.

Airflow 설치 및 설정이 올바르게 되었는지 확인하는 간단한 테스트 DAG입니다.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook


# Default arguments
default_args = {
    'owner': 'stock-portfolio-system',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}


def print_context(**context):
    """Print execution context."""
    print("=" * 60)
    print("Airflow Context:")
    print("=" * 60)
    print(f"Execution date: {context['execution_date']}")
    print(f"DAG: {context['dag'].dag_id}")
    print(f"Task: {context['task'].task_id}")
    print(f"Run ID: {context['run_id']}")
    print("=" * 60)


def test_postgres_connection(**context):
    """Test PostgreSQL connection."""
    print("\n" + "=" * 60)
    print("PostgreSQL Connection Test")
    print("=" * 60)

    try:
        # Get PostgreSQL hook
        pg_hook = PostgresHook(postgres_conn_id='postgres_stock_portfolio')

        # Execute simple query
        sql = "SELECT version();"
        records = pg_hook.get_records(sql)

        if records:
            print(f"✅ PostgreSQL 연결 성공")
            print(f"Version: {records[0][0]}")
        else:
            print("❌ PostgreSQL 연결 실패: No records")

        # Test stock count
        sql = "SELECT COUNT(*) FROM stocks;"
        records = pg_hook.get_records(sql)

        if records:
            stock_count = records[0][0]
            print(f"✅ Stocks table 조회 성공: {stock_count:,}개 종목")
        else:
            print("⚠️  Stocks table 조회 실패")

    except Exception as e:
        print(f"❌ PostgreSQL 연결 실패: {e}")
        raise

    print("=" * 60)


def test_python_environment(**context):
    """Test Python environment and imports."""
    print("\n" + "=" * 60)
    print("Python Environment Test")
    print("=" * 60)

    import sys
    import platform

    print(f"Python version: {sys.version}")
    print(f"Platform: {platform.platform()}")
    print(f"Python path: {sys.executable}")

    # Test project imports
    print("\nTesting project imports...")

    try:
        from models import Stock, DailyPrice
        print("✅ models 모듈 import 성공")
    except ImportError as e:
        print(f"❌ models 모듈 import 실패: {e}")

    try:
        from collectors import PyKRXPriceCollector
        print("✅ collectors 모듈 import 성공")
    except ImportError as e:
        print(f"❌ collectors 모듈 import 실패: {e}")

    try:
        import pandas as pd
        import numpy as np
        print(f"✅ pandas {pd.__version__}, numpy {np.__version__}")
    except ImportError as e:
        print(f"❌ pandas/numpy import 실패: {e}")

    print("=" * 60)


# Create DAG
with DAG(
    dag_id='test_dag',
    default_args=default_args,
    description='테스트 DAG - Airflow 설정 검증',
    schedule_interval=None,  # Manual trigger only
    start_date=datetime(2025, 1, 24),
    catchup=False,
    tags=['test', 'setup'],
) as dag:

    # Task 1: Print context
    task_print_context = PythonOperator(
        task_id='print_context',
        python_callable=print_context,
        provide_context=True,
    )

    # Task 2: Test Python environment
    task_test_python = PythonOperator(
        task_id='test_python_environment',
        python_callable=test_python_environment,
        provide_context=True,
    )

    # Task 3: Echo test
    task_echo = BashOperator(
        task_id='echo_test',
        bash_command='echo "✅ Bash operator working!" && date',
    )

    # Task 4: Test PostgreSQL connection
    task_test_postgres = PythonOperator(
        task_id='test_postgres_connection',
        python_callable=test_postgres_connection,
        provide_context=True,
    )

    # Task 5: Success message
    task_success = BashOperator(
        task_id='success',
        bash_command='echo "✅ All tests passed! Airflow is ready to use."',
    )

    # Define task dependencies
    task_print_context >> task_test_python >> task_echo >> task_test_postgres >> task_success


# DAG Documentation
dag.doc_md = """
# Test DAG

Airflow 설치 및 설정을 검증하는 테스트 DAG입니다.

## Tasks

1. **print_context**: Airflow 실행 컨텍스트 출력
2. **test_python_environment**: Python 환경 및 모듈 import 테스트
3. **echo_test**: Bash operator 테스트
4. **test_postgres_connection**: PostgreSQL 연결 테스트
5. **success**: 모든 테스트 통과 메시지

## 실행 방법

1. Airflow 웹 UI 접속: http://localhost:8080
2. DAGs 목록에서 `test_dag` 찾기
3. 토글 버튼을 ON으로 변경
4. "Trigger DAG" 버튼 클릭

## 검증 항목

- ✅ Airflow가 정상적으로 설치됨
- ✅ Python operator가 작동함
- ✅ Bash operator가 작동함
- ✅ PostgreSQL connection이 설정됨
- ✅ 프로젝트 모듈을 import할 수 있음
"""
