"""
Quarterly Financial Statement Collection DAG

Collects quarterly financial statements from DART API and calculates financial ratios.
Scheduled to run 45 days after each quarter end (allows time for filing).

Author: Stock Portfolio System
Created: 2025-10-25
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models import Variable

# Project imports
import sys
import os

# Add project root to sys.path
PROJECT_ROOT = '/Users/sunchulkim/src/stock-portfolio-system'
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Import notification callbacks
from utils.notification_callbacks import (
    task_failure_callback,
    task_success_callback,
    dag_failure_callback,
    dag_success_callback
)

from sqlalchemy import func, and_, desc
from sqlalchemy.orm import Session
from db.connection import SessionLocal
from models import Stock, FinancialStatement, FinancialRatio, CorpCodeMap
from collectors.dart_collector import DARTCollector
from calculators.financial_ratio_calculator import FinancialRatioCalculator
from loguru import logger

# Configure loguru logger
logger.add(
    "/Users/sunchulkim/src/stock-portfolio-system/logs/airflow_quarterly_financial_{time}.log",
    rotation="1 day",
    retention="30 days",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
)

# Default arguments for the DAG
default_args = {
    'owner': 'stock-portfolio',
    'depends_on_past': False,
    'email': ['admin@example.com'],
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 3,
    'retry_delay': timedelta(minutes=10),
    'execution_timeout': timedelta(hours=2),
    'on_failure_callback': task_failure_callback,
    'on_success_callback': task_success_callback,
}


def get_target_quarter(**context) -> Dict[str, str]:
    """
    Calculate target quarter for financial statement collection.
    Runs 45 days after quarter end.

    Returns:
        Dict with year and quarter information
    """
    execution_date = context['execution_date']

    # Calculate which quarter's statements we should collect
    # (45 days ago from execution date)
    target_date = execution_date - timedelta(days=45)

    year = target_date.year
    month = target_date.month

    # Determine quarter
    if month <= 3:
        quarter = 1
    elif month <= 6:
        quarter = 2
    elif month <= 9:
        quarter = 3
    else:
        quarter = 4

    quarter_info = {
        'year': str(year),
        'quarter': f'Q{quarter}',
        'reprt_code': f'110{quarter}3',  # DART report code (11013, 11023, 11033, 11043)
        'bsns_year': str(year)
    }

    logger.info(f"📅 Target quarter: {year} {quarter_info['quarter']}")
    logger.info(f"📋 DART report code: {quarter_info['reprt_code']}")

    # Push to XCom
    context['task_instance'].xcom_push(key='quarter_info', value=quarter_info)

    return quarter_info


def get_stocks_with_corp_code(**context) -> List[Dict[str, Any]]:
    """
    Get list of stocks with DART corp_code mapping.

    Returns:
        List of stock dictionaries with corp_code
    """
    logger.info("📊 Fetching stocks with DART corp_code...")

    db = SessionLocal()
    try:
        # Get stocks that have corp_code mapping
        stocks = db.query(Stock, CorpCodeMap).join(
            CorpCodeMap,
            Stock.id == CorpCodeMap.stock_id
        ).filter(
            Stock.is_active == True
        ).all()

        stock_list = [
            {
                'id': stock.id,
                'ticker': stock.ticker,
                'name': stock.name,
                'market': stock.market.value,
                'corp_code': corp_map.corp_code
            }
            for stock, corp_map in stocks
        ]

        logger.info(f"✅ Found {len(stock_list)} stocks with DART corp_code")

        # Push to XCom
        context['task_instance'].xcom_push(key='stock_list', value=stock_list)
        context['task_instance'].xcom_push(key='total_stocks', value=len(stock_list))

        return stock_list

    except Exception as e:
        logger.error(f"❌ Error fetching stocks: {e}")
        raise
    finally:
        db.close()


def collect_financial_statements(**context) -> Dict[str, int]:
    """
    Collect quarterly financial statements from DART API.

    Returns:
        Statistics dict with success/failure counts
    """
    task_instance = context['task_instance']

    # Get inputs from previous tasks
    stock_list = task_instance.xcom_pull(task_ids='get_stocks_with_corp_code', key='stock_list')
    quarter_info = task_instance.xcom_pull(task_ids='get_target_quarter', key='quarter_info')

    if not stock_list or not quarter_info:
        logger.warning("⚠️ No stocks or quarter info found")
        return {'success': 0, 'failed': 0, 'total': 0, 'skipped': 0}

    logger.info(f"🔄 Collecting financial statements for {len(stock_list)} stocks...")
    logger.info(f"📅 Target: {quarter_info['year']} {quarter_info['quarter']}")

    stats = {
        'success': 0,
        'failed': 0,
        'total': len(stock_list),
        'skipped': 0,
        'already_exists': 0
    }

    failed_stocks = []

    with DARTCollector() as collector:
        for idx, stock_info in enumerate(stock_list, 1):
            corp_code = stock_info['corp_code']
            stock_name = stock_info['name']
            stock_id = stock_info['id']

            try:
                logger.info(f"[{idx}/{len(stock_list)}] Collecting {stock_name} ({corp_code})...")

                # Collect financial statement
                success = collector.collect_financial_statement(
                    corp_code=corp_code,
                    bsns_year=quarter_info['bsns_year'],
                    reprt_code=quarter_info['reprt_code'],
                    stock_id=stock_id
                )

                if success:
                    stats['success'] += 1
                    logger.info(f"✅ Successfully collected {stock_name}")
                else:
                    stats['skipped'] += 1
                    logger.warning(f"⚠️ No data or already exists for {stock_name}")

            except Exception as e:
                stats['failed'] += 1
                failed_stocks.append({
                    'corp_code': corp_code,
                    'name': stock_name,
                    'error': str(e)
                })
                logger.error(f"❌ Failed to collect {stock_name}: {e}")

            # Log progress every 50 stocks
            if idx % 50 == 0:
                logger.info(f"📊 Progress: {idx}/{len(stock_list)} | Success: {stats['success']} | Failed: {stats['failed']}")

    # Final statistics
    logger.info(f"""
    ✅ Financial Statement Collection Complete!
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

    # Raise error if too many failures (>20%)
    if stats['failed'] > stats['total'] * 0.2:
        raise Exception(f"Too many failures: {stats['failed']}/{stats['total']} stocks failed")

    return stats


