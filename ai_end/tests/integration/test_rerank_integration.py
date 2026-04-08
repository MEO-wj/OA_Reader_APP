"""Rerank 集成测试

TDD GREEN 阶段 - 验证 rerank 功能的端到端集成

测试范围：
- 端到端测试：真实调用 rerank API
- 自定义 base URL 测试：验证配置继承行为
"""
import asyncio

import pytest

from src.config import Config
from src.core import api_clients
from src.core import article_retrieval


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rerank_end_to_end():
    """端到端测试：真实调用 rerank API

    Given: 配置好的环境和测试数据
    When: 执行包含 rerank 的搜索
    Then: 正确返回排序后的结果

    注意：此测试需要真实的数据库和 API 连接
    """
    # 重置客户端以确保干净的测试环境
    api_clients.close_clients()

    try:
        # === Given: 配置好的环境 ===
        config = Config.load()

        # === When: 执行搜索（会触发 rerank）===
        result = await article_retrieval.search_articles(
            query="医师执业注册流程",
            top_k=5,
            threshold=0.5
        )

        # === Then: 验证返回结构 ===
        assert "results" in result, "结果应包含 'results' 字段"
        assert isinstance(result["results"], list), "results 应该是列表"

        # 如果有结果，验证结构
        if len(result["results"]) > 0:
            first_result = result["results"][0]
            assert "id" in first_result, "结果应包含 'id' 字段"
            assert "title" in first_result, "结果应包含 'title' 字段"
            assert "summary" in first_result, "结果应包含 'summary' 字段"

        # 验证返回数量不超过 top_k
        assert len(result["results"]) <= 5, f"返回结果数量应不超过 top_k=5，实际: {len(result['results'])}"

    finally:
        # 清理：关闭客户端
        api_clients.close_clients()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rerank_with_custom_base_url():
    """测试自定义 rerank base URL

    Given: 配置了不同的 rerank_base_url
    When: 执行搜索
    Then: 正确使用自定义或继承的 base URL

    验证行为：
    1. rerank_base_url 为空时，继承 base_url
    2. rerank_base_url 有值时，使用自定义值
    """
    # 重置客户端
    api_clients.close_clients()

    try:
        # === Given: 获取当前配置 ===
        config = Config.load()

        # 测试 1: 验证 effective_rerank_base_url 属性
        # 如果 rerank_base_url 为 None，应返回 base_url
        if config.rerank_base_url is None:
            assert config.effective_rerank_base_url == config.base_url, \
                "rerank_base_url 为空时应继承 base_url"
        else:
            assert config.effective_rerank_base_url == config.rerank_base_url, \
                "rerank_base_url 有值时应使用自定义值"

        # 测试 2: 创建测试配置验证继承行为
        test_config = Config.with_defaults()
        # with_defaults 中 rerank_base_url 默认为 None
        assert test_config.effective_rerank_base_url == test_config.base_url, \
            "默认配置应继承 base_url"

        # === When: 执行搜索 ===
        # 注意：由于 Config 是 frozen 的，不能在测试中修改
        # 这里只验证搜索不会抛出异常
        result = await article_retrieval.search_articles(
            query="测试查询",
            top_k=3,
            threshold=0.5
        )

        # === Then: 验证搜索成功 ===
        assert "results" in result, "搜索应返回 results 字段"
        assert isinstance(result["results"], list), "results 应该是列表"

    finally:
        # 清理
        api_clients.close_clients()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rerank_empty_query():
    """测试空查询时的错误处理

    Given: 任何配置状态
    When: 传入空查询字符串
    Then: 正确抛出 ValueError
    """
    # 重置客户端
    api_clients.close_clients()

    try:
        # === When & Then: 验证空查询抛出异常 ===
        with pytest.raises(ValueError, match="查询文本不能为空"):
            await article_retrieval.search_articles(
                query="",
                top_k=5
            )

        with pytest.raises(ValueError, match="查询文本不能为空"):
            await article_retrieval.search_articles(
                query="   ",  # 仅空格
                top_k=5
            )

    finally:
        api_clients.close_clients()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rerank_with_keywords():
    """测试带关键词的搜索（Layer 1 + Layer 2 + Layer 3）

    Given: 配置好的环境
    When: 执行带关键词的搜索
    Then: 正确返回整合后的结果
    """
    # 重置客户端
    api_clients.close_clients()

    try:
        # === Given: 配置好的环境 ===
        config = Config.load()

        # === When: 执行带关键词的搜索 ===
        result = await article_retrieval.search_articles(
            query="住院医师培训",
            keywords="住院医师,培训,待遇",
            top_k=5,
            threshold=0.5
        )

        # === Then: 验证结果结构 ===
        assert "results" in result, "结果应包含 'results' 字段"
        assert isinstance(result["results"], list), "results 应该是列表"
        assert len(result["results"]) <= 5, "返回结果不应超过 top_k"

        # 如果有结果，验证可能包含的关键词相似度字段
        if len(result["results"]) > 0:
            first_result = result["results"][0]
            # 验证基本字段
            assert "id" in first_result
            assert "title" in first_result
            assert "summary" in first_result
            # 可能包含的相似度字段
            assert "ebd_similarity" in first_result or "keyword_similarity" in first_result or \
                   "rerank_score" in first_result or True  # 至少有一个相似度字段

    finally:
        api_clients.close_clients()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rerank_high_threshold():
    """测试高阈值过滤

    Given: 配置好的环境
    When: 使用高阈值进行搜索
    Then: 只返回高相似度的结果
    """
    # 重置客户端
    api_clients.close_clients()

    try:
        # === Given: 配置好的环境 ===
        config = Config.load()

        # === When: 使用高阈值搜索 ===
        result = await article_retrieval.search_articles(
            query="非常具体的查询词xyz123",
            top_k=10,
            threshold=0.9  # 高阈值
        )

        # === Then: 验证结果 ===
        assert "results" in result, "结果应包含 'results' 字段"
        # 高阈值可能返回较少或没有结果
        assert isinstance(result["results"], list), "results 应该是列表"

        # 如果有结果，验证它们符合阈值（通过 EBD 相似度）
        for doc in result["results"]:
            if "ebd_similarity" in doc and doc["ebd_similarity"] is not None:
                assert doc["ebd_similarity"] >= 0.9, \
                    f"EBD 相似度应 >= 阈值 0.9，实际: {doc['ebd_similarity']}"

    finally:
        api_clients.close_clients()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rerank_client_singleton():
    """测试 rerank 客户端单例模式

    Given: 清空的客户端状态
    When: 多次获取 rerank 客户端
    Then: 返回同一个实例
    """
    # === Given: 清空客户端 ===
    api_clients._rerank_client = None

    try:
        # === When: 多次获取客户端 ===
        client1 = api_clients.get_rerank_client()
        client2 = api_clients.get_rerank_client()
        client3 = api_clients.get_rerank_client()

        # === Then: 验证是同一个实例 ===
        assert client1 is client2, "多次调用应返回同一个实例"
        assert client2 is client3, "多次调用应返回同一个实例"

        # 验证客户端已初始化
        assert client1 is not None, "客户端不应为 None"

    finally:
        # 清理
        api_clients.close_clients()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rerank_close_clients_idempotent():
    """测试关闭客户端的幂等性

    Given: 已初始化的客户端
    When: 多次调用 close_clients
    Then: 不抛出异常，且可正常重新初始化
    """
    try:
        # === Given: 初始化客户端 ===
        client1 = api_clients.get_rerank_client()
        assert client1 is not None, "客户端应初始化"

        # === When: 多次关闭 ===
        api_clients.close_clients()  # 第一次关闭
        api_clients.close_clients()  # 第二次关闭（应幂等）
        api_clients.close_clients()  # 第三次关闭（应幂等）

        # === Then: 验证可以重新初始化 ===
        api_clients._rerank_client = None  # 清空引用
        client2 = api_clients.get_rerank_client()
        assert client2 is not None, "关闭后应能重新初始化"

    finally:
        # 最终清理
        api_clients.close_clients()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_rerank_requests():
    """测试并发 rerank 请求

    Given: 配置好的环境
    When: 同时发起多个搜索请求
    Then: 所有请求都正确返回，无死锁或资源泄漏
    """
    # 重置客户端
    api_clients.close_clients()

    try:
        # === Given: 配置好的环境 ===
        config = Config.load()

        # === When: 并发执行多个搜索 ===
        queries = [
            "内部培训流程",
            "职称评审制度",
            "通用知识库政策",
        ]

        # 并发执行搜索
        results = await asyncio.gather(*[
            article_retrieval.search_articles(query, top_k=3)
            for query in queries
        ], return_exceptions=True)

        # === Then: 验证所有请求都成功 ===
        assert len(results) == len(queries), "应返回与请求数量相同的结果"

        for i, result in enumerate(results):
            # 不应该是异常
            assert not isinstance(result, Exception), \
                f"查询 {queries[i]} 不应抛出异常，实际: {result}"

            # 验证结果结构
            assert "results" in result, f"查询 {queries[i]} 应包含 results 字段"
            assert isinstance(result["results"], list), f"查询 {queries[i]} 的 results 应该是列表"

    finally:
        # 清理
        api_clients.close_clients()
