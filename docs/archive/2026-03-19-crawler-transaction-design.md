# Crawler 数据流水线事务化方案

## 1. 目标

解决 crawler 爬取流程中"文章入库后向量生成失败"导致的数据不一致问题。

## 2. 问题描述

当前流水线分两次数据库写入，且各自独立 commit：
1. `insert_articles()` → commit
2. `insert_embeddings()` → 可能失败，无回滚

结果：文章已入库，但向量缺失，数据不一致。

## 3. 解决方案

### 3.1 核心原则

- 以**单篇文章**为处理单位
- 三个维度（原文、摘要、向量）任一失败则该文章不入库
- 摘要/详情获取失败不阻断其他文章
- 向量生成失败触发整体回滚

### 3.2 数据流

```
新链接
  │
  ▼
fetch_detail()              ✅ 继续
  │                        ❌ 跳过
  ▼
生成 AI 摘要                ✅ 继续
  │                        ❌ 跳过
  ▼
insert_articles(commit=False)  ✅ 继续
  │                            ❌ 回滚该篇
  ▼
生成向量                    ✅ 继续
  │                        ❌ 回滚该篇
  ▼
insert_embeddings(commit=False) ✅ 继续
  │                              ❌ 回滚该篇
  ▼
conn.commit()               ← 单篇文章事务结束
```

### 3.3 数据库改动

#### `db.py` - insert_articles()

```python
def insert_articles(conn, records, commit=True):
    # ... 构造 INSERT SQL
    cur.execute(sql, values)
    if commit:
        conn.commit()
    return articles
```

#### `db.py` - insert_embeddings()

```python
def insert_embeddings(conn, articles, commit=True):
    # ... 批量插入向量
    cur.execute(sql, values)
    if commit:
        conn.commit()
```

### 3.4 Pipeline 改动

改造 `pipeline.py` 的 `run()` 方法：
- 事务包裹每篇文章
- 摘要失败跳过，向量失败回滚
- 单篇成功后立即 commit

## 4. 幂等性保证

- `articles.link` UNIQUE 约束 + `ON CONFLICT DO NOTHING`
- `vectors.article_id` UNIQUE 索引
- 重复执行安全

## 5. 改动文件

| 文件 | 改动 |
|------|------|
| `crawler/db.py` | `insert_articles()` 加 `commit` 参数 |
| `crawler/db.py` | `insert_embeddings()` 加 `commit` 参数 |
| `crawler/pipeline.py` | 改造 `run()` 为事务模式 |

## 6. 极端情况

| 场景 | 处理 |
|------|------|
| 向量生成成功但 commit 前崩溃 | cron 重跑时，文章因 UNIQUE 冲突跳过，向量重新生成 |
| AI 摘要失败 | 跳过该篇，不影响其他文章 |
| fetch_detail 失败 | 跳过该篇，不影响其他文章 |