def calculate_financial_ratios(**context) -> Dict[str, int]:
    """
    Calculate financial ratios for newly collected statements.

    Returns:
        Statistics dict with calculation counts
    """
    task_instance = context['task_instance']
    quarter_info = task_instance.xcom_pull(task_ids='get_target_quarter', key='quarter_info')
    collection_stats = task_instance.xcom_pull(task_ids='collect_financial_statements', key='collection_stats')

    if not quarter_info:
        logger.warning("⚠️ No quarter info found")
        return {'success': 0, 'failed': 0, 'total': 0}

    logger.info(f"🧮 Calculating financial ratios for {quarter_info['year']} {quarter_info['quarter']}...")

    db = SessionLocal()
    calculator = FinancialRatioCalculator()

    stats = {
        'success': 0,
        'failed': 0,
        'total': 0,
        'skipped': 0
    }

    failed_calculations = []

    try:
        # Get all financial statements for this quarter
        statements = db.query(FinancialStatement).filter(
            FinancialStatement.fiscal_year == int(quarter_info['year']),
            FinancialStatement.fiscal_quarter == int(quarter_info['quarter'][1])  # Extract number from 'Q1', 'Q2', etc.
        ).all()

        stats['total'] = len(statements)
        logger.info(f"Found {stats['total']} statements to process")

        for idx, statement in enumerate(statements, 1):
            try:
                # Calculate ratios
                ratios = calculator.calculate_all_ratios(statement)

                if ratios:
                    # Save to database
                    db.add(ratios)
                    db.commit()
                    stats['success'] += 1

                    if idx % 50 == 0:
                        logger.info(f"📊 Progress: {idx}/{stats['total']} ratios calculated")
                else:
                    stats['skipped'] += 1
                    logger.warning(f"⚠️ Could not calculate ratios for statement {statement.id}")

            except Exception as e:
                stats['failed'] += 1
                failed_calculations.append({
                    'statement_id': statement.id,
                    'stock_id': statement.stock_id,
                    'error': str(e)
                })
                logger.error(f"❌ Failed to calculate ratios for statement {statement.id}: {e}")
                db.rollback()

        logger.info(f"""
        ✅ Financial Ratio Calculation Complete!
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        Total Statements: {stats['total']}
        Success:          {stats['success']}
        Skipped:          {stats['skipped']}
        Failed:           {stats['failed']}
        Success Rate:     {(stats['success']/stats['total']*100) if stats['total'] > 0 else 0:.2f}%
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        """)

        # Push stats to XCom
        task_instance.xcom_push(key='ratio_stats', value=stats)
        task_instance.xcom_push(key='failed_calculations', value=failed_calculations)

    except Exception as e:
        logger.error(f"❌ Error in ratio calculation: {e}")
        raise
    finally:
        db.close()

    return stats


