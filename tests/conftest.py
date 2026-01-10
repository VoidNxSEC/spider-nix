import pytest
import asyncio
from unittest.mock import MagicMock

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
