# Docker Compose Env Layering Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 支持同机并行部署 prod/dev 两套 OA-Reader（不同目录），通过 env 文件控制端口和关键配置，降低配置漂移。

**Architecture:** 保留单一 `docker-compose.yml` 作为唯一编排源；通过 `--env-file` 注入不同环境变量；通过 `-p` 项目名隔离资源；去除固定 `container_name` 防止冲突；采用 `common + env-specific` 的变量分层模板。

**Tech Stack:** Docker Compose, Bash, dotenv

---

### Task 1: 配置回归测试（TDD Red）

**Files:**
- Create: `scripts/test-compose-env.sh`

1. 写测试脚本，校验 compose 是否移除 `container_name`、端口是否变量化、是否存在 `env/dev.env.example` 与 `env/prod.env.example`。
2. 运行脚本，预期失败（当前仓库尚未完成这些改造）。

### Task 2: Compose 与 env 分层改造（TDD Green）

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Create: `env/common.env.example`
- Create: `env/dev.env.example`
- Create: `env/prod.env.example`
- Create: `scripts/compose-up.sh`
- Create: `scripts/compose-down.sh`

1. 最小化修改 compose，实现端口变量化、去除固定容器名、卷名前缀变量化。
2. 提供分层 env 样例并文档化命名规范。
3. 提供统一启动/停止脚本以减少人为差异。

### Task 3: 验证与使用示例

**Files:**
- Modify: `README.md`

1. 再次运行测试脚本，确认通过。
2. 更新 README 的部署示例（prod/dev 并行）。
