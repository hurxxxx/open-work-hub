from __future__ import annotations

from uuid import uuid4

import pytest

from open_work_hub_api.core.worker_task_publisher import create_fail_fast_celery_publisher


def test_fail_fast_celery_publisher_disables_publish_retries() -> None:
    client = create_fail_fast_celery_publisher(
        "open_work_hub_api_test",
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
    client.close()


@pytest.mark.parametrize(
    "transport",
    ["memory", pytest.param("redis", marks=pytest.mark.external_integration("redis"))],
)
def test_publisher_delivers_serialized_task_to_the_requested_queue(request, transport):
    broker = "memory://" if transport == "memory" else request.getfixturevalue("redis_url")
    queue_name = f"open-work-hub-api-test-publisher-{uuid4().hex}"
    job_id = str(uuid4())
    publisher = create_fail_fast_celery_publisher(
        "test_delivery", broker=broker, ignore_result=True
    )
    try:
        with publisher.connection_for_write() as connection:
            with connection.SimpleQueue(queue_name) as queue:
                try:
                    publisher.signature("test.dispatch", args=[job_id], immutable=True).apply_async(
                        queue=queue_name, retry=False
                    )
                    message = queue.get(block=True, timeout=3)
                    try:
                        assert message.headers["task"] == "test.dispatch"
                        assert message.content_type == "application/json"
                        assert message.payload[:2] == [[job_id], {}]
                    finally:
                        message.ack()
                finally:
                    # Delete only this test's queue/binding using the transport API.
                    queue.queue.delete()
    finally:
        publisher.close()


def test_search_outbox_publishes_the_registered_task_and_job_id():
    from open_work_hub_api.domains.search import outbox

    publisher = outbox.get_celery_client()
    job_id = str(uuid4())
    outbox._publish_job(job_id=job_id)
    with publisher.connection_for_read() as connection:
        with connection.SimpleQueue(outbox.SEARCH_INDEX_REALTIME_QUEUE) as queue:
            message = queue.get(block=True, timeout=3)
            try:
                assert message.headers["task"] == outbox.SEARCH_INDEX_RESOURCE_TASK_NAME
                assert message.payload[:2] == [[job_id], {}]
            finally:
                message.ack()
