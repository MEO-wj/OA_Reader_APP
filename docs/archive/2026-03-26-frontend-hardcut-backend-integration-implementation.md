# 前端硬切后端联调实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 移除前端无后端测试路径，强制资料、文章通知等新功能直接对接 Go 后端，并在后端启动时执行幂等 migration

**Architecture:** 前端资料域由“本地优先真值”改为“后端真值 + 本地缓存”；Go 后端新增用户资料域和头像上传域，并为文章通知补充增量查询契约；数据库在服务启动前执行版本化 migration

**Tech Stack:** Expo Router, React Native, TypeScript, Go, Gin, GORM, PostgreSQL

---

### Task 1: 盘点并锁定所有需移除的前端模拟路径

**Files:**
- Modify: `OAP-app/services/profile.ts`
- Modify: `OAP-app/app/(tabs)/settings/profile-edit.tsx`
- Modify: `OAP-app/storage/auth-storage.ts`
- Modify: `OAP-app/notifications/notification-task.ts`
- Test: 手动验证资料编辑页、通知设置页

**Step 1: 写出待清理路径清单**

确认以下机制需要被删除或改语义：

- `EXPO_PUBLIC_PROFILE_REMOTE_SYNC`
- 资料保存先写本地再尝试远端
- 头像仅保存在 `avatar_local_uri`
- 资料远端失败时只打印日志不报错

**Step 2: 手动验证当前行为**

Run:

```bash
cd /home/handy/OAP
rg -n "EXPO_PUBLIC_PROFILE_REMOTE_SYNC|avatar_local_uri|Reserved remote sync failed|updateUserProfile\\(" OAP-app
```

Expected: 能看到本地优先与开关路径的引用位置

**Step 3: 记录硬切后的目标语义**

- 资料读取失败就是失败
- 资料保存失败就是失败
- 头像无远端 URL 不算保存成功

**Step 4: 运行前端静态检查基线**

Run:

```bash
cd /home/handy/OAP/OAP-app
npm run lint
```

Expected: 记录现有基线，若已有失败需单独备注

**Step 5: 提交点**

本任务不提交 commit，只记录清理清单

---

### Task 2: 在 Go 后端引入启动时 migration 基础设施

**Files:**
- Create: `backend/internal/migration/migration.go`
- Create: `backend/internal/migration/versions.go`
- Modify: `backend/internal/repository/db.go`
- Modify: `backend/cmd/server/main.go`
- Test: `backend/tests/api_test.go`

**Step 1: 写失败测试或最小验证**

先为 migration 执行入口添加最小验证，至少确保重复执行不会报错，且会创建版本记录表。

可新增测试思路：

```go
func TestRunMigrationsIsIdempotent(t *testing.T) {
    // 初始化测试数据库
    // 连续执行两次 RunMigrations
    // 断言无错误，schema_migrations 存在
}
```

**Step 2: 运行测试确认当前失败**

Run:

```bash
cd /home/handy/OAP/backend
go test ./...
```

Expected: 当前不存在 migration 能力或测试失败

**Step 3: 实现 migration 入口**

实现要求：

- 创建 `schema_migrations`
- 按版本顺序执行
- 跳过已执行版本
- 单个 migration 失败即返回错误

**Step 4: 在服务启动中接入**

调整 `main.go` 启动顺序：

1. Load config
2. Init DB
3. Run migrations
4. Init services/handlers
5. Start server

**Step 5: 运行测试验证**

Run:

```bash
cd /home/handy/OAP/backend
go test ./...
```

Expected: migration 相关测试通过，现有测试不回退

---

### Task 3: 为 users 表增加资料字段 migration

**Files:**
- Modify: `backend/internal/migration/versions.go`
- Modify: `backend/internal/model/user.go`
- Test: `backend/internal/repository/user.go` 对应测试

**Step 1: 写失败测试**

新增测试验证用户模型可承载以下字段：

- `avatar_url`
- `profile_tags`
- `bio`
- `profile_updated_at`
- `is_vip`
- `vip_expired_at`

**Step 2: 运行测试确认失败**

Run:

```bash
cd /home/handy/OAP/backend
go test ./internal/... -run User -v
```

Expected: 当前字段不存在或扫描失败

**Step 3: 写 migration**

迁移内容：

- 增加列
- 设定默认值
- 历史空值回填
- 需要时补索引

建议字段：

```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_tags text[] NOT NULL DEFAULT '{}';
ALTER TABLE users ADD COLUMN IF NOT EXISTS bio text NOT NULL DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_updated_at timestamptz;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_vip boolean NOT NULL DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_expired_at timestamptz;
```

