"""
Pytest configuration and fixtures for Affinity SDK tests.
"""

import contextlib
from collections.abc import Iterator

# `tests/mcp/__init__.py` makes pytest register that directory as a top-level
# `mcp` package (no `tests/__init__.py` exists to anchor a `tests.mcp.*` path).
# That shadows the installed `mcp` Python package and breaks any test that
# eventually imports `affinity.mcp.server` (which does `from mcp.server import
# Server`). Eagerly importing the installed package here, before pytest
# collects any test module under `tests/mcp/`, caches the real module in
# `sys.modules` so subsequent resolution wins against the test-dir shadow.
with contextlib.suppress(ModuleNotFoundError):  # mcp is an optional extra
    import mcp.server  # noqa: F401

import pytest

try:
    import respx
except ModuleNotFoundError:  # pragma: no cover - optional test dependency
    respx = None  # type: ignore[assignment]

from affinity import Affinity


@pytest.fixture
def api_key() -> str:
    """Test API key."""
    return "test-api-key-12345"


@pytest.fixture
def mock_api() -> object:
    """
    Create a mock API router.

    Note: respx is an optional dev dependency; when it's missing we skip tests
    that require this fixture.
    """
    if respx is None:
        pytest.skip("respx is not installed")
    with respx.mock(assert_all_called=False) as router:  # type: ignore[attr-defined]
        yield router


@pytest.fixture
def client(api_key: str, mock_api: object) -> Iterator[Affinity]:
    """
    Create a test client with mocked HTTP.

    IMPORTANT: This fixture yields and closes the client to prevent httpx
    connection pools from lingering and causing gc.collect() hangs during
    pytest cleanup.
    """
    _ = mock_api
    c = Affinity(
        api_key=api_key,
        enable_cache=False,
        max_retries=0,
    )
    yield c
    c.close()


# Common mock responses
@pytest.fixture
def whoami_response() -> dict:
    """Mock /auth/whoami response."""
    return {
        "tenant": {
            "id": 1,
            "name": "Test Company",
            "subdomain": "test",
        },
        "user": {
            "id": 100,
            "firstName": "Test",
            "lastName": "User",
            "emailAddress": "test@example.com",
        },
        "grant": {
            "type": "api_key",
            "scopes": ["all"],
            "createdAt": "2024-01-01T00:00:00Z",
        },
    }


@pytest.fixture
def company_response() -> dict:
    """Mock single company response."""
    return {
        "id": 123,
        "name": "Acme Corp",
        "domain": "acme.com",
        "domains": ["acme.com"],
        "personIds": [1, 2, 3],
        "fields": {},
    }


@pytest.fixture
def companies_list_response() -> dict:
    """Mock companies list response."""
    return {
        "data": [
            {
                "id": 123,
                "name": "Acme Corp",
                "domain": "acme.com",
                "domains": ["acme.com"],
                "personIds": [],
                "fields": {},
            },
            {
                "id": 456,
                "name": "Beta Inc",
                "domain": "beta.io",
                "domains": ["beta.io"],
                "personIds": [],
                "fields": {},
            },
        ],
        "pagination": {
            "nextPageUrl": None,
            "prevPageUrl": None,
        },
    }


@pytest.fixture
def person_response() -> dict:
    """Mock single person response."""
    return {
        "id": 100,
        "firstName": "John",
        "lastName": "Doe",
        "primaryEmailAddress": "john@example.com",
        "emails": ["john@example.com"],
        "type": "external",
        "organizationIds": [123],
        "fields": {},
    }


@pytest.fixture
def list_response() -> dict:
    """Mock single list response."""
    return {
        "id": 789,
        "name": "Deal Pipeline",
        "type": 8,  # OPPORTUNITY
        "public": True,
        "ownerId": 100,
        "creatorId": 100,
        "listSize": 50,
        "fields": [],
    }


@pytest.fixture
def lists_response() -> dict:
    """Mock lists list response."""
    return {
        "data": [
            {
                "id": 789,
                "name": "Deal Pipeline",
                "type": 8,
                "public": True,
                "ownerId": 100,
                "creatorId": 100,
                "listSize": 50,
            },
            {
                "id": 790,
                "name": "Contacts",
                "type": 0,
                "public": True,
                "ownerId": 100,
                "creatorId": 100,
                "listSize": 100,
            },
        ],
        "pagination": {
            "nextPageUrl": None,
            "prevPageUrl": None,
        },
    }
