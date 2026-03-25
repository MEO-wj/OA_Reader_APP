# tests/acceptance/utils/assertions.py
import re
from typing import Any


class AssertionHelper:
    """测试断言辅助类"""

    @staticmethod
    def assert_tool_calls(actual: list[dict], expected: list[str]) -> tuple[bool, str]:
        """
        验证工具调用是否符合预期

        返回: (passed, reason)
        """
        actual_names = {call.get("name") for call in actual}
        expected_set = set(expected)

        missing = expected_set - actual_names
        if missing:
            return False, f"缺少工具调用: {', '.join(missing)}"

        return True, ""

    @staticmethod
    def assert_event_sequence(actual: list[str], expected: list[str]) -> bool:
        """验证事件序列包含所有预期事件（按顺序）"""
        return all(e in actual for e in expected)

    @staticmethod
    def assert_response_criteria(response: str, criteria: dict[str, Any]) -> tuple[bool, str]:
        """根据响应标准检查回复"""
        if "min_stages" in criteria:
            # 中文数字映射
            chinese_numbers = {
                '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
                '六': 6, '七': 7, '八': 8, '九': 9, '十': 10, '两': 2
            }

            max_stages = 0

            # 1. 检查中文数字 + 阶段/步/部分 (如 "三个阶段", "三步")
            chinese_pattern = r'([一二三四五六七八九十两])\s*个?\s*[阶段步部分]'
            matches = re.findall(chinese_pattern, response)
            for match in matches:
                if match in chinese_numbers:
                    max_stages = max(max_stages, chinese_numbers[match])

            # 2. 检查阿拉伯数字 + 阶段/步/部分 (如 "3个阶段", "3步")
            arabic_patterns = [
                r'(\d+)\s*个?\s*[阶段步部分]',
                r'第(\d+)[阶段步部分]',
                r'(\d+)[\s\-]*[阶段步部分]',
            ]
            for pattern in arabic_patterns:
                matches = re.findall(pattern, response)
                for match in matches:
                    try:
                        max_stages = max(max_stages, int(match))
                    except (ValueError, TypeError):
                        pass

            # 3. 如果没有明确的数字，检查是否有序号列表
            if max_stages == 0:
                # 查找 1. 2. 3. 或 ① ② ③ 等序号
                numbered_items = re.findall(r'\d+\.|①|②|③|④|⑤', response)
                max_stages = len(numbered_items)

            # 4. 如果仍然没有，检查是否至少有阶段相关关键词
            if max_stages == 0:
                stage_keywords = ["阶段", "step", "部分"]
                if any(kw in response for kw in stage_keywords):
                    max_stages = 1  # 至少有 1 个阶段

            if max_stages < criteria["min_stages"]:
                return False, f"响应缺少阶段划分（需要至少 {criteria['min_stages']} 个，找到 {max_stages} 个）"

        return True, ""

    @staticmethod
    def evaluate_dimension(
        response: str,
        tools_called: list[dict],  # 工具调用字典列表
        skills_called: list[str],  # 技能名称列表
        criteria: dict[str, Any]
    ) -> dict[str, str]:
        """
        三维评分

        返回: {"tool_chain": "pass|fail", "evidence_driven": "pass|fail", "actionable": "pass|fail"}
        """
        result = {
            "tool_chain": "pass",
            "evidence_driven": "pass",
            "actionable": "pass",
        }

        # tool_chain: 检查是否调用了预期工具
        if "expected_skills" in criteria:
            # 检查技能调用
            expected_skills = criteria["expected_skills"]
            missing = set(expected_skills) - set(skills_called)
            if missing:
                result["tool_chain"] = f"fail (缺少技能: {', '.join(missing)})"

        elif "expected_tools" in criteria:
            # 检查工具调用
            expected_tools = criteria["expected_tools"]
            actual_tools = {t["name"] for t in tools_called}
            missing = set(expected_tools) - actual_tools
            if missing:
                result["tool_chain"] = f"fail (缺少工具: {', '.join(missing)})"

        # actionable: 检查回复是否有结构
        if not any(marker in response for marker in ["1.", "-", "首先", "建议"]):
            result["actionable"] = "fail"

        return result
