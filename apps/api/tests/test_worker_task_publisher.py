from __future__ import annotations

from ai_do_api.core.worker_task_publisher import create_fail_fast_celery_publisher


def test_fail_fast_celery_publisher_disables_publish_retries() -> None:
    client = create_fail_fast_celery_publisher(
        "ai_do_api_test",
        broker="memory://",
        ignore_result=True,
    )

    assert client.conf.broker_connection_retry is False
    assert client.conf.broker_connection_retry_on_startup is False
    assert client.conf.broker_connection_max_retries == 0
    assert client.conf.task_publish_retry is False
    assert client.conf.task_ignore_result is True
    assert client.conf.task_store_eager_result is False
    assert client.conf.broker_transport_options == {
        "socket_connect_timeout": 1,
        "socket_timeout": 1,
        "retry_on_timeout": False,
    }
