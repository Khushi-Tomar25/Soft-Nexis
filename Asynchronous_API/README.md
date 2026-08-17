# async-github

A production-oriented asynchronous Python wrapper for selected GitHub REST API resources using `aiohttp`.

## Features

- `GitHubAPI` class with async methods
- `aiohttp.ClientSession` for connection pooling
- User and repository endpoints
- Async-generator pagination
- Configurable page size up to GitHub's 100-item page limit
- In-memory decorator-based async rate limiter
- GitHub `X-RateLimit-*` header tracking
- `429` / `Retry-After` handling
- Automatic retries for transient `502` and `503` errors
- Custom exception hierarchy
- Type hints and docstrings
- Async context manager support
- setuptools/PyPI-ready package structure
- Unit tests with mocked HTTP responses

## Installation

```bash
python -m pip install -r requirements.txt
```

For package installation:

```bash
python -m pip install .
```

## Quick start

```python
import asyncio
from async_github import GitHubAPI

async def main():
    async with GitHubAPI("YOUR_GITHUB_TOKEN") as api:
        user = await api.get_user("torvalds")
        print(user["login"])

        async for repo in api.get_repos("torvalds", page_size=50):
            print(repo["name"])

asyncio.run(main())
```

Use a token with the minimum permissions needed for the endpoints you call. Do not commit real tokens to source control.

## Supported resources

### Users

```python
user = await api.get_user("octocat")
```

### Repositories

```python
repo = await api.get_repo("octocat", "Hello-World")

async for repo in api.get_repos("octocat"):
    print(repo["name"])
```

### Issues

```python
async for issue in api.get_issues("octocat", "Hello-World"):
    print(issue["title"])
```

## Pagination

`get_repos()` and `get_issues()` return async generators. Pages are requested only as the caller consumes items.

```python
async for item in api.get_repos("octocat", page_size=25):
    print(item["name"])
```

The library stops when a page contains fewer records than the configured page size.

## Rate limiting

The client tracks:

- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`

The module also provides a reusable async decorator:

```python
from async_github import limits

@limits(calls=10, period=1)
async def my_call():
    ...
```

The built-in limiter is process-local and suitable for a single application process. A distributed deployment can replace the limiter store with Redis without changing the public API design.

For server-side rate limits, HTTP `429` responses honor `Retry-After` when supplied. If retries are exhausted, `RateLimitError` is raised with contextual information.

## Error handling

The following exceptions are exposed:

```text
APIError
├── BadRequestError       (400)
├── UnauthorizedError     (401)
├── ForbiddenError        (403)
├── NotFoundError         (404)
├── RateLimitError        (429)
├── ServerError           (5xx / transient failures)
└── RequestError          (network/timeout failures)
```

`502` and `503` responses are retried automatically with exponential backoff.

## Testing

Run:

```bash
pytest -q
```

The test suite uses mocked responses and does not require a GitHub token or network access.

## Packaging

The project contains both `setup.py` and `pyproject.toml`.

Build artifacts with:

```bash
python -m pip install build
python -m build
```

The generated `dist/` directory can be used for a PyPI upload after replacing the placeholder project URL/author metadata with your own information.

## Security

- Tokens are accepted at runtime and are never stored by the library.
- Never hard-code or commit a GitHub token.
- Add `.env` or local credential files to `.gitignore` if you use them.
