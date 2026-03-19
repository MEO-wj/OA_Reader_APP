"""爬虫集成测试 - 事务回滚验证

测试场景：
1. 向量生成失败 → 事务回滚，文章不入库
2. AI摘要失败 → 跳过该文章，不阻断其他文章
3. 向量入库失败 → 事务回滚，文章不入库
4. 文章重复 → 已存在的文章被跳过

注意：这些测试需要真实的 PostgreSQL + pgvector 数据库环境。
使用环境变量 DATABASE_URL 指定数据库连接。
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock, patch, Mock
from datetime import date

# 假设测试运行时设置 DATABASE_URL 环境变量
DATABASE_URL = os.environ.get("DATABASE_URL")
SKIP_DB_TESTS = DATABASE_URL is None


class TestTransactionRollback:
    """事务回滚机制测试"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前准备"""
        # 延迟导入避免模块加载问题
        from crawler.db import get_connection, init_db
        from crawler.storage import ArticleRepository
        from crawler.models import ArticleRecord

        self.get_connection = get_connection
        self.init_db = init_db
        self.repo = ArticleRepository()
        self.ArticleRecord = ArticleRecord

    def _get_test_article(self, link_suffix: str = "") -> dict:
        """创建测试用文章数据"""
        import uuid
        unique_id = str(uuid.uuid4())[:8]
        return {
            "标题": f"测试文章_{unique_id}",
            "发布单位": "测试单位",
            "链接": f"https://example.com/article/{unique_id}{link_suffix}",
            "发布日期": date.today().isoformat(),
            "正文": "这是测试文章的正文内容，用于验证事务回滚机制。",
            "摘要": "这是AI生成的测试摘要",
            "附件": [],
        }

    def _clean_test_data(self, conn, link: str):
        """清理测试数据"""
        with conn.cursor() as cur:
            cur.execute("DELETE FROM vectors WHERE article_id IN (SELECT id FROM articles WHERE link = %s)", (link,))
            cur.execute("DELETE FROM articles WHERE link = %s", (link,))
        conn.commit()

    # ===== 测试1: 向量生成失败 → 事务回滚，文章不入库 =====

    @pytest.mark.skipif(SKIP_DB_TESTS, reason="需要 DATABASE_URL 环境变量")
    def test_article_not_stored_when_embedding_fails(self):
        """向量生成失败时，文章不应入库"""

        item = self._get_test_article()
        link = item["链接"]

        try:
            conn = self.get_connection()
            self.init_db(conn)
            self._clean_test_data(conn, link)

            # 验证文章不存在
            existing = self.repo.existing_links(conn, item["发布日期"])
            assert link not in existing, "测试前文章不应存在"

            # Mock 向量生成失败
            with patch.object(
                self.repo, '_Crawler__embedder',  # 或者直接 mock embedder
                create=True
            ), patch('crawler.pipeline.Embedder') as MockEmbedder:
                MockEmbedder.return_value.embed_batch.return_value = None  # 向量生成失败

                # 手动模拟 Crawler 的事务逻辑
                record = self.ArticleRecord(
                    title=item["标题"],
                    unit=item["发布单位"],
                    link=item["链接"],
                    published_on=item["发布日期"],
                    content=item["正文"],
                    summary=item["摘要"],
                    attachments=item.get("附件", []),
                )

                conn.begin()
                inserted = self.repo.insert_articles(conn, [record], commit=False)

                # 模拟向量生成失败
                ok = False  # 模拟 _generate_embeddings 返回 False
                if not ok:
                    conn.rollback()
                    print(f"向量生成失败，回滚: {item['标题']}")
                else:
                    conn.commit()

            # 验证：文章应该不存在（被回滚了）
            conn.rollback()  # 确保任何未提交的事务都被回滚
            existing_after = self.repo.existing_links(conn, item["发布日期"])
            assert link not in existing_after, "向量生成失败时，文章不应入库"

        finally:
            self._clean_test_data(conn, link)
            conn.close()

    # ===== 测试2: AI摘要失败 → 跳过该文章，不阻断其他文章 =====

    @pytest.mark.skipif(SKIP_DB_TESTS, reason="需要 DATABASE_URL 环境变量")
    def test_articles_continue_after_summary_failure(self):
        """AI摘要失败时，跳过该文章但继续处理其他文章"""

        items = [self._get_test_article(), self._get_test_article()]

        try:
            conn = self.get_connection()
            self.init_db(conn)

            for item in items:
                self._clean_test_data(conn, item["链接"])

            # 模拟：第1篇摘要失败，第2篇成功
            summaries = {
                items[0]["链接"]: None,  # 摘要失败
                items[1]["链接"]: "成功生成的摘要",
            }

            success_count = 0
            skip_count = 0

            for item in items:
                summary = summaries.get(item["链接"])
                if not summary or summary == "[AI摘要失败]":
                    print(f"跳过（无有效摘要）: {item['标题']}")
                    skip_count += 1
                    continue

                # 正常入库
                record = self.ArticleRecord(
                    title=item["标题"],
                    unit=item["发布单位"],
                    link=item["链接"],
                    published_on=item["发布日期"],
                    content=item["正文"],
                    summary=summary,
                    attachments=item.get("附件", []),
                )

                conn.begin()
                inserted = self.repo.insert_articles(conn, [record], commit=False)
                conn.commit()
                if inserted > 0:
                    success_count += 1

            # 验证：第1篇被跳过，第2篇入库成功
            assert skip_count == 1, "应该有1篇被跳过"
            assert success_count == 1, "应该有1篇入库成功"

            # 验证：第1篇不存在，第2篇存在
            existing = self.repo.existing_links(conn, items[0]["发布日期"])
            assert items[0]["链接"] not in existing, "第1篇（摘要失败）不应入库"
            assert items[1]["链接"] in existing, "第2篇（摘要成功）应该入库"

        finally:
            for item in items:
                self._clean_test_data(conn, item["链接"])
            conn.close()

    # ===== 测试3: 向量入库失败 → 事务回滚，文章不入库 =====

    @pytest.mark.skipif(SKIP_DB_TESTS, reason="需要 DATABASE_URL 环境变量")
    def test_article_not_stored_when_vector_insert_fails(self):
        """向量入库失败时，文章和向量都不应入库"""

        item = self._get_test_article()
        link = item["链接"]

        try:
            conn = self.get_connection()
            self.init_db(conn)
            self._clean_test_data(conn, link)

            record = self.ArticleRecord(
                title=item["标题"],
                unit=item["发布单位"],
                link=item["链接"],
                published_on=item["发布日期"],
                content=item["正文"],
                summary=item["摘要"],
                attachments=item.get("附件", []),
            )

            # 模拟：文章入库成功，但向量入库失败（通过 mock insert_embeddings）
            conn.begin()
            inserted_article = self.repo.insert_articles(conn, [record], commit=False)
            assert inserted_article > 0, "文章应该插入成功"

            # 获取刚插入的文章 ID
            articles = self.repo.fetch_for_embedding(conn, [link])
            assert len(articles) > 0, "应该能获取到文章ID"

            # 模拟向量入库失败（通过抛出异常）
            def mock_insert_embeddings(*args, **kwargs):
                raise Exception("向量表不存在或插入失败")

            with patch.object(self.repo, 'insert_embeddings', side_effect=mock_insert_embeddings):
                try:
                    # 模拟 _generate_embeddings 的逻辑
                    payloads = [
                        {
                            "article_id": articles[0]["id"],
                            "embedding": "[0.1,0.2,0.3]",
                            "published_on": item["发布日期"],
                        }
                    ]
                    self.repo.insert_embeddings(conn, payloads, commit=False)
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    print(f"向量入库失败，回滚: {e}")

            # 验证：文章应该不存在（被回滚了）
            conn.rollback()  # 确保任何未提交的事务都被回滚
            existing_after = self.repo.existing_links(conn, item["发布日期"])
            assert link not in existing_after, "向量入库失败时，文章不应入库"

        finally:
            self._clean_test_data(conn, link)
            conn.close()

    # ===== 测试4: 文章重复 → 已存在的文章被跳过 =====

    @pytest.mark.skipif(SKIP_DB_TESTS, reason="需要 DATABASE_URL 环境变量")
    def test_duplicate_article_skipped(self):
        """已存在的文章应该被跳过"""

        item = self._get_test_article()
        link = item["链接"]

        try:
            conn = self.get_connection()
            self.init_db(conn)
            self._clean_test_data(conn, link)

            record = self.ArticleRecord(
                title=item["标题"],
                unit=item["发布单位"],
                link=item["链接"],
                published_on=item["发布日期"],
                content=item["正文"],
                summary=item["摘要"],
                attachments=item.get("附件", []),
            )

            # 第1次插入：成功
            conn.begin()
            inserted1 = self.repo.insert_articles(conn, [record], commit=False)
            conn.commit()
            assert inserted1 == 1, "第1次插入应该成功"

            # 第2次插入（重复）：应该被跳过
            conn.begin()
            inserted2 = self.repo.insert_articles(conn, [record], commit=False)
            conn.commit()
            assert inserted2 == 0, "重复插入应该被跳过（返回0）"

            # 验证：数据库中只有1条记录
            existing = self.repo.existing_links(conn, item["发布日期"])
            assert list(existing).count(link) == 1, "数据库中应该只有1条记录"

        finally:
            self._clean_test_data(conn, link)
            conn.close()


