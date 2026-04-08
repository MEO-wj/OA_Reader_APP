# AI 服务抽离设计方案

**日期**: 2026-03-15

## 目标

将 backend 中的 AI 相关逻辑抽离成独立的 ai_end 服务，实现业务逻辑与 AI 能力的解耦。

## 架构概览

```
┌─────────────┐      HTTP       ┌─────────────┐
│   backend   │ ──────────────► │   ai_end    │
│  (业务逻辑)  │    /ask API    │  (AI 推理)  │
└──────┬──────┘                 └──────┬──────┘
       │                               │
       │         ┌─────────────┐       │
       └────────►│  PostgreSQL │◄──────┘
        业务查询   │  (pgvector) │   向量搜索
                 └─────────────┘
```

## 职责分离

| 模块 | 职责 |
|------|------|
| **backend** | 业务逻辑、API路由、数据库CRUD、调用 ai_end |
| **ai_end** | AI 问答、向量嵌入生成、负载均衡、请求队列 |
| **pgvector** | 存储文章向量，供 ai_end 查询相似文章 |

## ai_end API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/ask` | POST | AI 问答 |

请求参数:
```json
{
  "question": "问题内容",
  "top_k": 3,
  "display_name": "用户昵称",
  "user_id": "用户ID"
}
```

响应:
```json
{
  "answer": "AI 回答内容",
  "related_articles": [...]
}
```

## 数据流

1. 用户发起问答请求 → backend `/ai/ask`
2. backend 验证用户身份，将请求转发给 ai_end `/ask`
3. ai_end 接收请求：
   - 调用 embedding API 生成向量
   - 查询 pgvector 获取相似文章
   - 调用 LLM 生成回答
4. ai_end 返回回答 → backend → 返回给用户

## 配置分离

- **backend**: 移除所有 AI 相关配置
- **ai_end**: 独立配置文件（复用原 backend AI 配置）

## 部署方式

- **backend**: 保持现有部署方式
- **ai_end**: Docker 容器部署

## 待迁移文件

从 backend 迁移到 ai_end:
- `backend/routes/ai.py` → `ai_end/app.py`
- `backend/services/ai_queue.py` → `ai_end/services/queue.py`
- `backend/services/ai_load_balancer.py` → `ai_end/services/load_balancer.py`
- `backend/config.py` (AI 部分) → `ai_end/config.py`
