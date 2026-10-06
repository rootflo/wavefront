"""Celery app wiring for the async executor worker."""

import celery_worker.tasks.agent_task  # noqa: F401 — register tasks
import celery_worker.tasks.workflow_task  # noqa: F401

from celery_worker import settings
from celery_worker.celery_app import app
from celery_worker.signals import teardown_event_loop, teardown_telemetry


def test_app_includes_agent_and_workflow_tasks_only():
    assert 'celery_worker.tasks.agent_task' in app.conf.include
    assert 'celery_worker.tasks.workflow_task' in app.conf.include
    assert 'celery_worker.tasks.trigger_event_task' not in app.conf.include


def test_app_uses_json_serialization():
    assert app.conf.task_serializer == 'json'
    assert app.conf.result_serializer == 'json'
    assert 'json' in app.conf.accept_content


def test_registered_task_names():
    assert 'celery_worker.tasks.agent_task.execute_agent_task' in app.tasks
    assert 'celery_worker.tasks.workflow_task.execute_workflow_task' in app.tasks


def test_tasks_use_settings_retry_policy():
    agent = app.tasks['celery_worker.tasks.agent_task.execute_agent_task']
    workflow = app.tasks['celery_worker.tasks.workflow_task.execute_workflow_task']
    assert agent.max_retries == settings.MAX_RETRIES
    assert workflow.max_retries == settings.MAX_RETRIES
    assert agent.default_retry_delay == settings.RETRY_DELAY
    assert workflow.default_retry_delay == settings.RETRY_DELAY


def test_app_broker_matches_settings():
    assert app.conf.broker_url == settings.CELERY_BROKER_URL
    assert app.conf.result_backend == settings.CELERY_RESULT_BACKEND


def test_teardown_helpers_are_callable():
    # Idempotent / safe when telemetry + loop were never started.
    teardown_event_loop()
    teardown_telemetry()


def test_main_module_imports_app():
    import celery_worker.main as main

    assert main.app is app
