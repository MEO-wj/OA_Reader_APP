# CLAUDE.md

此文件为 Claude Code (claude.ai/code) 提供在此代码库中工作的指导。

## Top Rules
!!!回复使用中文!!!
使用superpower skill指导开发
使用TDD开发模式
优先复用项目中已有的组件
除非我明确要你帮我 git commit 其他情况一律不许commit
如果存在多个方案优先输出未来技术债最少的方案


## 项目概述

通用 AI Agent 后端 - 基于技能系统的 CLI 聊天应用，使用 OpenAI Function Calling 技术动态调用技能。

### 核心特性

- **技能系统**: 从 `skills/` 目录动态加载技能定义 (SKILL.md)
- **验证暗号**: 每个技能包含唯一暗号，用于验证 AI 真实使用了技能
- **可视化输出**: 终端彩色输出，显示技能加载、工具调用等过程
- **分层架构**: 代码按职责分层 (config/core/ui/chat)

## 架构

```
src/
├── config/          # 配置管理
│   └── settings.py       # 从环境变量加载配置，使用 dataclass
├── core/            # 核心业务逻辑
│   ├── skill_parser.py   # 解析 SKILL.md (YAML front matter + 内容)
│   └── skill_system.py   # 扫描技能目录，构建 OpenAI tools 定义
├── ui/              # 用户界面
│   └── console.py        # 终端彩色输出和打印函数
└── chat/            # 聊天功能
    ├── client.py          # ChatClient 类，主聊天逻辑
    └── handlers.py        # 工具调用处理函数

main.py                 # 入口，使用上述模块
```

### 技能系统工作流

1. **扫描**: SkillSystem 扫描 `skills/` 下的所有子目录
2. **解析**: 每个子目录的 `SKILL.md` 由 SkillParser 解析
3. **工具定义**: 技能信息转换为 OpenAI Function Calling 格式
4. **调用**: AI 决定调用技能时，返回对应技能内容
5. **验证**: 检查 AI 回复是否包含技能的验证暗号

## 常用命令

### 构建与测试

```bash
# 安装依赖（使用 uv）
uv pip install -e ".[dev]"

# 运行所有测试
uv run pytest tests/ -v

# 运行特定测试
uv run pytest tests/unit/test_skill_system.py -v

# 测试覆盖率
uv run pytest tests/ --cov=src --cov-report=term
```

### 运行程序

```bash
# 或使用 uv
uv run main.py
```

### 开发模式

- **TDD**: 所有新功能先写测试，再实现代码
- **分层**: 每个模块职责单一，高内聚低耦合
- **类型提示**: 使用 Python 3.11+ 类型标注

## 添加新技能

1. 在 `skills/` 下创建新目录，如 `skills/new-skill/`
2. 创建 `SKILL.md` 文件，格式：

```markdown
---
name: new-skill
description: 技能描述
verification_token: UNIQUE-TOKEN-123
---

# 技能内容

详细说明技能的使用场景和指令。
```

3. 重启程序，技能会自动被加载

## 技能 SKILL.md 格式

每个技能目录包含一个 `SKILL.md` 文件，使用 YAML front matter 定义元数据：

```yaml
---
name: skill-name              # 技能唯一标识
description: 技能描述         # 简短描述
verification_token: TOKEN-XYZ    # 验证暗号（可选）
---
```

## 环境变量

| 变量 | 说明 | 默认值 |
|-------|------|--------|
| OPENAI_API_KEY | OpenAI API 密钥 | (必需) |
| OPENAI_BASE_URL | API 基础 URL | https://api.openai.com/v1 |
| OPENAI_MODEL | 使用的模型 | gpt-4 |
| SKILLS_DIR | 技能目录 | ./skills |
| RERANK_BASE_URL | Rerank API 地址（为空则继承 OPENAI_BASE_URL） | |
| RERANK_MODEL | Rerank 模型名称 | BAAI/bge-reranker-v2-m3 |
| RERANK_MAX_CANDIDATES | Rerank 最大候选数 | 40 |

## 特殊命令

- `skills` 或 `list` - 列出所有可用技能
- `verify <skill_name>` - 显示特定技能的验证暗号
- `quit`, `exit`, `q` - 退出程序

## 注意事项

- **所有 Python 脚本请使用 uv 运行**
- **回复请使用中文**
- **不包含敏感信息** (API keys, tokens) 在代码或提交中

## 检索系统架构（三层策略）

1. **Layer 1: EBD 向量搜索** - 语义召回 top-20
2. **Layer 2: 关键词模糊搜索** - 精确匹配召回 top-20
3. **Layer 3: Rerank 重排序** - 使用 bge-reranker-v2-m3 模型重排序，返回 top-k

## grep_document 增强功能

新增搜索模式：
- `mode="regex"`: 正则表达式匹配
- `mode="line_range"`: 精确行范围
- `context_lines`: 上下文控制
- `grep_documents()`: 跨文档搜索

返回格式统一：
```python
{
    "status": "success" | "not_found" | "error",
    "data": {...},
    "metadata": {...}
}
```

## 并发治理与生命周期

- 采用**分层队列**而非单全局队列：`llm` 与 `embedding` 分 lane 控制并发。
- 并发参数（默认）：
  - `LLM 并发`: 2
  - `Embedding 并发`: 6
  - `搜索重试次数`: 2（总 3 次尝试）
  - `重试退避`: 50ms
- 关闭顺序：`close_clients` → `close_resources` → `close_pool` → `shutdown_tool_loop`
- 常见排查命令：
  - `uv run pytest tests/integration/test_concurrency_regression.py -v`
  - `uv run pytest tests/unit/test_document_retrieval.py tests/unit/test_chat_client.py tests/unit/test_db.py -v`

---

## 开发经验总结

### read_reference 功能 (2026-02)

**问题**：AI 调用技能时，只能看到 SKILL.md 的指令内容，无法直接访问技能目录下的参考资料（references/）。

**解决方案**：
1. 新增 `read_reference` 工具，支持按需读取指定技能的 reference 文件
2. 修改系统提示词，明确调用顺序：先调用技能 → 再根据需要使用 read_reference
3. 添加 API 错误处理，当 API 返回空响应时显示友好提示

**关键代码位置**：
- `src/core/skill_system.py::read_reference()` - 读取 reference 文件
- `src/core/skill_system.py::build_tools_definition()` - 添加 read_reference 工具定义
- `src/chat/handlers.py::handle_tool_calls()` - 处理 read_reference 工具调用
- `src/chat/client.py::chat()` - API 错误处理和调试日志

**使用流程**：
```
用户提问 → AI 调用技能（获取 SKILL.md）→ AI 看到 references 路径
→ AI 调用 read_reference（读取具体文件）→ AI 基于文件内容回复
```

**测试覆盖**：
- `tests/unit/test_skill_system.py` - read_reference 功能测试
- `tests/unit/test_handlers.py` - 工具调用处理测试
- `tests/unit/test_chat_client.py` - API 错误处理测试

**经验教训**：
1. 工具描述必须清晰明确，避免 AI 误用（如直接调用 read_reference 而不先调用技能）
2. API 可能返回空响应，需要添加错误处理
3. 详细的调试日志有助于定位问题
4. 遵循 TDD 原则，先写测试再实现代码