def validate_data_quality(**context) -> bool:
    """
    Validate quality of collected financial data.

    Returns:
        True if validation passes
    """
    task_instance = context['task_instance']
    collection_stats = task_instance.xcom_pull(task_ids='collect_financial_statements', key='collection_stats')
    ratio_stats = task_instance.xcom_pull(task_ids='calculate_financial_ratios', key='ratio_stats')

    if not collection_stats or not ratio_stats:
        raise Exception("No statistics found for validation")

    logger.info("🔍 Validating data quality...")

    # Validation criteria
    validations = []

    # 1. Collection success rate >= 80%
    collection_success_rate = (collection_stats['success'] / collection_stats['total']) * 100 if collection_stats['total'] > 0 else 0
    validations.append({
        'check': 'Collection success rate >= 80%',
        'value': f"{collection_success_rate:.2f}%",
        'passed': collection_success_rate >= 80.0
    })

    # 2. Ratio calculation success rate >= 90%
    ratio_success_rate = (ratio_stats['success'] / ratio_stats['total']) * 100 if ratio_stats['total'] > 0 else 0
    validations.append({
        'check': 'Ratio calculation success rate >= 90%',
        'value': f"{ratio_success_rate:.2f}%",
        'passed': ratio_success_rate >= 90.0
    })

    # 3. At least 1000 statements collected
    validations.append({
        'check': 'At least 1000 statements collected',
        'value': f"{collection_stats['success']} statements",
        'passed': collection_stats['success'] >= 1000
    })

    # Print validation results
    logger.info("Validation Results:")
    for validation in validations:
        status = "✅ PASS" if validation['passed'] else "❌ FAIL"
        logger.info(f"  {status} | {validation['check']}: {validation['value']}")

    # Overall validation
    all_passed = all(v['passed'] for v in validations)

    if not all_passed:
        failed_checks = [v['check'] for v in validations if not v['passed']]
        raise Exception(f"Data quality validation failed: {', '.join(failed_checks)}")

    logger.info("✅ All data quality checks passed!")
    return True


def send_completion_report(**context) -> None:
    """
    Send completion report with collection and calculation statistics.
    """
    task_instance = context['task_instance']
    quarter_info = task_instance.xcom_pull(task_ids='get_target_quarter', key='quarter_info')
    collection_stats = task_instance.xcom_pull(task_ids='collect_financial_statements', key='collection_stats')
    ratio_stats = task_instance.xcom_pull(task_ids='calculate_financial_ratios', key='ratio_stats')
    failed_stocks = task_instance.xcom_pull(task_ids='collect_financial_statements', key='failed_stocks')

    execution_date = context['execution_date']

    report = f"""
    📊 Quarterly Financial Statement Collection Report
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    Execution Date: {execution_date.strftime('%Y-%m-%d')}
    Target Quarter: {quarter_info['year']} {quarter_info['quarter']}

    📈 Collection Statistics:
    - Total Stocks:    {collection_stats['total']}
    - Successful:      {collection_stats['success']}
    - Skipped:         {collection_stats['skipped']}
    - Failed:          {collection_stats['failed']}
    - Success Rate:    {(collection_stats['success']/collection_stats['total']*100):.2f}%

    🧮 Ratio Calculation Statistics:
    - Total Statements: {ratio_stats['total']}
    - Successful:       {ratio_stats['success']}
    - Skipped:          {ratio_stats['skipped']}
    - Failed:           {ratio_stats['failed']}
    - Success Rate:     {(ratio_stats['success']/ratio_stats['total']*100) if ratio_stats['total'] > 0 else 0:.2f}%
    """

    if failed_stocks:
        report += f"\n❌ Failed Stocks ({len(failed_stocks)}):\n"
        for stock in failed_stocks[:10]:
            report += f"  - {stock['name']}: {stock['error']}\n"
        if len(failed_stocks) > 10:
            report += f"  ... and {len(failed_stocks) - 10} more\n"

    logger.info(report)

    # Push report to XCom
    task_instance.xcom_push(key='completion_report', value=report)


