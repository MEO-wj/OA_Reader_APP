# Backend Review Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复代码评审指出的四个后端问题，确保 Docker 部署可启动、头像 URL 可被原生端使用、迁移真正运行在事务中、上传文件在容器重建后仍然存在。

**Architecture:** 配置层改为“环境变量优先，`.env` 可选补充”；头像上传和资料读取统一通过公共基地址生成绝对 URL，但数据库继续保存相对上传路径；迁移层显式把 `*gorm.DB` 事务句柄传入每个版本函数，杜绝外层 `db` 泄漏；Compose 为 `/app/uploads` 提供命名卷，并在镜像中预创建可写目录。

**Tech Stack:** Go, Gin, Gorm, Viper, Docker Compose

---

### Task 1: 配置加载回归测试

**Files:**
- Modify: `backend/internal/config/config.go`
- Create: `backend/internal/config/config_test.go`

**Step 1: Write the failing test**

写测试覆盖：
- `.env` 不存在时，环境变量仍可完成配置加载
- `CORS_ALLOW_ORIGINS` 能从环境变量解析为切片

**Step 2: Run test to verify it fails**

Run: `go test ./internal/config -run TestLoad -count=1`
Expected: FAIL，因为当前实现强依赖 `.env`

**Step 3: Write minimal implementation**

在 `Load` 中：
- 仅在配置文件存在时读取 `.env`
- 始终启用环境变量覆盖
- 配置 `CORS_ALLOW_ORIGINS` 的分隔解析

**Step 4: Run test to verify it passes**

Run: `go test ./internal/config -run TestLoad -count=1`
Expected: PASS

### Task 2: 头像绝对 URL 回归测试

**Files:**
- Modify: `backend/internal/handler/profile.go`
- Modify: `backend/internal/handler/profile_avatar_test.go`
- Modify: `backend/internal/handler/profile_test.go`

**Step 1: Write the failing test**

写测试覆盖：
- 上传头像接口返回绝对 URL
- 资料读取接口在存量相对路径场景下返回绝对 URL

**Step 2: Run test to verify it fails**

Run: `go test ./internal/handler -run 'TestUploadAvatar_ReturnsAvatarURL|TestGetProfile' -count=1`
Expected: FAIL，因为当前仅返回 `/uploads/...`

**Step 3: Write minimal implementation**

在 handler 中新增 URL 构造 helper：
- 优先使用 `PUBLIC_BASE_URL`
- 回退到请求头推导绝对地址
- 仅读取/响应时拼接绝对 URL，不把 host 写回数据库

**Step 4: Run test to verify it passes**

Run: `go test ./internal/handler -run 'TestUploadAvatar_ReturnsAvatarURL|TestGetProfile' -count=1`
Expected: PASS

### Task 3: 迁移事务回归测试

**Files:**
- Modify: `backend/internal/migration/migration.go`
- Modify: `backend/internal/migration/versions.go`
- Modify: `backend/internal/migration/migration_test.go`

**Step 1: Write the failing test**

写测试覆盖：
- `Apply` 必须把事务句柄传给 `Up`
- 若记录 `schema_migrations` 失败，迁移 SQL 不应逃逸到事务外

**Step 2: Run test to verify it fails**

Run: `go test ./internal/migration -count=1`
Expected: FAIL，因为当前 `Up` 不接收 `tx`

**Step 3: Write minimal implementation**

调整迁移接口签名并把默认版本全部切到 `tx` 执行。

**Step 4: Run test to verify it passes**

Run: `go test ./internal/migration -count=1`
Expected: PASS

### Task 4: 容器上传目录持久化

**Files:**
- Modify: `backend/Dockerfile`
- Modify: `docker-compose.yml`

**Step 1: Write the failing test**

这里不引入集成脚本，使用配置层面的最小可验证变更：
- Compose 挂载 `/app/uploads`
- 镜像预创建 `/app/uploads` 并赋权给 `appuser`

**Step 2: Run targeted verification**

Run: `rg -n '/app/uploads|backend_uploads|mkdir -p /app/uploads|chown .* /app/uploads' backend/Dockerfile docker-compose.yml`
Expected: 变更前缺少命中

**Step 3: Write minimal implementation**

为 backend service 添加命名卷，并确保镜像运行用户有写权限。

**Step 4: Run targeted verification**

Run: `rg -n '/app/uploads|backend_uploads|mkdir -p /app/uploads|chown .* /app/uploads' backend/Dockerfile docker-compose.yml`
Expected: 命中对应配置

### Task 5: 最终验证

**Files:**
- Modify: `backend/cmd/server/main.go`

**Step 1: Run focused tests**

Run:
- `go test ./internal/config -count=1`
- `go test ./internal/handler -count=1`
- `go test ./internal/migration -count=1`

**Step 2: Run package-level regression check**

Run: `go test ./...`
Expected: 全部通过；若已有无关失败，记录实际失败项并说明未由本次改动引入。
