"""
Notification Callbacks for Airflow DAGs

Provides callbacks for email and Slack notifications on task failure/success.

Author: Stock Portfolio System
Created: 2025-10-25
"""

from typing import Dict, Any
import logging
from datetime import datetime

from airflow.models import TaskInstance
from loguru import logger


def task_failure_callback(context: Dict[str, Any]) -> None:
    """
    Callback function executed when a task fails.

    Args:
        context: Airflow context dict containing task instance, DAG, etc.
    """
    task_instance: TaskInstance = context['task_instance']
    dag_id = context['dag'].dag_id
    task_id = task_instance.task_id
    execution_date = context['execution_date']
    exception = context.get('exception')

    error_message = f"""
    ❌ AIRFLOW TASK FAILURE ❌
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    DAG:             {dag_id}
    Task:            {task_id}
    Execution Date:  {execution_date}
    Run ID:          {context.get('run_id', 'N/A')}
    Try Number:      {task_instance.try_number}
    Max Tries:       {task_instance.max_tries}

    Exception:
    {str(exception) if exception else 'No exception info available'}

    Log URL: {task_instance.log_url}
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """

    logger.error(error_message)

    # TODO: Send to Slack if configured
    # _send_slack_notification(error_message, is_error=True)


def task_success_callback(context: Dict[str, Any]) -> None:
    """
    Callback function executed when a task succeeds.

    Args:
        context: Airflow context dict containing task instance, DAG, etc.
    """
    task_instance: TaskInstance = context['task_instance']
    dag_id = context['dag'].dag_id
    task_id = task_instance.task_id
    execution_date = context['execution_date']

    # Get collection stats if available
    stats = task_instance.xcom_pull(task_ids='collect_daily_prices', key='collection_stats')

    success_message = f"""
    ✅ AIRFLOW TASK SUCCESS ✅
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    DAG:             {dag_id}
    Task:            {task_id}
    Execution Date:  {execution_date}
    Run ID:          {context.get('run_id', 'N/A')}
    Duration:        {task_instance.duration}s
    """

    if stats:
        success_message += f"""
    📊 Collection Statistics:
    - Total:    {stats.get('total', 'N/A')}
    - Success:  {stats.get('success', 'N/A')}
    - Failed:   {stats.get('failed', 'N/A')}
    - Skipped:  {stats.get('skipped', 'N/A')}
    """

    success_message += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    logger.info(success_message)

    # TODO: Send to Slack if configured
    # _send_slack_notification(success_message, is_error=False)


def dag_failure_callback(context: Dict[str, Any]) -> None:
    """
    Callback function executed when entire DAG fails.

    Args:
        context: Airflow context dict containing task instance, DAG, etc.
    """
    dag_id = context['dag'].dag_id
    execution_date = context['execution_date']
    run_id = context.get('run_id', 'N/A')

    error_message = f"""
    🚨 AIRFLOW DAG FAILURE 🚨
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    DAG:             {dag_id}
    Execution Date:  {execution_date}
    Run ID:          {run_id}

    The DAG has failed. Please check the Airflow UI for details.
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """

    logger.error(error_message)

    # TODO: Send to Slack if configured
    # _send_slack_notification(error_message, is_error=True)


def dag_success_callback(context: Dict[str, Any]) -> None:
    """
    Callback function executed when entire DAG succeeds.

    Args:
        context: Airflow context dict containing task instance, DAG, etc.
    """
    dag_id = context['dag'].dag_id
    execution_date = context['execution_date']
    run_id = context.get('run_id', 'N/A')

    # Try to get completion report from XCom
    task_instance = context.get('task_instance')
    report = None
    if task_instance:
        try:
            report = task_instance.xcom_pull(
                task_ids='send_completion_report',
                key='completion_report'
            )
        except Exception:
            pass

    success_message = f"""
    ✅ AIRFLOW DAG SUCCESS ✅
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    DAG:             {dag_id}
    Execution Date:  {execution_date}
    Run ID:          {run_id}
    Completed At:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """

    if report:
        success_message += f"\n{report}"

    success_message += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    logger.info(success_message)

    # TODO: Send to Slack if configured
    # _send_slack_notification(success_message, is_error=False)


def _send_slack_notification(message: str, is_error: bool = False) -> None:
    """
    Send notification to Slack (to be implemented).

    Args:
        message: Message to send
        is_error: Whether this is an error notification
    """
    # TODO: Implement Slack webhook integration
    # Example:
    # import requests
    # webhook_url = Variable.get("slack_webhook_url", default_var=None)
    # if webhook_url:
    #     payload = {
    #         "text": message,
    #         "icon_emoji": ":x:" if is_error else ":white_check_mark:",
    #         "username": "Airflow Bot"
    #     }
    #     requests.post(webhook_url, json=payload)
    pass


def _send_email_notification(
    to: str,
    subject: str,
    message: str
) -> None:
    """
    Send email notification (to be implemented).

    Args:
        to: Recipient email address
        subject: Email subject
        message: Email body
    """
    # TODO: Implement email sending
    # Airflow has built-in email support via EmailOperator
    # or you can use SMTP configuration
    pass
