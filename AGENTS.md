# Repository Guidelines
##  TOP RULES
!!!回复请使用中文!!!
## 工作原则
- **明确需求**: 用户表达模糊时，主AI必须用多轮提问澄清，可质疑思路并提出更优解。
- **语义理解**:
- 外部检索：优先使用仓库搜索MCP；
- 引用资料必须写明来源与用途，保持可追溯。
- **诉诸现有方案**: 必须首先使用工具检索官方 / 社区方案，优先复用现有方案。
## 架构优先级
标准化、复用官方 SDK / 社区成熟方案 > 常规搜索 > 本地资料。
必须首先使用工具检索官方/社区方案，禁止无参考自研（除非已有方案无法满足需求且获特批）。
引入外部能力必须确认兼容并写明复用指引。
旧有自研实现需规划替换或下线。
## 代码质量标准
### 注释要求
- **简体中文，UTF-8（无 BOM）**
- 解释意图、约束、行为。
- 禁止写“修改说明式注释”。
- 对复杂依赖必须写明设计理由。
### 设计原则
- 遵循 SOLID、DRY、关注点分离。
- 依赖倒置、接口隔离优先。
- 复用原则：严格优先使用项目现有的组件、工具类和架构模式。
  - 注意：由于你可能无法读取全量代码，如果你推测可能存在相关组件但不确定位置，请先询问我，而不是直接制造重复轮子。
### 实现标准
- 禁止占位符或未完成实现（除非用户要求）。
- 必须删除过时代码。
- 破坏性改动无需兼容，但需给出迁移或回滚方案。
- 拒绝一切 CI、远程流水线或人工外包验证，所有验证均由本地 AI 自动执行。
## 开发哲学
- 渐进式、小步交付、每次可编译可验证。
- 简单优先、拒绝炫技。
- 风格、命名、格式必须与现有保持一致。
- 有额外解释代表过于复杂，应继续简化。
### 简单性定义
- 每个函数或类建议仅承担单一责任
- 禁止过早抽象；重复出现三次以上再考虑通用化
- 禁止使用"聪明"技巧，以可读性为先
- 如果需要额外解释，说明实现仍然过于复杂，应继续简化
## Project Structure
TODO：放一个项目结构树
## Common Commands
TODO：放一些可能需要用到的命令
    
## Project Structure & Module Organization
This repository is a multi-module project:
- `OAP-app/`: Expo React Native client. Screens live in `OAP-app/app/`, shared UI in `OAP-app/components/`, hooks in `OAP-app/hooks/`, assets in `OAP-app/assets/`.
- `backend/`: Flask API service. Entry point is `backend/app.py`, routes in `backend/routes/`, data access in `backend/repository/`, domain logic in `backend/services/`.
- `crawler/`: Data ingestion and summarization pipeline. Main runner is `crawler/main.py`.
- `docs/`: API docs and project notes (e.g., `docs/api_documentation.md`).

## Build, Test, and Development Commands
- `cd OAP-app && npm install && npm run start`: start Expo dev server (client).
- `cd OAP-app && npm run android|ios|web`: platform-specific Expo launches.
- `cd OAP-app && npm run lint`: run ESLint for the app.
- `python backend/app.py`: run Flask API locally (configure `backend/env.example`).
- `python crawler/main.py`: run crawler locally (configure `crawler/env.example`).
Note: `crawler/run.sh` is environment-specific; prefer direct `python` or `uv run`.

## Coding Style & Naming Conventions
- TypeScript/React: follow existing file-based routing in `OAP-app/app/` and component naming in `PascalCase` (e.g., `ArticleCard`).
- Python: follow 4-space indentation and module organization in `backend/` and `crawler/`.
- Linting: Expo app uses `eslint-config-expo` via `npm run lint`. No formatter is enforced for Python; keep style consistent with nearby files.

## Testing Guidelines
- No dedicated test suites are present in the repo.
- If adding backend tests, use `pytest` and place files under `backend/tests/` (example command in docs: `uv run pytest`).
- For app tests, add a clear runner command and document it in this file.

## Commit & Pull Request Guidelines
- Recent commit messages are short and action-focused, often in Chinese (e.g., `fix：修复对话框被遮挡`) and sometimes include a scope like `deploy(android): ...`. Follow this style for consistency.
- PRs should include: a clear description, linked issues if applicable, and screenshots for UI changes (especially under `OAP-app/`).
- Note any new env vars or config changes in the PR description.

## Security & Configuration Tips
- Use the provided `env.example` files in `backend/` and `crawler/`. For the app, set `EXPO_PUBLIC_API_BASE_URL` via `.env` or EAS build envs.
- Do not commit secrets or local credentials.