**Step 4: 更新模型**

在 `model.User` 中补齐字段并使用与 PostgreSQL 一致的类型。

**Step 5: 运行测试验证**

Run:

```bash
cd /home/handy/OAP/backend
go test ./...
```

Expected: 模型与迁移兼容

---

### Task 4: 实现用户资料 repository 与 service

**Files:**
- Modify: `backend/internal/repository/user.go`
- Create: `backend/internal/service/profile.go`
- Create: `backend/internal/service/profile_test.go`

**Step 1: 写失败测试**

为以下行为写测试：

- 通过 user id 获取完整资料
- 更新昵称、标签、简介、头像 URL
- 服务端校验非法昵称、标签数量、简介长度

测试示例：

```go
func TestProfileService_UpdateProfile_ValidatesInput(t *testing.T) {
    // display_name 太短
    // profile_tags 超过上限
    // bio 超长
}
```

**Step 2: 运行测试确认失败**

Run:

```bash
cd /home/handy/OAP/backend
go test ./internal/service -run Profile -v
```

Expected: `profile.go` 不存在或测试失败

**Step 3: 实现最小 repository 方法**

至少新增：

- `FindProfileByID`
- `UpdateProfileByID`

**Step 4: 实现 service**

职责：

- DTO 转换
- 输入校验
- 更新时间兜底
- 返回完整资料对象

**Step 5: 运行测试验证**

Run:

```bash
cd /home/handy/OAP/backend
go test ./internal/service -run Profile -v
```

Expected: Profile service 测试通过

---

### Task 5: 实现用户资料 handler 与路由注册

**Files:**
- Create: `backend/internal/handler/profile.go`
- Create: `backend/internal/handler/profile_test.go`
- Modify: `backend/cmd/server/main.go`

**Step 1: 写失败测试**

为以下端点写 handler 测试：

- `GET /api/user/profile`
- `PATCH /api/user/profile`

断言：

- 未认证返回 401
- 合法请求返回 200
- 参数错误返回 400

**Step 2: 运行测试确认失败**

Run:

```bash
cd /home/handy/OAP/backend
go test ./internal/handler -run Profile -v
```

Expected: 路由不存在或 handler 不存在

**Step 3: 实现 handler**

要求：

- 从 JWT 中读取 `user_id`
- 统一错误响应
- PATCH 返回完整资料对象

**Step 4: 注册路由**

在 `main.go` 中新增：

```go
user := r.Group("/api/user")
user.Use(middleware.AuthRequired(cfg.AuthJWTSecret))
{
    user.GET("/profile", profileHandler.GetProfile)
    user.PATCH("/profile", profileHandler.UpdateProfile)
}
```

**Step 5: 运行测试验证**

Run:

```bash
cd /home/handy/OAP/backend
go test ./internal/handler -run Profile -v
```

Expected: Profile handler 测试通过

---

### Task 6: 实现头像上传接口

**Files:**
- Modify: `backend/internal/config/config.go`
- Modify: `backend/cmd/server/main.go`
- Modify: `backend/internal/handler/profile.go`
- Create: `backend/internal/handler/profile_avatar_test.go`

**Step 1: 写失败测试**

覆盖以下场景：

- 缺少 `avatar` 字段返回 400
- 文件类型非法返回 400
- 上传成功返回 `avatar_url`

**Step 2: 运行测试确认失败**

Run:

```bash
cd /home/handy/OAP/backend
go test ./internal/handler -run Avatar -v
```

Expected: 当前上传逻辑不存在

**Step 3: 实现最小上传能力**

第一阶段约束：

- 保存到本地目录，例如 `backend/uploads/avatars/<user-id>/`
- 限制 MIME 类型为图片
- 限制大小
- 返回稳定静态访问路径

**Step 4: 注册静态资源路径**

在 `main.go` 中增加静态目录暴露，例如：

```go
r.Static("/uploads", "./uploads")
```

路径方案需与部署结构一致。

**Step 5: 运行测试验证**

Run:

```bash
cd /home/handy/OAP/backend
go test ./internal/handler -run Avatar -v
```

Expected: 上传测试通过

---

### Task 7: 前端移除资料域 mock / 本地优先逻辑

**Files:**
- Modify: `OAP-app/services/profile.ts`
- Modify: `OAP-app/app/(tabs)/settings/profile-edit.tsx`
- Modify: `OAP-app/hooks/use-user-profile.ts`
- Modify: `OAP-app/storage/auth-storage.ts`

**Step 1: 写失败测试或最小验证清单**

