# tests/test_performance.py
import pytest
from unittest.mock import MagicMock, AsyncMock
from src.performance import ConnectionPool

@pytest.mark.asyncio
@pytest.fixture
async def connection_pool():
    pool = await ConnectionPool.get_instance()
    yield pool
    await ConnectionPool.close()

@pytest.mark.asyncio
async def test_connection_pool_singleton():
    # Test singleton pattern
    pool1 = await ConnectionPool.get_instance()
    pool2 = await ConnectionPool.get_instance()
    assert pool1 is pool2
    await ConnectionPool.close()

@pytest.mark.asyncio
async def test_get_request(connection_pool):
    # Setup mocks
    mock_response = MagicMock()
    mock_response.json = AsyncMock(return_value={"data": "test"})
    
    mock_get = MagicMock()
    mock_get.__aenter__ = AsyncMock(return_value=mock_response)
    
    connection_pool.session.get = MagicMock(return_value=mock_get)
    
    # Execute test
    result = await connection_pool.get("https://api.example.com/data")
    
    # Assertions
    assert result == {"data": "test"}
    connection_pool.session.get.assert_called_once_with("https://api.example.com/data")
    mock_response.json.assert_called_once()