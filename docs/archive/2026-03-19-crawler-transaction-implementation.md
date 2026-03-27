# Crawler 数据流水线事务化实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 解决 crawler 爬取流程中"文章入库后向量生成失败"导致的数据不一致问题。以单篇文章为处理单位，三个维度任一失败则该文章不入库。

**Architecture:** 在 `db.py` 的 `insert_articles()` 和 `insert_embeddings()` 加 `commit` 参数控制提交时机，在 `pipeline.py` 的 `run()` 中用事务包裹每篇文章的完整流程。

**Tech Stack:** Python, psycopg, PostgreSQL, pgvector

---

## Task 1: 修改 db.py - insert_articles() 加 commit 参数

**Files:**
- Modify: `crawler/db.py:108-142`

**Step 1: 添加 commit 参数**

```python
def insert_articles(conn: psycopg.Connection, records: Iterable[ArticleRecord], commit: bool = True) -> int:
    """批量插入文章记录，已存在的链接会被忽略（基于UNIQUE约束）。

    参数：
        conn: 数据库连接对象
        records: ArticleRecord 对象的可迭代集合
        commit: 是否立即提交，False 时由调用方控制事务

    返回：
        int: 成功插入的记录数
    """
    sql = """
    INSERT INTO articles (title, unit, link, published_on, content, summary, attachments)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (link) DO NOTHING  -- 链接冲突时忽略
    """

    count = 0
    with conn.cursor() as cur:
        for rec in records:
            cur.execute(
                sql,
                (
                    rec.title,          # 文章标题
                    rec.unit,           # 发布单位
                    rec.link,           # 文章链接
                    rec.published_on,   # 发布日期
                    rec.content,        # 文章内容
                    rec.summary,        # 文章摘要
                    Json(rec.attachments),  # 附件信息（转换为JSONB）
                ),
            )
            count += cur.rowcount  # 累加受影响的行数

    if commit:
        conn.commit()
    return count
```

**Step 2: 验证语法正确**

Run: `cd /home/handy/OAP/crawler && python -m py_compile db.py`
Expected: 无输出（语法正确）

---

## Task 2: 修改 db.py - insert_embeddings() 加 commit 参数

**Files:**
- Modify: `crawler/db.py:180-206`

**Step 1: 添加 commit 参数**

```python
def insert_embeddings(conn: psycopg.Connection, payloads: Iterable[dict[str, Any]], commit: bool = True) -> int:
    """批量插入文章向量记录，已存在的article_id会被忽略。

    参数：
        conn: 数据库连接对象
        payloads: 向量数据字典的可迭代集合，每个字典包含：
                  - article_id: 文章ID
                  - embedding: 向量数据
                  - published_on: 发布日期
        commit: 是否立即提交，False 时由调用方控制事务

    返回：
        int: 成功插入的记录数
    """
    sql = """
    INSERT INTO vectors (article_id, embedding, published_on)
    VALUES (%(article_id)s, %(embedding)s::vector, %(published_on)s)
    ON CONFLICT (article_id) DO NOTHING  -- article_id冲突时忽略
    """

    count = 0
    with conn.cursor() as cur:
        for item in payloads:
            cur.execute(sql, item)
            count += cur.rowcount  # 累加受影响的行数

    if commit:
        conn.commit()
    return count
```

**Step 2: 验证语法正确**

Run: `cd /home/handy/OAP/crawler && python -m py_compile db.py`
Expected: 无输出（语法正确）

---

## Task 3: 修改 storage.py - 透传 commit 参数

**Files:**
- Modify: `crawler/storage.py:56-66`
- Modify: `crawler/storage.py:80-90`

**Step 1: 修改 insert_articles() 透传 commit 参数**

```python
def insert_articles(self, conn: psycopg.Connection, records: Iterable[ArticleRecord], commit: bool = True) -> int:
    """批量插入文章数据。

    参数：
        conn: 数据库连接对象
        records: 文章记录迭代器
        commit: 是否立即提交，False 时由调用方控制事务

    返回：
        int: 成功插入的记录数
    """
    return insert_articles(conn, records, commit=commit)
```

**Step 2: 修改 insert_embeddings() 透传 commit 参数**

```python
def insert_embeddings(self, conn: psycopg.Connection, payloads: Iterable[dict[str, Any]], commit: bool = True) -> int:
    """批量插入文章向量数据。

    参数：
        conn: 数据库连接对象
        payloads: 向量数据迭代器
        commit: 是否立即提交，False 时由调用方控制事务

    返回：
        int: 成功插入的向量数
    """
    return insert_embeddings(conn, payloads, commit=commit)
```

**Step 3: 验证语法正确**

Run: `cd /home/handy/OAP/crawler && python -m py_compile storage.py`
Expected: 无输出（语法正确）

---

## Task 4: 修改 pipeline.py - 重构 run() 为事务模式

**Files:**
- Modify: `crawler/pipeline.py:106-262`
- Modify: `crawler/pipeline.py:329-358`

**Step 1: 重构 run() 方法**

将原有的批量处理流程重构为：
1. 外部 `conn.begin()` 开始事务
2. 对每篇文章：详情获取 → AI摘要 → insert_articles → 向量生成 → insert_embeddings → 单篇 commit
3. 摘要失败跳过该篇，不阻断其他文章
4. 向量失败触发 rollback

核心改动在 `run()` 方法的数据库存储部分（约第212-241行）。

**新流程：**
```python
# 数据库存储部分重构为：
if use_database and conn:
    print("正在存储文章数据...")
    try:
        conn.begin()  # 开始事务

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
                print(f"  跳过（无法获取文章ID）: {item['标题']}")
                continue

            # 生成向量
            ok = self._generate_embeddings(conn, articles)
            if not ok:
                conn.rollback()  # 回滚事务
                print(f"  向量生成失败，回滚: {item['标题']}")
                raise Exception("向量生成失败")

            # 单篇提交
            conn.commit()
            self._article_count += 1
            print(f"  入库成功: {item['标题']}")

    except Exception as e:
        conn.rollback()
        print(f"⚠️ 数据库操作失败: {type(e).__name__}: {e}")
```

**Step 2: 修改 _generate_embeddings() 返回布尔值**

将第329-358行的方法改为：
- 成功返回 `True`
- 失败（embeddings 为 None）返回 `False`
- 不再内部调用 `insert_embeddings`，由调用方控制

```python
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
        return False  # 失败标记

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
```

**Step 3: 验证语法正确**

Run: `cd /home/handy/OAP/crawler && python -m py_compile pipeline.py`
Expected: 无输出（语法正确）

---

## Task 5: 整体验证

**Step 1: 运行 lint 检查**

Run: `cd /home/handy/OAP/crawler && uv run ruff check .`
Expected: 无错误

**Step 2: 运行类型检查**

Run: `cd /home/handy/OAP/crawler && uv run ruff check . --select=type-annotations` 或 `mypy`
Expected: 无类型错误

---

## 改动文件清单

| 文件 | 改动内容 |
|------|----------|
| `crawler/db.py` | `insert_articles()` 加 `commit` 参数 |
| `crawler/db.py` | `insert_embeddings()` 加 `commit` 参数 |
| `crawler/storage.py` | `insert_articles()` 透传 `commit` 参数 |
| `crawler/storage.py` | `insert_embeddings()` 透传 `commit` 参数 |
| `crawler/pipeline.py` | 重构 `run()` 为事务模式 |
| `crawler/pipeline.py` | `_generate_embeddings()` 返回布尔值 |
