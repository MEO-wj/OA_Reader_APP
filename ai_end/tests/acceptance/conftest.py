# tests/acceptance/conftest.py
import pytest
import asyncio


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_runner():
    """测试运行器 fixture"""
    from tests.acceptance.test_acceptance import AcceptanceTestRunner
    runner = AcceptanceTestRunner()
    yield runner
    # 清理工作（如需要）
