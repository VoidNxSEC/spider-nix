import pytest
import asyncio
from unittest.mock import MagicMock


def pytest_collection_modifyitems(items):
    """Let HTTPX-mocked discovery probes be intentionally partial."""
    marker = pytest.mark.httpx_mock(
        assert_all_responses_were_requested=False,
        assert_all_requests_were_expected=False,
    )
    for item in items:
        if "httpx_mock" in getattr(item, "fixturenames", ()):
            item.add_marker(marker)

@pytest.fixture
def mock_aioresponse():
    with pytest.raises(ImportError):
        import aioresponses
    # If we had aioresponses, we would use it here.
    # For now, we will rely on unittest.mock
    pass

@pytest.fixture
def mock_response():
    mock = MagicMock()
    mock.status_code = 200
    mock.text = "<html><body><a href='http://example.com/page2'>link</a></body></html>"
    mock.headers = {"Content-Type": "text/html"}
    return mock
