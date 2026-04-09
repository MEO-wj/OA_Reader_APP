"""TOOLS.md 参数契约测试

验证 search_articles 工具定义的参数契约，
确保日期范围参数存在且格式说明正确。
"""
from pathlib import Path

import yaml


# TOOLS.md 路径：从 tests/unit/ 上溯到 ai_end/ 再进入 skills/
TOOLS_PATH = Path(__file__).parent.parent.parent / "skills" / "article-retrieval" / "TOOLS.md"


def _load_tools_definition():
    """加载并解析 TOOLS.md 中的 YAML 定义。"""
    text = TOOLS_PATH.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    return data


def _find_tool(tools_data, name: str):
    """从 tools 列表中按名称查找工具定义。"""
    for tool in tools_data.get("tools", []):
        if tool.get("name") == name:
            return tool
    return None


class TestSearchArticlesContract:
    """search_articles 工具参数契约测试"""

    def test_start_date_exists(self):
        """start_date 参数应存在。"""
        text = TOOLS_PATH.read_text(encoding="utf-8")
        assert "start_date" in text

    def test_end_date_exists(self):
        """end_date 参数应存在。"""
        text = TOOLS_PATH.read_text(encoding="utf-8")
        assert "end_date" in text

    def test_date_format_description_contains_yyyy_mm_dd(self):
        """日期参数描述应包含 YYYY-MM-DD 格式说明。"""
        text = TOOLS_PATH.read_text(encoding="utf-8")
        assert "YYYY-MM-DD" in text

    def test_query_is_not_required(self):
        """query 参数不应在 required 列表中。"""
        data = _load_tools_definition()
        tool = _find_tool(data, "search_articles")
        assert tool is not None, "search_articles 工具定义未找到"

        required = tool.get("parameters", {}).get("required", [])
        assert "query" not in required, (
            f"query 不应为 required 参数，当前 required={required}"
        )

    def test_start_and_end_date_in_properties(self):
        """start_date 和 end_date 应出现在 properties 中。"""
        data = _load_tools_definition()
        tool = _find_tool(data, "search_articles")
        assert tool is not None

        props = tool["parameters"]["properties"]
        assert "start_date" in props, "缺少 start_date 属性"
        assert "end_date" in props, "缺少 end_date 属性"

    def test_date_params_type_is_string(self):
        """日期参数类型应为 string。"""
        data = _load_tools_definition()
        tool = _find_tool(data, "search_articles")

        props = tool["parameters"]["properties"]
        assert props["start_date"]["type"] == "string"
        assert props["end_date"]["type"] == "string"

    def test_query_description_mentions_optional(self):
        """query 描述应说明它可以被省略（用于纯日期查询）。"""
        data = _load_tools_definition()
        tool = _find_tool(data, "search_articles")
        query_desc = tool["parameters"]["properties"]["query"]["description"].lower()
        # 描述中应包含提示 query 可为空/可选的措辞
        assert any(
            kw in query_desc for kw in ["可选", "可选的", "可省略", "可以为空", "optional", "日期"]
        ), f"query 描述未说明可选性: {query_desc}"
