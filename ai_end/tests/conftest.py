"""
Pytest 配置文件
"""
import pytest


def pytest_configure(config):
    """Pytest 初始化配置"""
    import sys
    from pathlib import Path

    # 添加项目根目录到 Python path（src 的父目录）
    root_path = Path(__file__).parent.parent
    src_path = root_path / "src"
    if src_path.exists():
        sys.path.insert(0, str(root_path))


# 配置 pytest-asyncio
pytest_plugins = ("pytest_asyncio",)

# 设置 asyncio 模式为 auto
pytest_asyncio_mode = "auto"


@pytest.fixture
def sample_skill_content():
    """示例 SKILL.md 内容"""
    return """---
name: test-skill
description: 测试技能
verification_token: TEST-TOKEN-123
---

# 测试技能内容

这是一个测试技能。
"""


@pytest.fixture
def sample_skill_without_yaml():
    """无 YAML front matter 的技能内容"""
    return """# 简单技能

这是没有 front matter 的简单技能。
"""


@pytest.fixture
def mock_skills_dir(tmp_path):
    """创建临时技能目录"""
    skill_dir = tmp_path / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)

    (skill_dir / "SKILL.md").write_text("""---
name: test-skill
description: 测试技能
verification_token: MOCK-TOKEN-456
---

# 测试技能
""", encoding="utf-8")

    return tmp_path / "skills"
