"""Async GitHub API client."""

import asyncio
import json
import time
from dataclasses import dataclass
from functools import wraps
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, Optional, Tuple, TypeVar

import aiohttp


class APIError(Exception):
    """Base exception for GitHub API errors."""


class BadRequestError(APIError):
    """Raised for HTTP 400 responses."""


class UnauthorizedError(APIError):
    """Raised for HTTP 401 responses."""


class ForbiddenError(APIError):
    """Raised for HTTP 403 responses."""


class NotFoundError(APIError):
    """Raised for HTTP 404 responses."""


class RateLimitError(APIError):
    """Raised when GitHub rate limiting prevents the request."""


class ServerError(APIError):
    """Raised for transient GitHub server errors."""


class RequestError(APIError):
    """Raised for network/request failures."""


@dataclass
class RateLimit:
    """Current GitHub rate-limit state."""

    remaining: int = 5000
    reset: float = 0.0
    limit: int = 5000


F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


class AsyncRateLimiter:
    """Simple in-memory token-bucket-style limiter for async calls.

    The limiter is process-local. It is intentionally small and dependency-free;
    applications needing a distributed limiter can replace the store with Redis.
    """

    def __init__(self, calls: int, period: float) -> None:
        if calls <= 0 or period <= 0:
            raise ValueError("calls and period must be positive")
        self.calls = calls
        self.period = period
        self._timestamps = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                cutoff = now - self.period
                self._timestamps = [t for t in self._timestamps if t > cutoff]

                if len(self._timestamps) < self.calls:
                    self._timestamps.append(now)
                    return

                wait_for = self.period - (now - self._timestamps[0])

            await asyncio.sleep(max(wait_for, 0.01))


def limits(calls: int, period: float) -> Callable[[F], F]:
    """Decorate an async method with a process-local rate limiter."""

    limiter = AsyncRateLimiter(calls, period)

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            await limiter.acquire()
            return await func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


class Paginator:
    """Async iterator that yields one item at a time from page-based endpoints."""

    def __init__(
        self,
        api: "GitHubAPI",
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        page_size: int = 100,
    ) -> None:
        if page_size < 1 or page_size > 100:
            raise ValueError("page_size must be between 1 and 100")
        self.api = api
        self.endpoint = endpoint
        self.params = dict(params or {})
        self.page_size = page_size
        self.page = 1
        self._buffer = []
        self._finished = False

    def __aiter__(self) -> "Paginator":
        return self

    async def __anext__(self) -> Dict[str, Any]:
        while not self._buffer and not self._finished:
            params = dict(self.params)
            params.update({"page": self.page, "per_page": self.page_size})
            data = await self.api._request("GET", self.endpoint, params=params)

            if not isinstance(data, list):
                raise APIError(
                    "Pagination expected a JSON list from %s, received %s"
                    % (self.endpoint, type(data).__name__)
                )

            self.page += 1
            self._buffer.extend(data)

            if len(data) < self.page_size:
                self._finished = True

        if not self._buffer:
            raise StopAsyncIteration

        return self._buffer.pop(0)