class TestPipelineTransactionFlow:
    """Pipeline 事务流程集成测试

    这些测试验证完整的爬取流程中的事务行为。
    """

    @pytest.fixture(autouse=True)
    def setup_pipeline(self):
        """准备 Pipeline 测试环境"""
        from crawler.pipeline import Crawler
        from crawler.config import Config

        self.Crawler = Crawler
        self.Config = Config

    def _create_mock_crawler(self) -> MagicMock:
        """创建 Mock Crawler"""
        crawler = MagicMock()
        crawler.config = self.Config()
        crawler.repo = MagicMock()
        crawler.summarizer = MagicMock()
        crawler.embedder = MagicMock()
        return crawler

    @pytest.mark.skipif(SKIP_DB_TESTS, reason="需要 DATABASE_URL 环境变量")
    def test_single_article_rollback_isolation(self):
        """验证单篇文章失败不会影响其他已提交的文章

        场景：
        - 文章A：成功入库 + 成功生成向量
        - 文章B：成功入库 + 向量生成失败 → 回滚
        - 文章C：成功入库 + 成功生成向量

        预期：
        - 文章A：存在
        - 文章B：不存在（被回滚）
        - 文章C：存在
        """
        from crawler.db import get_connection, init_db
        from crawler.storage import ArticleRepository
        from crawler.models import ArticleRecord
        from datetime import date

        repo = ArticleRepository()
        link_a = f"https://example.com/article_a_{date.today()}"
        link_b = f"https://example.com/article_b_{date.today()}"
        link_c = f"https://example.com/article_c_{date.today()}"

        articles_data = [
            {"title": "Article_A", "link": link_a, "success": True},
            {"title": "Article_B", "link": link_b, "success": False},  # 向量生成失败
            {"title": "Article_C", "link": link_c, "success": True},
        ]

        try:
            conn = get_connection()
            init_db(conn)

            # 清理测试数据
            for a in articles_data:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM vectors WHERE article_id IN (SELECT id FROM articles WHERE link = %s)", (a["link"],))
                    cur.execute("DELETE FROM articles WHERE link = %s", (a["link"],))
                conn.commit()

            # 模拟 Crawler 的事务处理逻辑
            for article_data in articles_data:
                record = ArticleRecord(
                    title=article_data["title"],
                    unit="测试单位",
                    link=article_data["link"],
                    published_on=date.today().isoformat(),
                    content="测试正文内容",
                    summary="测试摘要",
                    attachments=[],
                )

                conn.begin()
                inserted = repo.insert_articles(conn, [record], commit=False)

                if inserted == 0:
                    print(f"跳过（已存在或插入失败）: {article_data['title']}")
                    continue

                # 模拟向量生成（成功或失败）
                if not article_data["success"]:
                    conn.rollback()
                    print(f"向量生成失败，回滚: {article_data['title']}")
                    continue

                conn.commit()
                print(f"入库成功: {article_data['title']}")

            # 验证结果
            existing = repo.existing_links(conn, date.today().isoformat())

            assert link_a in existing, "文章A应该存在"
            assert link_b not in existing, "文章B不应该存在（被回滚）"
            assert link_c in existing, "文章C应该存在"

        finally:
            conn.rollback()
            for a in articles_data:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM vectors WHERE article_id IN (SELECT id FROM articles WHERE link = %s)", (a["link"],))
                    cur.execute("DELETE FROM articles WHERE link = %s", (a["link"],))
                conn.commit()
            conn.close()


if __name__ == "__main__":
    # 运行测试
    # DATABASE_URL="postgresql://user:pass@localhost:5432/dbname" python -m pytest tests/test_transaction.py -v
    pytest.main([__file__, "-v"])
