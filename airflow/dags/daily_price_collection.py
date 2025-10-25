"""
Daily Price Collection DAG

Collects daily stock prices for all KOSPI/KOSDAQ stocks and saves to database.
Scheduled to run daily at 6 PM KST.

Author: Stock Portfolio System
Created: 2025-10-25
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any
import logging

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from airflow.models import Variable

# Import notification callbacks
from utils.notification_callbacks import (
    task_failure_callback,
    task_success_callback,
    dag_failure_callback,
    dag_success_callback
)

# Project imports (ensure project root is in PYTHONPATH)
import sys
import os

# Add project root to sys.path
PROJECT_ROOT = '/Users/sunchulkim/src/stock-portfolio-system'
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import func, and_
from sqlalchemy.orm import Session
from db.connection import SessionLocal
from models import Stock, DailyPrice, MarketType
from collectors.pykrx_price_collector import PyKRXPriceCollector
from loguru import logger

# Configure loguru logger
logger.add(
    "/Users/sunchulkim/src/stock-portfolio-system/logs/airflow_daily_price_{time}.log",
    rotation="1 day",
    retention="30 days",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
)

# Default arguments for the DAG
default_args = {
    'owner': 'stock-portfolio',
    'depends_on_past': False,
    'email': ['admin@example.com'],  # TODO: Update with actual email
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'execution_timeout': timedelta(minutes=45),
    'on_failure_callback': task_failure_callback,
    'on_success_callback': task_success_callback,
}


def get_stocks_to_update(**context) -> List[Dict[str, Any]]:
    """
    Get list of stocks that need price updates.

    Returns:
        List of dicts with stock info (id, ticker, name, market)
    """
    logger.info("📊 Fetching stocks that need price updates...")

    db = SessionLocal()
    try:
        # Get all active stocks (not delisted or delisted recently)
        today = datetime.now().date()

        stocks = db.query(Stock).filter(
            and_(
                Stock.is_active == True,
                (Stock.delisting_date.is_(None) | (Stock.delisting_date >= today))
            )
        ).all()

        stock_list = [
            {
                'id': stock.id,
                'ticker': stock.ticker,
                'name': stock.name,
                'market': stock.market.value
            }
            for stock in stocks
        ]

        logger.info(f"✅ Found {len(stock_list)} active stocks to update")

        # Push to XCom for next task
        context['task_instance'].xcom_push(key='stock_list', value=stock_list)
        context['task_instance'].xcom_push(key='total_stocks', value=len(stock_list))

        return stock_list

    except Exception as e:
        logger.error(f"❌ Error fetching stocks: {e}")
        raise
    finally:
        db.close()


def collect_daily_prices(**context) -> Dict[str, int]:
    """
    Collect daily prices for all stocks using PyKRX collector.

    Returns:
        Statistics dict with success/failure counts
    """
    # Get stock list from previous task
    task_instance = context['task_instance']
    stock_list = task_instance.xcom_pull(task_ids='get_stocks_to_update', key='stock_list')

    if not stock_list:
        logger.warning("⚠️ No stocks to update")
        return {'success': 0, 'failed': 0, 'total': 0}

    logger.info(f"🔄 Starting price collection for {len(stock_list)} stocks...")

    # Get execution date (yesterday's date for daily prices)
    execution_date = context['execution_date']
    target_date = execution_date.date()

    logger.info(f"📅 Target date: {target_date}")

    stats = {
        'success': 0,
        'failed': 0,
        'total': len(stock_list),
        'skipped': 0
    }

    failed_stocks = []

    with PyKRXPriceCollector() as collector:
        for idx, stock_info in enumerate(stock_list, 1):
            ticker = stock_info['ticker']
            stock_name = stock_info['name']

            try:
                logger.info(f"[{idx}/{len(stock_list)}] Collecting {ticker} ({stock_name})...")

                # Collect single day price
                date_str = target_date.strftime('%Y%m%d')

                success = collector.collect_price_data(
                    ticker=ticker,
                    start_date=date_str,
                    end_date=date_str,
                    stock_id=stock_info['id']
                )

                if success:
                    stats['success'] += 1
                    logger.info(f"✅ Successfully collected {ticker}")
                else:
                    stats['skipped'] += 1
                    logger.warning(f"⚠️ No data for {ticker} (possibly holiday/weekend)")

            except Exception as e:
                stats['failed'] += 1
                failed_stocks.append({'ticker': ticker, 'name': stock_name, 'error': str(e)})
                logger.error(f"❌ Failed to collect {ticker}: {e}")

            # Log progress every 100 stocks
            if idx % 100 == 0:
                logger.info(f"📊 Progress: {idx}/{len(stock_list)} | Success: {stats['success']} | Failed: {stats['failed']}")

    # Final statistics
    logger.info(f"""
    ✅ Daily Price Collection Complete!
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    Total Stocks:    {stats['total']}
    Success:         {stats['success']}
    Skipped:         {stats['skipped']}
    Failed:          {stats['failed']}
    Success Rate:    {(stats['success']/stats['total']*100):.2f}%
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """)

    # Push stats to XCom
    task_instance.xcom_push(key='collection_stats', value=stats)
    task_instance.xcom_push(key='failed_stocks', value=failed_stocks)

    # Raise error if too many failures (>10%)
    if stats['failed'] > stats['total'] * 0.1:
        raise Exception(f"Too many failures: {stats['failed']}/{stats['total']} stocks failed")

    return stats


def validate_collection(**context) -> bool:
    """
    Validate that price collection was successful.

    Returns:
        True if validation passes
    """
    task_instance = context['task_instance']
    stats = task_instance.xcom_pull(task_ids='collect_daily_prices', key='collection_stats')

    if not stats:
        raise Exception("No collection statistics found")

    logger.info("🔍 Validating price collection...")

    # Check success rate
    success_rate = (stats['success'] / stats['total']) * 100 if stats['total'] > 0 else 0

    logger.info(f"Success rate: {success_rate:.2f}%")

    # Validation criteria: at least 90% success rate
    if success_rate < 90.0:
        raise Exception(f"Validation failed: Success rate {success_rate:.2f}% is below 90%")

    logger.info("✅ Validation passed!")
    return True


def send_completion_report(**context) -> None:
    """
    Send completion report with collection statistics.
    This will be used for email/Slack notifications.
    """
    task_instance = context['task_instance']
    stats = task_instance.xcom_pull(task_ids='collect_daily_prices', key='collection_stats')
    failed_stocks = task_instance.xcom_pull(task_ids='collect_daily_prices', key='failed_stocks')

    execution_date = context['execution_date']

    report = f"""
    📊 Daily Price Collection Report
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    Date: {execution_date.strftime('%Y-%m-%d')}

    📈 Statistics:
    - Total Stocks: {stats['total']}
    - Successful: {stats['success']}
    - Skipped: {stats['skipped']}
    - Failed: {stats['failed']}
    - Success Rate: {(stats['success']/stats['total']*100):.2f}%

    """

    if failed_stocks:
        report += f"\n❌ Failed Stocks ({len(failed_stocks)}):\n"
        for stock in failed_stocks[:10]:  # Show first 10
            report += f"  - {stock['ticker']} ({stock['name']}): {stock['error']}\n"
        if len(failed_stocks) > 10:
            report += f"  ... and {len(failed_stocks) - 10} more\n"

    logger.info(report)

    # Push report to XCom for email callback
    task_instance.xcom_push(key='completion_report', value=report)


# Define the DAG
with DAG(
    dag_id='daily_price_collection',
    default_args=default_args,
    description='Collect daily stock prices for all KOSPI/KOSDAQ stocks',
    schedule='0 18 * * 1-5',  # 6 PM KST, Monday-Friday
    start_date=datetime(2025, 1, 25),
    catchup=False,
    tags=['stock', 'price', 'daily', 'collection'],
    max_active_runs=1,  # Only one run at a time
    on_failure_callback=dag_failure_callback,
    on_success_callback=dag_success_callback,
) as dag:

    # Task 1: Get stocks to update
    task_get_stocks = PythonOperator(
        task_id='get_stocks_to_update',
        python_callable=get_stocks_to_update,
        doc_md="""
        ### Get Stocks to Update

        Fetches all active stocks from database that need daily price updates.
        Excludes delisted stocks.

        **Output**: List of stock dictionaries pushed to XCom
        """
    )

    # Task 2: Collect daily prices
    task_collect_prices = PythonOperator(
        task_id='collect_daily_prices',
        python_callable=collect_daily_prices,
        doc_md="""
        ### Collect Daily Prices

        Collects daily price data using PyKRX collector.
        Target date is the execution date.

        **Input**: Stock list from XCom
        **Output**: Collection statistics pushed to XCom
        """
    )

    # Task 3: Validate collection
    task_validate = PythonOperator(
        task_id='validate_collection',
        python_callable=validate_collection,
        doc_md="""
        ### Validate Collection

        Validates that collection was successful:
        - Success rate >= 90%
        - No critical errors

        **Raises**: Exception if validation fails
        """
    )

    # Task 4: Send completion report
    task_report = PythonOperator(
        task_id='send_completion_report',
        python_callable=send_completion_report,
        trigger_rule='all_done',  # Run even if upstream fails
        doc_md="""
        ### Send Completion Report

        Generates and logs completion report with statistics.
        Can be extended to send email/Slack notifications.
        """
    )

    # Define task dependencies
    task_get_stocks >> task_collect_prices >> task_validate >> task_report


# DAG documentation
dag.doc_md = """
# Daily Price Collection DAG

## Overview
Automated daily collection of stock prices for all KOSPI/KOSDAQ stocks.

## Schedule
- **Frequency**: Daily at 6:00 PM KST
- **Days**: Monday - Friday (trading days)
- **Duration**: ~30 minutes for 2,500 stocks

## Tasks
1. **get_stocks_to_update**: Fetch active stocks from database
2. **collect_daily_prices**: Collect prices using PyKRX API
3. **validate_collection**: Validate success rate >= 90%
4. **send_completion_report**: Generate completion report

## Data Source
- **API**: PyKRX (KRX public data)
- **Rate Limit**: None (public API)
- **Authentication**: Not required

## Error Handling
- Automatic retry: 2 attempts with 5-minute delay
- Email notification on failure
- Validation fails if success rate < 90%

## Monitoring
- Check Airflow UI for DAG runs
- Review logs at: `/logs/airflow_daily_price_*.log`
- XCom data includes detailed statistics

## Manual Execution
To run manually:
```bash
airflow dags trigger daily_price_collection
```

To backfill for specific date:
```bash
airflow dags backfill daily_price_collection -s 2025-01-20 -e 2025-01-20
```
"""
