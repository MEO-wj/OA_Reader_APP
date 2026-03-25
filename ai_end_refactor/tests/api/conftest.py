"""API 测试配置"""
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.fixture
async def client():
    """FastAPI 测试客户端"""
    from src.api.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac
