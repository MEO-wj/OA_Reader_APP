"""OA 系统增量爬虫核心执行流程。

该模块是爬虫的核心组件，负责协调各个子模块完成完整的爬取流程：
- 日期规范化处理
- 运行时段控制（仅07-24点运行当日数据）
- 增量爬取逻辑（避免重复抓取）
- 文章列表获取和过滤
- 文章详情获取
- AI 摘要生成
- 向量生成
- 数据存储到数据库

使用数据库会话管理和事务处理，确保数据一致性。
"""

from __future__ import annotations

import datetime
import time
from typing import List

from crawler.config import Config
from crawler.embeddings import Embedder
from crawler.fetcher import fetch_detail, fetch_list, fetch_list_paged
from crawler.models import ArticleRecord, ArticleMeta
from crawler.storage import ArticleRepository
from crawler.summarizer import Summarizer
from crawler.db import db_session



def _normalize_date(raw: str | None) -> str:
    """规范化日期格式。
    
    如果日期为 None，则使用当前日期；否则将日期字符串转换为标准格式。
    
    参数：
        raw: 原始日期字符串或 None
        
    返回：
        str: 标准化的日期字符串，格式为 YYYY-MM-DD
    """
    if raw is None:
        return time.strftime("%Y-%m-%d", time.localtime())
    return datetime.datetime.strptime(raw, "%Y-%m-%d").strftime("%Y-%m-%d")


