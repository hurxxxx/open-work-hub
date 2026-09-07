from __future__ import annotations

import subprocess
import sys
import textwrap


def test_result_finalizer_can_unsubscribe_during_pubsub_command() -> None:
    # Run in a child: redis-py 5.3.1 deadlocks here and cannot be interrupted
    # inside the Python thread. No Redis server or application data is used.
    code = textwrap.dedent("""
        import gc
        from unittest.mock import Mock
        from celery import Celery
        from celery.result import AsyncResult
        from redis.backoff import NoBackoff
        from redis.retry import Retry

        app = Celery('reentrancy', backend='redis://localhost:1/0')
        backend = app.backend
        pubsub = backend.client.pubsub(ignore_subscribe_messages=True)
        connection = Mock()
        connection.retry = Retry(NoBackoff(), 0)
        pubsub.connection = connection
        pubsub.subscribed_event.set()
        backend.result_consumer._pubsub = pubsub

        gc.disable()
        result = AsyncResult('expired-result', backend=backend)
        result.parent = result
        del result

        def send_command(command, *args, **kwargs):
            if command == 'SUBSCRIBE':
                gc.collect()

        connection.send_command.side_effect = send_command
        pubsub.subscribe('new-result')
        commands = [call.args[0] for call in connection.send_command.call_args_list]
        assert commands == ['SUBSCRIBE', 'UNSUBSCRIBE'], commands
        pubsub.close()
        app.close()
    """)
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=5,
    )
    assert result.returncode == 0, result.stderr
