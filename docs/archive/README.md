# 文档归档说明

本目录存放已完成或已废弃的设计/实现计划文档。

## 归档原因分类

### 已完成的功能实现
| 文档 | 完成内容 |
|------|----------|
| `2026-03-15-ai-endpoint-separation-*.md` | AI 服务从 backend 抽离为独立的 ai_end |
| `2026-03-15-redis-removal-*.md` | 移除 Redis 依赖，改为直接查询数据库 |
| `2026-03-19-backend-go-refactor-*.md` | Python Flask 后端重构为 Go + Gin |
| `2026-03-19-crawler-transaction-*.md` | 爬虫数据流水线事务化 |
| `2026-03-23-user-profile-personalization-*.md` | 个人中心个性化资料功能 |
| `2026-03-26-frontend-hardcut-backend-integration-*.md` | 前端硬切后端联调 |
| `2026-03-26-backend-review-fixes-implementation.md` | 后端评审修复（配置加载、头像URL、迁移事务、容器持久化）|
| `2026-03-27-user-vip-column-mapping-fix.md` | VIP 字段名映射修复 |

### 已废弃的技术方案
| 文档 | 废弃原因 |
|------|----------|
| `redis_cache_strategy.md` | 项目已移除 Redis，改用直接查询数据库 |

## 当前有效文档

主文档目录 (`docs/`) 下的有效文档：

- `architecture.md` - 项目架构文档（保持更新）
- `deployment.md` - 部署指南（需更新为 Go 后端）
- `configuration.md` - 配置说明（需移除 Redis 相关内容）
- `api_documentation.md` - API 文档（需更新技术栈描述）
- `backfill_deployment.md` - 历史数据回填部署指南
- `eas_build.md` - EAS 构建指南
- `web-spa-rewrite.md` - Web SPA 路由重写
- `profile_personalization_api.md` - 个人资料 API 文档
- `development_plan.md` - 开发计划（需更新架构描述）
- `workflow_analysis.md` - 工作流程分析（需更新）

---

*归档时间: 2026-03-27*
