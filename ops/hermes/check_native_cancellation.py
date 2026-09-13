"""Verify the pinned Hermes admission contract in a disposable, offline container.

Run with the pinned image and readonly gateway entry mount as documented in

docs/domains/ai/hermes.md. This check uses the actual native HTTP handlers and
SQLite reservation store. Only model task scheduling is replaced; no provider,
profile volume, application database, Docker socket or credentials are used.
"""

import asyncio
import importlib.util
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from gateway.platforms import api_server, api_server_runs
from gateway.platforms.api_server_run_idempotency import RunIdempotencyStore

spec = importlib.util.spec_from_file_location("owh_review_entry", "/opt/owh_gateway_entry.py")
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


class Request(dict):
    method = "POST"
    path = "/v1/runs"

    def __init__(self, key, body):
        super().__init__()
        self.headers = {
            "Authorization": "Bearer synthetic-native-control-key",
            "Idempotency-Key": key,
            "X-Hermes-Session-Key": "synthetic-conversation",
        }
        self.body = body
        self.match_info = {}

    async def json(self):
        return self.body


async def check():
    with tempfile.TemporaryDirectory() as directory:
        adapter = api_server.APIServerAdapter.__new__(api_server.APIServerAdapter)
        adapter._api_key = "synthetic-native-control-key"
        adapter._expected_api_key = lambda: adapter._api_key
        adapter._request_audit_log_suffix = lambda request: "synthetic request"
        adapter._model_name = "synthetic"
        adapter._background_tasks = set()
        adapter._activate_admitted_request = lambda: None
        adapter._resolve_route = lambda model: None
        adapter._request_route_conflict_error = lambda **kwargs: None
        adapter._concurrency_limited_response = lambda: None
        api_server_runs._initialize_run_state(
            adapter, store_factory=lambda: RunIdempotencyStore(str(Path(directory) / "native.db"))
        )
        body = {
            "input": "synthetic",
            "session_id": "synthetic-session",
            "provider": "custom:synthetic",
            "model": "synthetic",
            "model_options": {},
        }
        profile_token = api_server._api_request_profile.set("owh-" + "a" * 32)
        try:
            request = Request("cancel-first", body)
            handler = next(
                row[2]
                for row in api_server_runs._http_routes(adapter)
                if row[1] == "/v1/owh/runs/cancel-admission"
            )
            denied = Request("denied", body)
            denied.headers.pop("Authorization")
            assert (await handler(denied)).status == 401
            cancelled = await handler(request)
            assert cancelled.status == 202
            result = json.loads(cancelled.body)
            assert result["status"] == "cancelled"
            # Invoke the actual pinned admission implementation. It must find
            # the cancellation using its own fingerprint and create no task.
            replay = await entry._original_handle_runs(adapter, request, _api_server=api_server)
            assert replay.status == 202, replay.body
            assert json.loads(replay.body)["run_id"] == result["run_id"]
            assert json.loads(replay.body)["status"] == "cancelled"
            assert not adapter._active_run_tasks
            request.match_info = {"run_id": result["run_id"]}
            status = await adapter._handle_get_run(request)
            assert status.status == 200
            assert json.loads(status.body)["status"] == "cancelled"

            changed = Request("cancel-first", {**body, "input": "different"})
            assert (await handler(changed)).status == 409

            # Native lookup misses before cancellation, then resumes its
            # original atomic reservation after cancellation has won.
            waiting, release = asyncio.Event(), asyncio.Event()

            async def history(session_id):
                waiting.set()
                await release.wait()
                return []

            adapter._conversation_history_for_session = history
            racing = Request("race", body)
            native_task = asyncio.create_task(
                entry._original_handle_runs(adapter, racing, _api_server=api_server)
            )
            await asyncio.wait_for(waiting.wait(), 2)
            raced_cancel = await handler(racing)
            assert raced_cancel.status == 202
            release.set()
            raced_native = await asyncio.wait_for(native_task, 2)
            assert raced_native.status == 202, raced_native.body
            assert json.loads(raced_native.body)["status"] == "cancelled"
            assert (
                json.loads(raced_native.body)["run_id"] == json.loads(raced_cancel.body)["run_id"]
            )
            assert not adapter._active_run_tasks

            accepted = Request("accepted-first", body)
            scheduled = []

            def suppress_model_task(coroutine):
                # Run native admission/reservation, but never execute its model
                # coroutine. Cancellation/replay must not schedule another one.
                coroutine.close()
                future = asyncio.get_running_loop().create_future()
                scheduled.append(future)
                return future

            with patch.object(api_server_runs.asyncio, "create_task", suppress_model_task):
                original = await entry._original_handle_runs(
                    adapter, accepted, _api_server=api_server
                )
                assert original.status == 202
                original_id = json.loads(original.body)["run_id"]
                assert len(scheduled) == 1
                recovered = await handler(accepted)
                assert json.loads(recovered.body) == {
                    "run_id": original_id,
                    "status": "queued",
                    "replayed": True,
                }
                assert len(scheduled) == 1
            adapter._active_run_tasks.pop(original_id).cancel()
            other_token = api_server._api_request_profile.set("owh-" + "b" * 32)
            try:
                other = await handler(accepted)
                assert json.loads(other.body)["status"] == "cancelled"
                assert json.loads(other.body)["run_id"] != original_id
            finally:
                api_server._api_request_profile.reset(other_token)
            # Reopen native durable storage, as after a gateway restart.
            adapter._run_idempotency_store.close()
            adapter._run_idempotency_store = RunIdempotencyStore(str(Path(directory) / "native.db"))
            reopened = await handler(request)
            assert json.loads(reopened.body)["run_id"] == result["run_id"]
            assert not adapter._active_run_tasks
            replay = await entry._original_handle_runs(adapter, request, _api_server=api_server)
            assert replay.status == 202
            assert json.loads(replay.body)["run_id"] == result["run_id"]
            status = await adapter._handle_get_run(request)
            assert status.status == 200 and json.loads(status.body)["status"] == "cancelled"
            print(
                "Pinned native cancellation: auth, profile isolation, exact replay, both native admission orderings, durable status and reopen passed; zero model calls."
            )
        finally:
            api_server._api_request_profile.reset(profile_token)
            adapter._run_idempotency_store.close()


asyncio.run(check())