前端当前缺少完整自动化测试时，至少定义以下手动验证：

- 打开资料页必须请求远端
- 后端关闭时资料页必须报错
- 保存资料失败时不得显示成功
- 头像上传失败时不得只保留本地 URI 伪成功

**Step 2: 移除开关**

删除：

```ts
isProfileRemoteSyncEnabled()
```

以及所有条件调用分支。

**Step 3: 调整保存流程**

目标顺序：

1. 若头像变更，先上传头像
2. 调用 `PATCH /user/profile`
3. 以服务端返回对象覆盖本地缓存
4. 成功后返回上一页

失败则中止并提示，不更新本地成功态。

**Step 4: 限制本地字段语义**

`avatar_local_uri` 仅允许作为本次编辑预览态，不允许作为持久化资料真值。

**Step 5: 运行静态检查**

Run:

```bash
cd /home/handy/OAP/OAP-app
npm run lint
```

Expected: 无新增 lint 错误

---

### Task 8: 实现资料页首次拉取远端资料

**Files:**
- Modify: `OAP-app/hooks/use-user-profile.ts`
- Modify: `OAP-app/app/(tabs)/settings/index.tsx`
- Modify: `OAP-app/app/(tabs)/settings/profile-edit.tsx`

**Step 1: 写最小验证**

定义以下行为：

- settings 页面进入后拉取 `/user/profile`
- 拉取成功后刷新缓存
- 拉取失败展示错误态或提示重试

**Step 2: 实现远端加载流程**

建议在资料页聚合逻辑中调用：

```ts
fetchReservedProfile()
```

但函数命名应同步去掉 `Reserved` 语义，改成真实接口命名。

**Step 3: 更新页面表现**

- 初始 loading
- 加载失败错误提示
- 重试按钮或重新进入页面重试

**Step 4: 手动验证**

Run:

```bash
cd /home/handy/OAP/OAP-app
npm run lint
```

Expected: 页面可编译，联调时失败能清晰暴露

**Step 5: 记录风险**

如果 `auth/token` 返回的 `user` 字段仍然缺少资料字段，不阻塞本任务，资料页以独立拉取接口为准。

---

### Task 9: 补齐文章增量通知契约

**Files:**
- Modify: `backend/internal/service/articles.go`
- Modify: `backend/internal/handler/articles.go`
- Modify: `backend/internal/repository/article.go`
- Modify: `backend/internal/model/article.go`
- Test: `backend/internal/handler/articles_test.go`
- Test: `OAP-app/notifications/notification-task.ts`

**Step 1: 写失败测试**

覆盖：

- `since` 参数返回新增文章
- `If-Modified-Since` 命中时返回 304
- 返回结果包含 `created_at`

**Step 2: 运行测试确认失败**

Run:

```bash
cd /home/handy/OAP/backend
go test ./internal/handler -run Articles -v
```

Expected: 当前不支持这些契约

**Step 3: 实现后端契约**

后端要求：

- 解析 `since`
- 计算结果集最后修改时间
- 设置 `Last-Modified`
- 按需返回 304
- DTO 补 `created_at`

**Step 4: 前端通知逻辑清理**

清理前端对增量的猜测逻辑，改成直接消费真实字段。

**Step 5: 运行验证**

Run:

```bash
cd /home/handy/OAP/backend
go test ./...
```

Expected: 文章和通知相关测试通过

---

### Task 10: 全量回归验证

**Files:**
- Verify: `backend/...`
- Verify: `OAP-app/...`

**Step 1: 后端测试**

Run:

```bash
cd /home/handy/OAP/backend
go test ./...
```

Expected: 所有 Go 测试通过

**Step 2: 前端静态检查**

Run:

```bash
cd /home/handy/OAP/OAP-app
npm run lint
```

Expected: lint 通过

**Step 3: 手动联调检查**

手动验证以下链路：

1. 登录
2. 进入设置页拉取资料
3. 编辑昵称/标签/简介并保存
4. 上传头像
5. 重启应用后资料保持一致
6. 打开通知并触发文章轮询

**Step 4: 明确失败处理**

如后端某接口未完成，前端必须直接暴露错误，不新增本地兜底。

**Step 5: 提交点**

按仓库要求，本次不自动 commit。

---

Plan complete and saved to `docs/plans/2026-03-26-frontend-hardcut-backend-integration-implementation.md`. Two execution options:

1. Subagent-Driven (this session) - 我按任务逐步实现、边改边验证
2. Parallel Session (separate) - 另开会话按计划执行

你如果要我继续落代码，我建议直接选第 1 种。
