# 配置说明

本文档详细说明OAP项目的环境变量配置。

## 后端环境变量（backend/.env）

### 数据库配置

```bash
# PostgreSQL数据库连接URL
DATABASE_URL=postgresql://user:pass@localhost:5432/oap
```

**说明：**
- 必须使用PostgreSQL 15+版本
- 需要安装pgvector扩展
- 数据库名称建议使用`oap`

### Redis配置

> **注意**：Redis 已从项目中移除。AI 对话历史现在存储在 PostgreSQL 中。

~~本节已废弃，保留作为历史参考。~~

### JWT认证配置

```bash
# JWT访问令牌签名密钥（必须设置）
AUTH_JWT_SECRET=your-secret-key-here

# JWT刷新令牌哈希密钥（必须设置）
AUTH_REFRESH_HASH_KEY=your-hash-key-here
```

**说明：**
- 这两个密钥必须设置为强随机字符串
- 生产环境必须修改默认值
- 建议使用至少32位的随机字符串

### AI服务配置

> **注意**：ai_end 已重构为 FastAPI + 技能系统架构，环境变量名已变更。以下为当前使用的变量名。

```bash
# AI服务基础URL
OPENAI_BASE_URL=https://api.openai.com/v1

# AI模型名称
OPENAI_MODEL=deepseek-v3.2

# AI服务API密钥
OPENAI_API_KEY=your-api-key-here
```

**说明：**
- 支持OpenAI兼容的API服务
- 可使用其他兼容服务（如Azure OpenAI、本地部署的模型）
- `OPENAI_BASE_URL` 应指向 API 根路径（如 `https://api.openai.com/v1`）

### 嵌入服务配置

```bash
# 嵌入模型名称
EMBEDDING_MODEL=BAAI/bge-m3

# 向量维度
EMBEDDING_DIMENSIONS=1024

# 嵌入服务API地址（可选，不设置则继承 OPENAI_BASE_URL）
# EMBEDDING_BASE_URL=https://api.openai.com/v1

# 嵌入服务API密钥（可选，不设置则继承 OPENAI_API_KEY）
# EMBEDDING_API_KEY=your-api-key-here
```

**说明：**
- 用于生成文章的向量嵌入
- `EMBEDDING_DIMENSIONS` 必须与模型输出的维度一致
- 默认使用 BAAI/bge-m3 模型，维度 1024

### Rerank 服务配置

```bash
# Rerank 模型名称
RERANK_MODEL=BAAI/bge-reranker-v2-m3

# Rerank 最大候选数
RERANK_MAX_CANDIDATES=40

# Rerank 超时 (秒)
RERANK_TIMEOUT=60.0

# Rerank API 地址（可选，不设置则继承 OPENAI_BASE_URL）
# RERANK_BASE_URL=https://api.openai.com/v1
```

### LLM 生成参数配置

```bash
# LLM 请求超时 (秒)
LLM_TIMEOUT=120.0

# Embedding 请求超时 (秒)
EMBEDDING_TIMEOUT=30.0

# LLM 最大 token 数
LLM_MAX_TOKENS=1500

# LLM 温度参数
LLM_TEMPERATURE=0.1
```

### 向量搜索限制配置

```bash
# 向量搜索的时间范围（天）
AI_VECTOR_LIMIT_DAYS=365

# 向量搜索的文章数量限制
AI_VECTOR_LIMIT_COUNT=10000
```

**说明：**
- `AI_VECTOR_LIMIT_DAYS`：只搜索最近N天的文章
- `AI_VECTOR_LIMIT_COUNT`：最多搜索N篇文章
- 这些限制用于提高搜索性能

### CORS配置

```bash
# 允许跨域的来源（多个用逗号分隔）
CORS_ALLOW_ORIGINS=http://localhost:8081,http://localhost:19006
```

**说明：**
- 开发环境可设置为`*`允许所有来源
- 生产环境应设置具体的域名

### 限流配置

```bash
# 每日请求限制
RATE_LIMIT_PER_DAY=100

# 每小时请求限制
RATE_LIMIT_PER_HOUR=20
```

**说明：**
- 用于防止API滥用
- 设置为空或0表示不启用限流

## 爬虫环境变量（crawler/.env）

### 数据库配置

```bash
# PostgreSQL数据库连接URL（与后端相同）
DATABASE_URL=postgresql://user:pass@localhost:5432/oap
```

### AI服务配置

```bash
# AI服务基础URL（与后端相同）
AI_BASE_URL=https://api.openai.com/v1

# AI模型名称（与后端相同）
AI_MODEL=gpt-4

# AI服务API密钥（与后端相同）
API_KEY=your-api-key-here
```

### 嵌入服务配置