class Crawler:
    """OA 系统增量爬虫类。

    实现了按天、按时的增量爬取逻辑，包含完整的爬取流程控制。
    支持指定日期的历史数据补抓。
    """

    def __init__(self, target_date: str | None = None, enable_delay: bool = False) -> None:
        """初始化爬虫实例。

        参数：
            target_date: 目标日期，格式为 YYYY-MM-DD；若为 None 则使用当前日期
            enable_delay: 是否启用文章间延迟（用于回填场景）
        """
        self.config = Config()
        self.target_date = _normalize_date(target_date)
        self.enable_delay = enable_delay
        self.summarizer = Summarizer(self.config)  # 摘要生成器
        self.embedder = Embedder(self.config)  # 向量生成器
        self.repo = ArticleRepository()  # 数据仓库
        self._article_count = 0  # 本次爬取的文章数

    def _within_hours(self) -> bool:
        """检查是否在允许的运行时段内。
        
        - 如果是历史日期，则始终允许运行
        - 如果是当天日期，则仅在 07:00-24:00 时段允许运行
        
        返回：
            bool: 是否在允许的运行时段内
        """
        now = datetime.datetime.now()
        if self.target_date != now.strftime("%Y-%m-%d"):
            return True  # 历史日期始终运行
        return 7 <= now.hour < 24  # 当天仅在 07-24 点运行

    def _random_delay(self) -> None:
        """文章间随机延迟。

        根据配置中的延迟参数进行随机延迟，用于回填场景避免触发反爬。
        """
        if not self.config.backfill_enable_random_delay:
            return

        import random
        delay_min = self.config.backfill_delay_min
        delay_max = self.config.backfill_delay_max
        delay = random.uniform(delay_min, delay_max)
        time.sleep(delay)

    def get_article_count(self) -> int:
        """获取本次运行爬取的文章数。

        返回：
            int: 爬取的文章数量
        """
        return self._article_count

    def run(self) -> None:
        """执行完整的爬取流程。
        
        包含以下步骤：
        1. 检查运行时段
        2. 初始化数据库结构（如果数据库可用）
        3. 获取已有链接（去重，如果数据库可用）
        4. 获取文章列表
        5. 过滤新增文章（如果数据库可用）
        6. 获取文章详情
        7. 生成AI摘要
        8. 存储文章数据（如果数据库可用）
        9. 生成和存储向量（如果数据库可用）
        """
        if not self._within_hours():
            print("当前不在运行时段(07-24)，跳过执行")
            return

        print(f"开始增量抓取 {self.target_date} 的OA通知")
        
        # 初始化变量
        conn = None
        existing_links = set()
        use_database = True
        
        # 尝试连接数据库
        try:
            from crawler.db import get_connection
            conn = get_connection()
            print("✅ 数据库连接成功")
            
            # 确保数据库结构存在
            print("正在检查数据库结构...")
            self.repo.ensure_schema(conn)
            print("✅ 数据库结构检查完成")
            
            # 获取已存在的链接（用于去重）
            print("正在获取已存在的链接...")
            existing_links = self.repo.existing_links(conn, self.target_date)
            print(f"✅ 已存在 {len(existing_links)} 条记录")
        except Exception as e:
            print(f"⚠️ 数据库连接失败: {type(e).__name__}: {e}")
            print("将继续执行爬虫，但不会进行去重和存储操作")
            use_database = False
            conn = None
        
        try:
            # 获取当天文章列表
            print("正在获取文章列表...")
            if self.enable_delay:
                candidates = fetch_list_paged(self.target_date)
            else:
                candidates = fetch_list(self.target_date)
            if not candidates:
                print("未获取到当天列表，结束")
                # 如果数据库连接已建立，关闭连接
                if conn:
                    conn.close()
                return
            print(f"✅ 获取到 {len(candidates)} 条文章列表")

            # 过滤新增文章（不在已有链接中）
            new_items = [item for item in candidates if item.link not in existing_links]
            print(f"列表总计 {len(candidates)} 条，新增 {len(new_items)} 条")
            if not new_items:
                # 如果数据库连接已建立，关闭连接
                if conn:
                    conn.close()
                return

            # 获取文章详情
            detailed: list[dict] = []
            print("正在获取文章详情...")
            for i, item in enumerate(new_items, 1):
                print(f"  处理第 {i}/{len(new_items)} 篇: {item.title}")
                detail = fetch_detail(item.link)
                if not detail.content:
                    print(f"    ⚠️ 跳过 {item.link}，未获取到正文")
                    continue
                detailed.append(
                    {
                        "标题": item.title,
                        "发布单位": item.unit,
                        "链接": item.link,
                        "发布日期": item.published_on,
                        "正文": detail.content,
                        "附件": detail.attachments,
                    }
                )
                # 文章间随机延迟（用于回填场景）
                if self.enable_delay and i < len(new_items):
                    self._random_delay()
            print(f"✅ 获取到 {len(detailed)} 篇文章详情")

            if not detailed:
                print("没有可处理的新文章")
                # 如果数据库连接已建立，关闭连接
                if conn:
                    conn.close()
                return

            # 生成AI摘要
            print("正在生成AI摘要...")
            self._fill_summaries(detailed)
            print("✅ AI摘要生成完成")

            # 转换为数据库记录并存储（如果数据库可用）
            if use_database and conn:
                print("正在存储文章数据...")
                try:
                    # psycopg3 事务是隐式管理的，不需要 conn.begin()
                    # 当执行第一条 SQL 时事务自动开始

                    for item in detailed:
                        # 跳过没有摘要的文章（摘要生成失败）
                        if not item.get("摘要") or item["摘要"] == "[AI摘要失败]":
                            print(f"  跳过（无有效摘要）: {item['标题']}")
                            continue

                        record = ArticleRecord(
                            title=item["标题"],
                            unit=item["发布单位"],
                            link=item["链接"],
                            published_on=item["发布日期"],
                            content=item["正文"],
                            summary=item["摘要"],
                            attachments=item.get("附件", []),
                        )

                        # 插入文章（不自动提交）
                        inserted = self.repo.insert_articles(conn, [record], commit=False)
                        if inserted == 0:
                            print(f"  跳过（已存在或插入失败）: {item['标题']}")
                            continue

                        # 获取刚插入的文章 ID
                        articles = self.repo.fetch_for_embedding(conn, [item["链接"]])
                        if not articles:
                            conn.rollback()  # 回滚当前文章事务，避免后续误提交
                            print(f"  跳过（无法获取文章ID）: {item['标题']}")
                            continue

                        # 生成向量
                        ok = self._generate_embeddings(conn, articles)
                        if not ok:
                            conn.rollback()  # 回滚事务
                            print(f"  向量生成失败，回滚: {item['标题']}")
                            continue

                        # 单篇提交
                        conn.commit()
                        self._article_count += 1
                        print(f"  入库成功: {item['标题']}")

                except Exception as e:
                    conn.rollback()
                    print(f"⚠️ 数据库操作失败: {type(e).__name__}: {e}")
            else:
                print("⚠️ 数据库不可用，跳过存储操作")
                print(f"共获取到 {len(detailed)} 篇文章详情，其中:")
                for item in detailed[:5]:  # 只显示前5篇文章
                    print(f"- {item['标题']} ({item['链接']})")
                if len(detailed) > 5:
                    print(f"- ... 还有 {len(detailed) - 5} 篇文章")
            
            # 如果数据库连接已建立，关闭连接
            if conn:
                conn.close()
        except Exception as e:
            print(f"❌ 爬虫执行失败: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            # 如果数据库连接已建立，关闭连接
            if conn:
                conn.close()
        print("爬虫执行完成")

    # ------------------------------------------------------------------ AI 摘要相关方法
    def _fill_summaries(self, items: list[dict]) -> None:
        """为文章列表生成AI摘要（带重试机制）。
        
        参数：
            items: 文章列表，每个元素是包含"正文"字段的字典
        """
        remaining = list(items)
        max_retries = 3
        attempt = 0
        
        # 重试机制
        while remaining and attempt <= max_retries:
            failures: list[dict] = []
            for item in remaining:
                summary = self.summarizer.summarize(item["正文"])
                if summary:
                    item["摘要"] = summary
                else:
                    failures.append(item)
            
            # 所有摘要生成成功
            if not failures:
                break
                
            attempt += 1
            if attempt > max_retries:
                break
                
            remaining = failures
            if remaining:
                print(f"AI摘要失败 {len(remaining)} 条，开始第 {attempt} 次重试")

        # 为仍失败的文章添加默认摘要
        for item in remaining:
            item["摘要"] = item.get("摘要") or "[AI摘要失败]"

    # ------------------------------------------------------------------ 向量生成相关方法
    def _compose_embed_text(self, article: dict) -> str:
        """组合文章的标题、摘要和正文，用于生成向量。
        
        参数：
            article: 包含标题、摘要和正文的文章字典
            
        返回：
            str: 组合后的文本（最多2000字符）
        """
        body = article.get("content") or ""
        summary = article.get("summary") or ""
        title = article.get("title") or ""
        combined = "\n".join([title, summary, body])
        return combined[:2000]  # 限制最大长度

    def _call_embedding(self, texts: list[str]) -> list[list[float]] | None:
        """调用向量生成API生成文本向量。
        
        参数：
            texts: 文本列表
            
        返回：
            list[list[float]] | None: 向量列表，失败时返回None
        """
        cfg = self.config
        return self.embedder.embed_batch(texts)

    def _generate_embeddings(self, conn, articles: List[dict]) -> bool:
        """为文章生成向量并存储到数据库。

        参数：
            conn: 数据库连接对象
            articles: 文章列表，包含文章ID、标题、摘要和正文

        返回：
            bool: 是否成功生成向量
        """
        # 组合文本用于生成向量
        texts = [self._compose_embed_text(a) for a in articles]
        # 调用向量生成API
        embeddings = self._call_embedding(texts)
        if not embeddings:
            return False

        # 准备存储数据
        payloads = []
        for article, emb in zip(articles, embeddings):
            # 将向量转换为数据库存储格式
            emb_str = "[" + ",".join(f"{x:.6f}" for x in emb) + "]"
            payloads.append(
                {
                    "article_id": article["id"],
                    "embedding": emb_str,
                    "published_on": article["published_on"],
                }
            )

        # 存储向量到数据库（不自动提交）
        inserted = self.repo.insert_embeddings(conn, payloads, commit=False)
        print(f"向量入库完成，新增 {inserted} 条")
        return True