# Define the DAG
with DAG(
    dag_id='quarterly_financial_statement',
    default_args=default_args,
    description='Collect quarterly financial statements from DART and calculate ratios',
    schedule='0 0 15 2,5,8,11 *',  # 45 days after quarter end (Feb 15, May 15, Aug 15, Nov 15)
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=['stock', 'financial', 'quarterly', 'dart'],
    max_active_runs=1,
    on_failure_callback=dag_failure_callback,
    on_success_callback=dag_success_callback,
) as dag:

    # Task 1: Get target quarter
    task_get_quarter = PythonOperator(
        task_id='get_target_quarter',
        python_callable=get_target_quarter,
        doc_md="""
        ### Get Target Quarter

        Calculates which quarter's financial statements to collect.
        Execution date - 45 days = target quarter.

        **Output**: Quarter info pushed to XCom
        """
    )

    # Task 2: Get stocks with corp_code
    task_get_stocks = PythonOperator(
        task_id='get_stocks_with_corp_code',
        python_callable=get_stocks_with_corp_code,
        doc_md="""
        ### Get Stocks with Corp Code

        Fetches stocks that have DART corp_code mapping.

        **Output**: Stock list with corp_code pushed to XCom
        """
    )

    # Task 3: Collect financial statements
    task_collect = PythonOperator(
        task_id='collect_financial_statements',
        python_callable=collect_financial_statements,
        doc_md="""
        ### Collect Financial Statements

        Collects quarterly financial statements from DART API.

        **Input**: Stock list and quarter info from XCom
        **Output**: Collection statistics pushed to XCom
        """
    )

    # Task 4: Calculate financial ratios
    task_calculate = PythonOperator(
        task_id='calculate_financial_ratios',
        python_callable=calculate_financial_ratios,
        doc_md="""
        ### Calculate Financial Ratios

        Calculates 33 financial ratios from collected statements.

        **Input**: Quarter info from XCom
        **Output**: Calculation statistics pushed to XCom
        """
    )

    # Task 5: Validate data quality
    task_validate = PythonOperator(
        task_id='validate_data_quality',
        python_callable=validate_data_quality,
        doc_md="""
        ### Validate Data Quality

        Validates collection and calculation quality:
        - Collection success rate >= 80%
        - Ratio calculation success rate >= 90%
        - At least 1000 statements collected

        **Raises**: Exception if validation fails
        """
    )

    # Task 6: Send completion report
    task_report = PythonOperator(
        task_id='send_completion_report',
        python_callable=send_completion_report,
        trigger_rule='all_done',
        doc_md="""
        ### Send Completion Report

        Generates completion report with all statistics.
        """
    )

    # Define task dependencies
    [task_get_quarter, task_get_stocks] >> task_collect >> task_calculate >> task_validate >> task_report


# DAG documentation
dag.doc_md = """
# Quarterly Financial Statement Collection DAG

## Overview
Automated quarterly collection of financial statements from DART (전자공시) and calculation of financial ratios.

## Schedule
- **Frequency**: Quarterly (4 times per year)
- **Dates**: February 15, May 15, August 15, November 15
- **Timing**: 45 days after each quarter end to allow for company filings
- **Duration**: ~1-2 hours for 2,500 stocks

## Quarter Calculation
- **Q1 (Jan-Mar)**: Collected on May 15 (45 days after Mar 31)
- **Q2 (Apr-Jun)**: Collected on Aug 15 (45 days after Jun 30)
- **Q3 (Jul-Sep)**: Collected on Nov 15 (45 days after Sep 30)
- **Q4 (Oct-Dec)**: Collected on Feb 15 (45 days after Dec 31)

## Tasks
1. **get_target_quarter**: Calculate which quarter to collect
2. **get_stocks_with_corp_code**: Get stocks with DART mapping
3. **collect_financial_statements**: Collect from DART API
4. **calculate_financial_ratios**: Calculate 33 ratios
5. **validate_data_quality**: Validate collection quality
6. **send_completion_report**: Generate report

## Data Collected
- **Balance Sheet**: Assets, liabilities, equity
- **Income Statement**: Revenue, expenses, profit
- **Cash Flow Statement**: Operating, investing, financing
- **Equity Changes**: Share capital, retained earnings

## Financial Ratios (33 total)
- **Profitability**: ROE, ROA, ROIC, margins
- **Growth**: Revenue growth, profit growth, EPS growth
- **Stability**: Debt ratios, liquidity ratios
- **Activity**: Turnover ratios
- **Market Value**: PER, PBR, PCR, PSR, etc.

## Data Source
- **API**: DART OpenAPI (https://opendart.fss.or.kr/)
- **Rate Limit**: ~5 requests/second recommended
- **Authentication**: DART_API_KEY required

## Error Handling
- Automatic retry: 3 attempts with 10-minute delay
- Email notification on failure
- Validation fails if success rate < 80%

## Manual Execution
```bash
airflow dags trigger quarterly_financial_statement
```

## Backfill
```bash
airflow dags backfill quarterly_financial_statement -s 2025-02-15 -e 2025-02-15
```
"""