```bash
# 嵌入服务基础URL（与后端相同）
EMBED_BASE_URL=https://api.openai.com/v1

# 嵌入模型名称（与后端相同）
EMBED_MODEL=text-embedding-3-small

# 嵌入服务API密钥（与后端相同）
EMBED_API_KEY=your-api-key-here
```

### OA系统配置

```bash
# OA系统基础URL
OA_BASE_URL=https://oa.example.com

# OA系统登录URL
OA_LOGIN_URL=https://oa.example.com/login

# OA系统用户名
OA_USERNAME=your-oa-username

# OA系统密码
OA_PASSWORD=your-oa-password
```

**说明：**
- 用于爬取OA系统的通知
- 需要有效的OA账号
- 密码应妥善保管

## 客户端环境变量（OAP-app/.env）

### API配置

```bash
# 后端API基础URL
EXPO_PUBLIC_API_BASE_URL=http://localhost:4420/api
```

**说明：**
- 开发环境：`http://localhost:4420/api`
- 生产环境：`https://your-domain.com/api`
- 必须以`EXPO_PUBLIC_`开头才能在客户端代码中访问

### Expo配置

```bash
# Expo项目ID（自动生成，无需手动设置）
EXPO_PROJECT_ID=your-project-id
```

## 配置最佳实践

### 1. 安全性

- **永远不要**将`.env`文件提交到版本控制系统
- 使用强随机字符串作为密钥
- 生产环境使用环境变量管理服务（如AWS Secrets Manager）
- 定期轮换API密钥和JWT密钥

### 2. 性能优化

- 根据实际负载调整Redis缓存TTL
- 合理设置向量搜索限制，避免全表扫描
- 使用CDN加速静态资源

### 3. 开发环境

```bash
# backend/.env
DATABASE_URL=postgresql://dev:dev@localhost:5432/oap_dev
REDIS_HOST=localhost
REDIS_PORT=6379
AUTH_JWT_SECRET=dev-secret-key
AUTH_REFRESH_HASH_KEY=dev-hash-key
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-4
API_KEY=your-dev-api-key
EMBED_BASE_URL=https://api.openai.com/v1
EMBED_MODEL=text-embedding-3-small
EMBED_API_KEY=your-dev-api-key
EMBED_DIM=1536
CORS_ALLOW_ORIGINS=*
RATE_LIMIT_PER_DAY=1000
RATE_LIMIT_PER_HOUR=100
```

### 4. 生产环境

```bash
# backend/.env
DATABASE_URL=postgresql://prod_user:strong_password@prod-db.example.com:5432/oap_prod
REDIS_HOST=prod-redis.example.com
REDIS_PORT=6379
REDIS_PASSWORD=strong_redis_password
AUTH_JWT_SECRET=<使用32位以上随机字符串>
AUTH_REFRESH_HASH_KEY=<使用32位以上随机字符串>
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-4
API_KEY=<生产环境API密钥>
EMBED_BASE_URL=https://api.openai.com/v1
EMBED_MODEL=text-embedding-3-small
EMBED_API_KEY=<生产环境API密钥>
EMBED_DIM=1536
CORS_ALLOW_ORIGINS=https://your-app.com,https://www.your-app.com
RATE_LIMIT_PER_DAY=100
RATE_LIMIT_PER_HOUR=20
```

## 故障排查

### 数据库连接失败

1. 检查PostgreSQL服务是否运行
2. 验证`DATABASE_URL`格式是否正确
3. 确认数据库用户权限
4. 检查pgvector扩展是否已安装

```sql
-- 检查pgvector扩展
SELECT * FROM pg_extension WHERE extname = 'vector';

-- 安装pgvector扩展
CREATE EXTENSION IF NOT EXISTS vector;
```

### Redis连接失败

1. 检查Redis服务是否运行
2. 验证`REDIS_HOST`和`REDIS_PORT`
3. 确认Redis密码是否正确
4. 检查防火墙设置

### AI服务调用失败

1. 验证API密钥是否有效
2. 检查`AI_BASE_URL`是否正确
3. 确认模型名称是否可用
4. 检查API配额是否用尽

### 向量维度不匹配

如果遇到向量维度错误，检查：

1. `EMBED_DIM`是否与模型实际输出维度一致
2. 数据库中已存储的向量维度是否一致
3. 是否需要重新生成所有向量嵌入

## 环境变量模板

项目提供了环境变量模板文件：

- `backend/env.example` - 后端环境变量模板
- `crawler/env.example` - 爬虫环境变量模板
- `OAP-app/.env.example` - 客户端环境变量模板

使用方法：

```bash
# 复制模板文件
cp backend/env.example backend/.env
cp crawler/env.example crawler/.env
cp OAP-app/.env.example OAP-app/.env

# 编辑配置文件
vim backend/.env