"""用户资料模板注入测试"""
import pytest
from src.chat.prompts_runtime import build_user_profile_section


class TestUserProfileSection:
    def test_full_profile(self):
        result = build_user_profile_section(
            display_name="张三",
            profile_tags=["计算机", "夜猫子"],
            bio="计算机学院大三学生",
        )
        assert "【用户资料】" in result
        assert "张三" in result
        assert "计算机" in result
        assert "夜猫子" in result
        assert "大三学生" in result

    def test_empty_profile_returns_empty(self):
        result = build_user_profile_section(
            display_name=None,
            profile_tags=None,
            bio=None,
        )
        assert result == ""

    def test_partial_profile_name_only(self):
        result = build_user_profile_section(display_name="李四")
        assert "李四" in result
        assert "兴趣标签" not in result

    def test_partial_profile_tags_only(self):
        result = build_user_profile_section(
            profile_tags=["摄影", "阅读"],
        )
        assert "摄影" in result
        assert "阅读" in result
        assert "昵称" not in result

    def test_empty_tags_list_returns_empty(self):
        result = build_user_profile_section(
            display_name="测试",
            profile_tags=[],
        )
        assert "兴趣标签" not in result
