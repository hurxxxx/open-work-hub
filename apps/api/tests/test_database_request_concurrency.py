from __future__ import annotations

import asyncio
from collections import Counter

import anyio
import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from dev_accounts import auth_headers, dev_login
from open_work_hub_api.core import db
from open_work_hub_api.domains.auth import dependencies


@pytest.mark.parametrize("invalid_credentials", [False, True])
def test_authenticated_read_burst_does_not_starve_request_threads(
    client, monkeypatch, invalid_credentials
):
    from open_work_hub_api.app import create_app

    headers = auth_headers(dev_login(client)["token"])
    engine = create_engine(db.get_engine().url, pool_size=2, max_overflow=0, pool_timeout=0.5)
    factory = sessionmaker(engine)
    settings = dependencies.get_settings().model_copy(
        update={"db_pool_size": 2, "db_max_overflow": 0}
    )
    monkeypatch.setattr(db, "get_session_factory", lambda: factory)
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
    app = create_app(initialize_runtime=False)

    async def burst():
        anyio.to_thread.current_default_thread_limiter().total_tokens = 4
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
            headers=headers,
        ) as transport:

            async def read(index):
                if invalid_credentials and index % 2:
                    return await transport.get(
                        "/api/v1/agent/runs", headers={"Authorization": "Bearer invalid-test-token"}
                    )
                return await transport.get("/api/v1/agent/runs")

            return await asyncio.gather(*(read(index) for index in range(16)))

    try:
        responses = asyncio.run(burst())
        expected = {200: 8, 401: 8} if invalid_credentials else {200: 16}
        assert Counter(response.status_code for response in responses) == expected
        assert engine.pool.checkedout() == 0
    finally:
        engine.dispose()
