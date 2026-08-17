import asyncio

import pytest
import pytest_asyncio
from aiohttp import web

from async_github import (
    GitHubAPI,
    NotFoundError,
    ServerError,
    limits,
)


@pytest_asyncio.fixture
async def api_server(unused_tcp_port):
    calls = {"repos": 0, "server": 0}

    async def user(request):
        return web.json_response(
            {"login": request.match_info["username"], "id": 1},
            headers={
                "X-RateLimit-Limit": "5000",
                "X-RateLimit-Remaining": "4999",
                "X-RateLimit-Reset": "1234567890",
            },
        )

    async def repos(request):
        calls["repos"] += 1
        page = int(request.query.get("page", "1"))
        data = [{"name": "one"}, {"name": "two"}] if page == 1 else [{"name": "three"}]
        return web.json_response(data)

    async def missing(request):
        return web.json_response({"message": "Not Found"}, status=404)

    async def transient(request):
        calls["server"] += 1
        if calls["server"] == 1:
            return web.json_response({"message": "temporary"}, status=503)
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_get("/users/{username}", user)
    app.router.add_get("/repos/{owner}/{repo}/issues", repos)
    app.router.add_get("/missing", missing)
    app.router.add_get("/transient", transient)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", unused_tcp_port)
    await site.start()

    api = GitHubAPI("test-token", max_retries=2)
    api.BASE_URL = "http://127.0.0.1:%d" % unused_tcp_port

    try:
        yield api, calls
    finally:
        await api.close()
        await runner.cleanup()


@pytest.mark.asyncio
async def test_get_user_and_rate_headers(api_server):
    api, _ = api_server
    result = await api.get_user("octocat")
    assert result["login"] == "octocat"
    assert api.rate_limit.remaining == 4999
    assert api.rate_limit.limit == 5000


@pytest.mark.asyncio
async def test_pagination(api_server):
    api, calls = api_server
    items = []
    async for item in api.get_issues("owner", "repo", page_size=2):
        items.append(item["name"])

    assert items == ["one", "two", "three"]
    assert calls["repos"] == 2


@pytest.mark.asyncio
async def test_not_found_error(api_server):
    api, _ = api_server
    with pytest.raises(NotFoundError):
        await api._request("GET", "missing")


@pytest.mark.asyncio
async def test_transient_server_retry(api_server):
    api, calls = api_server
    result = await api._request("GET", "transient")

    assert result["ok"] is True
    assert calls["server"] == 2


@pytest.mark.asyncio
async def test_rate_limit_decorator():
    calls = []

    @limits(calls=2, period=0.05)
    async def work():
        calls.append(True)

    await asyncio.gather(work(), work(), work())
    assert len(calls) == 3


def test_package_exports():
    from async_github import GitHubAPI, RateLimitError, ServerError
    assert GitHubAPI is not None
    assert RateLimitError is not None
    assert ServerError is not None
