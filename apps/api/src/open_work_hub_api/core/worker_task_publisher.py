from __future__ import annotations

from celery import Celery


def create_fail_fast_celery_publisher(
    app_name: str,
    *,
    broker: str,
    backend: str | None = None,
    ignore_result: bool = False,
) -> Celery:
    celery_client = Celery(app_name, broker=broker, backend=backend)
    celery_client.conf.update(
        broker_connection_retry=False,
        broker_connection_retry_on_startup=False,
        broker_connection_max_retries=0,
        task_publish_retry=False,
        broker_transport_options={
            "socket_connect_timeout": 1,
            "socket_timeout": 1,
            "retry_on_timeout": False,
        },
    )
    if ignore_result:
        celery_client.conf.update(
            result_backend=None,
            task_ignore_result=True,
            task_store_eager_result=False,
        )
    return celery_client
