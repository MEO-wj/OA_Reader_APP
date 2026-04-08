# 前端硬切后端联调设计方案

**日期**: 2026-03-26
**状态**: 已批准
**技术栈**: Expo 54 + React Native + TypeScript + Go + Gin + GORM + PostgreSQL

---

## 1. 背景与目标

最近几次前端提交已经引入了新的用户资料、通知轮询、AI 体验增强等能力，但其中部分能力仍依赖“无后端可运行”的前端本地优先逻辑、预留开关或占位契约。

本次联调的核心目标不是继续补兼容层，而是直接切到真实后端：

- 移除前端模拟实现、占位开关和本地优先成功路径
- 让前端优先暴露真实后端缺口
- 在 Go 后端中补齐真实接口与数据模型
- 在服务启动阶段执行幂等、智能、可前滚的数据库 migration

目标是尽快得到一条真实的前后端链路，而不是继续积累“能跑但不真”的技术债。

---

## 2. 当前问题概览

### 2.1 前端已经存在真实调用点，但后端未完整承接

前端当前已直接依赖以下后端契约：

- `POST /api/auth/token`
- `POST /api/auth/token/refresh`
- `GET /api/articles/today`
- `GET /api/articles/`
- `GET /api/articles/count`
- `GET /api/articles/:id`
- `POST /api/ai/ask`
- `POST /api/ai/clear_memory`
- `GET /api/user/profile`
- `PATCH /api/user/profile`
- `POST /api/user/profile/avatar`

其中最后 3 个接口在当前 Go 后端中尚未注册。

### 2.2 前端仍保留“非真实后端”运行路径

目前前端仍存在以下联调遮蔽问题：

- 个人资料编辑页优先写本地缓存，再按开关决定是否远端同步
- `EXPO_PUBLIC_PROFILE_REMOTE_SYNC=1` 使资料同步成为可选而非默认行为
- 头像本地 URI 可以长期作为有效资料存在，掩盖远端上传缺失
- 通知轮询对文章增量接口做了前端推断，后端真实契约并未完全满足
- 部分失败路径被吞掉，只打印日志，不中断用户流程

### 2.3 Go 后端重构后丢失了历史占位接口

历史 Python 后端分支中曾为资料接口保留 `501` 占位路由，但 Go 重构后这部分未被带入。当前问题不是“占位逻辑待实现”，而是“真实路由不存在”。

---

## 3. 总体方案

本次采用“前端硬切 + 后端补齐 + 启动迁移”的统一方案。

### 3.1 前端策略

前端直接移除 mock / 本地优先 / 占位兼容路径：

- 资料页加载必须请求真实后端
- 资料保存必须先走真实后端，成功后再刷新本地缓存
- 头像必须通过真实上传接口获得 `avatar_url`
- 不再用开关决定是否同步资料
- 通知轮询仅依赖真实文章增量契约
- 所有远端失败必须显式暴露为错误态

### 3.2 后端策略

Go 后端补齐用户资料域、头像上传域和文章增量契约：

- 补 `user/profile` 路由、handler、service、repository
- 扩展 `users` 表承载资料字段
- 为文章增量轮询提供稳定字段和缓存协商
- 在服务启动时自动执行 migration

### 3.3 迁移策略

数据库采用“版本化 migration + 启动执行”的方案：

- migration 幂等
- 失败阻止启动
- 只做前滚，不做自动回滚
- 简单结构变更可由 GORM 辅助，但业务关键变更以显式 SQL 或显式 migration 逻辑为主

这是当前阶段技术债最少的方案。

---

## 4. 后端接口设计

### 4.1 用户资料接口

#### GET `/api/user/profile`

用途：

- 页面进入时拉取真实资料
- 登录后同步用户资料展示

响应结构：

```json
{
  "id": "uuid",
  "username": "20240001",
  "display_name": "张三",
  "roles": [],
  "avatar_url": "https://cdn.example.com/avatar/20240001.jpg",
  "profile_tags": ["计算机", "效率控"],
  "bio": "热爱校园自动化。",
  "profile_updated_at": "2026-03-26T12:00:00Z",
  "is_vip": false,
  "vip_expired_at": null
}
```

要求：

- 必须由 JWT 中的 `user_id` 决定返回对象
- 不允许返回前端本地字段 `avatar_local_uri`

#### PATCH `/api/user/profile`

用途：

- 保存用户昵称、标签、简介、头像 URL

请求体：

```json
{
  "display_name": "张三",
  "profile_tags": ["计算机", "效率控"],
  "bio": "热爱校园自动化。",
  "avatar_url": "https://cdn.example.com/avatar/20240001.jpg",
  "profile_updated_at": "2026-03-26T12:00:00Z"
}
```

约束：

- `display_name` 长度 2-20
- `profile_tags` 最多 5 个，每个 2-10 字
- `bio` 最长 80 字
- `avatar_url` 为后端允许的资源 URL
- 服务端必须重复校验，不信任前端

响应：

- 返回完整资料对象，不返回局部 patch

#### POST `/api/user/profile/avatar`

用途：