class GitHubAPI:
    """Async, typed wrapper around selected GitHub REST API resources.

    Example:
        async with GitHubAPI("ghp_token") as api:
            user = await api.get_user("octocat")
            async for repo in api.get_repos("octocat"):
                print(repo["name"])
    """

    BASE_URL = "https://api.github.com"

    def __init__(
        self,
        token: str,
        *,
        timeout: float = 20.0,
        max_retries: int = 3,
        user_agent: str = "async-github/0.1.0",
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        if not token:
            raise ValueError("A GitHub token is required")

        self.token = token
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.user_agent = user_agent
        self._session = session
        self._owns_session = session is None
        self.rate_limit = RateLimit()

    async def __aenter__(self) -> "GitHubAPI":
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=self.timeout,
                headers={
                    "Authorization": "Bearer %s" % self.token,
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": self.user_agent,
                },
            )
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        if self._session is not None and not self._session.closed and self._owns_session:
            await self._session.close()

    @staticmethod
    def _retry_delay(response: Any, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(float(retry_after), 0.0)
            except ValueError:
                pass
        return min(2 ** attempt, 30)

    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any
    ) -> Any:
        session = await self._ensure_session()
        url = endpoint if endpoint.startswith("http") else self.BASE_URL + "/" + endpoint.lstrip("/")

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                async with session.request(method, url, **kwargs) as response:
                    self._update_rate_limit(response)

                    if response.status == 429:
                        delay = self._retry_delay(response, attempt)
                        if attempt < self.max_retries:
                            await asyncio.sleep(delay)
                            continue
                        raise RateLimitError(
                            "GitHub rate limit exceeded for %s; retry after %.1f seconds"
                            % (url, delay)
                        )

                    if response.status in (502, 503):
                        if attempt < self.max_retries:
                            await asyncio.sleep(self._retry_delay(response, attempt))
                            continue
                        raise ServerError(
                            "GitHub returned HTTP %s after %d retries for %s"
                            % (response.status, self.max_retries, url)
                        )

                    if response.status == 400:
                        raise BadRequestError(await self._error_message(response, url))
                    if response.status == 401:
                        raise UnauthorizedError(await self._error_message(response, url))
                    if response.status == 403:
                        raise ForbiddenError(await self._error_message(response, url))
                    if response.status == 404:
                        raise NotFoundError(await self._error_message(response, url))
                    if response.status >= 500:
                        raise ServerError(await self._error_message(response, url))
                    if response.status >= 400:
                        raise APIError(await self._error_message(response, url))

                    try:
                        return await response.json()
                    except (aiohttp.ContentTypeError, json.JSONDecodeError) as exc:
                        raise APIError("GitHub returned invalid JSON for %s" % url) from exc

            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(min(2 ** attempt, 30))
                    continue
                raise RequestError(
                    "Network failure calling %s after %d retries: %s"
                    % (url, self.max_retries, exc)
                ) from exc

        raise RequestError("Request failed: %s" % last_error)

    @staticmethod
    async def _error_message(response: Any, url: str) -> str:
        try:
            payload = await response.json()
            message = payload.get("message", "No API message")
        except Exception:
            message = await response.text()
        return "GitHub HTTP %s for %s: %s" % (response.status, url, message)

    def _update_rate_limit(self, response: Any) -> None:
        headers = response.headers
        self.rate_limit = RateLimit(
            remaining=int(headers.get("X-RateLimit-Remaining", self.rate_limit.remaining)),
            reset=float(headers.get("X-RateLimit-Reset", self.rate_limit.reset)),
            limit=int(headers.get("X-RateLimit-Limit", self.rate_limit.limit)),
        )

    async def get_user(self, username: str) -> Dict[str, Any]:
        """Fetch a GitHub user profile."""
        if not username.strip():
            raise ValueError("username must not be empty")
        return await self._request("GET", "users/%s" % username.strip())

    def get_repos(
        self,
        username: str,
        *,
        page_size: int = 100,
        **params: Any
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Return an async generator streaming a user's repositories."""
        if not username.strip():
            raise ValueError("username must not be empty")
        return self._paginate(
            "users/%s/repos" % username.strip(),
            params=params,
            page_size=page_size,
        )

    def get_issues(
        self,
        owner: str,
        repo: str,
        *,
        page_size: int = 100,
        **params: Any
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Return an async generator streaming repository issues."""
        if not owner.strip() or not repo.strip():
            raise ValueError("owner and repo must not be empty")
        return self._paginate(
            "repos/%s/%s/issues" % (owner.strip(), repo.strip()),
            params=params,
            page_size=page_size,
        )

    async def _paginate(
        self,
        endpoint: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        page_size: int = 100,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        paginator = Paginator(self, endpoint, params=params, page_size=page_size)
        async for item in paginator:
            yield item

    async def get_repo(self, owner: str, repo: str) -> Dict[str, Any]:
        """Fetch a single repository."""
        if not owner.strip() or not repo.strip():
            raise ValueError("owner and repo must not be empty")
        return await self._request(
            "GET", "repos/%s/%s" % (owner.strip(), repo.strip())
        )


__all__ = [
    "APIError",
    "BadRequestError",
    "UnauthorizedError",
    "ForbiddenError",
    "NotFoundError",
    "RateLimitError",
    "ServerError",
    "RequestError",
    "RateLimit",
    "limits",
    "Paginator",
    "GitHubAPI",
]