- 上传头像并返回可持久化的 `avatar_url`

请求：

- `multipart/form-data`
- 字段名固定为 `avatar`

响应：

```json
{
  "avatar_url": "/uploads/avatars/<user-id>/<file>.jpg"
}
```

第一阶段建议：

- 可先落本地目录并由 Gin 暴露静态文件
- URL 语义要稳定，后续替换对象存储时前端无需改动

---

## 5. 文章增量通知契约

通知模块已经在前端实现，但当前后端契约不完整，需补齐。

### 5.1 GET `/api/articles/today`

新增支持：

- 查询参数 `since`
- 请求头 `If-Modified-Since`
- 响应头 `Last-Modified`

用途：

- 用于 Android 后台任务判断是否有新文章
- 避免每次全量拉取并由前端自行猜测新增

### 5.2 返回字段要求

文章列表需稳定包含：

- `id`
- `title`
- `unit`
- `published_on`
- `created_at`
- `summary`

其中 `created_at` 是通知轮询计算增量的核心字段，必须有稳定且可比较的时间语义。

### 5.3 缓存协商规则

- 如果自上次轮询后没有新文章，优先返回 `304 Not Modified`
- 若有 `since`，则仅返回新增文章
- 若无 `since`，返回当天或最新可用日期的完整列表

---

## 6. 数据模型调整

### 6.1 users 表新增字段

建议新增：

- `avatar_url TEXT NULL`
- `profile_tags TEXT[] NOT NULL DEFAULT '{}'`
- `bio TEXT NOT NULL DEFAULT ''`
- `profile_updated_at TIMESTAMPTZ NULL`
- `is_vip BOOLEAN NOT NULL DEFAULT FALSE`
- `vip_expired_at TIMESTAMPTZ NULL`

### 6.2 字段选择理由

`profile_tags` 推荐使用 `TEXT[]`：

- 当前项目中 `roles` 已使用 `text[]`
- GORM 映射更直接
- 不需要再为 JSONB 实现额外扫描器
- 当前前端没有复杂标签对象结构，数组字符串足够

### 6.3 User 模型扩展

Go `User` 模型需要与接口最小字段集对齐，避免前端继续为“后端字段不存在”做兼容。

---

## 7. Migration 设计

### 7.1 启动顺序

服务启动顺序调整为：

1. 加载配置
2. 连接数据库
3. 执行 migration
4. 初始化 repository / service / handler
5. 注册路由
6. 启动 HTTP 服务

### 7.2 migration 机制要求

必须满足：

- 版本化管理
- 幂等执行
- 已执行版本有记录
- 单个 migration 失败则停止启动
- 不做静默跳过

建议新增：

- `internal/migration/`
- `schema_migrations` 表

### 7.3 推荐实现方式

采用混合方案：

- 简单列新增、简单索引可交给 GORM `AutoMigrate`
- 默认值回填、复杂约束、目录初始化、历史数据修正由显式 migration 管理

不建议只依赖纯 `AutoMigrate`，否则后续字段约束与数据修正难以控制。

---

## 8. 前端清理设计

### 8.1 必须移除的前端机制

- `EXPO_PUBLIC_PROFILE_REMOTE_SYNC`
- 资料保存“先本地成功、后远端失败忽略”的逻辑
- 头像长期依赖 `avatar_local_uri` 的展示语义
- 资料接口保底假装成功的分支
- 依赖本地缓存掩盖服务端失败的初始展示

### 8.2 允许保留的本地能力

仅保留“缓存”而非“真值来源”：

- 登录态 token 存储
- 用户资料远端成功后的本地缓存
- 通知任务本地轮询时间戳

本地缓存只能作为优化，不再作为资料真值。

---

## 9. 分阶段联调顺序

### 阶段一：后端基础能力

- 引入 migration 框架
- 扩展 `users` 表
- 实现 `GET/PATCH /api/user/profile`
- 实现 `POST /api/user/profile/avatar`

### 阶段二：前端硬切资料域

- 删除资料远端同步开关
- 删除本地优先资料保存路径
- 资料页和编辑页直接依赖真实接口
- 暴露真实错误态

### 阶段三：文章通知契约

- `articles/today` 增加 `since` 和缓存协商
- 补稳定 `created_at`
- 前端通知任务改为完全信任后端契约

### 阶段四：统一收尾

- 清理文档里的“预留接口”表述
- 删除无用兼容代码
- 补测试与回归检查

---

## 10. 风险与约束

- 硬切后前端部分页面在联调早期会直接失败，这是预期行为
- 头像上传第一阶段若使用本地磁盘，部署时需保证挂载和静态资源路径一致
- 文章 `created_at` 若历史数据不稳定，需要迁移阶段确认回填策略
- 若前端继续保留本地优先逻辑，会再次遮蔽后端缺口，本方案效果会被削弱

---

## 11. 推荐结论

本次应直接执行“前端硬切真实后端”的方案，不再延续 mock、预留开关和本地优先成功路径。

后端优先补齐用户资料域和启动 migration，再补文章增量通知契约。这样可以最早暴露真实问题，同时保证后续技术债最低。
