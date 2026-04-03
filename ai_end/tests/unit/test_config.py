"""
TDD: 配置模块单元测试

RED 阶段 - 测试先于实现
"""
import os
import pytest


class TestConfig:
    """配置模块测试套件"""

    def test_load_from_env(self, monkeypatch):
        """
        RED #1: 从环境变量加载配置
        Given: 设置了 OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL 环境变量
        When: 调用 Config.load()
        Then: 返回包含这些值的配置对象
        """
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-123")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://test.api.com")
        monkeypatch.setenv("OPENAI_MODEL", "test-model")

        from src.config.settings import Config

        config = Config.load()

        assert config.api_key == "test-key-123"
        assert config.base_url == "https://test.api.com"
        assert config.model == "test-model"

    def test_config_defaults(self, monkeypatch):
        """
        RED #2: 未设置环境变量时使用默认值
        Given: 没有设置相关环境变量
        When: 调用 Config.load()
        Then: 使用预定义的默认值
        """
        # 确保环境变量未设置
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("OPENAI_MODEL", raising=False)

        from src.config.settings import Config

        config = Config.load()

        assert config.api_key == ""
        assert config.base_url == "https://api.openai.com/v1"
        assert config.model == "deepseek-v3.2"

    def test_config_validation(self, monkeypatch):
        """
        RED #3: 无效配置抛出异常
        Given: OPENAI_BASE_URL 不是有效的 URL
        When: 调用 Config.load()
        Then: 抛出 ConfigError 异常
        """
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        monkeypatch.setenv("OPENAI_BASE_URL", "not-a-valid-url")

        from src.config.settings import Config, ConfigError

        with pytest.raises(ConfigError):
            Config.load()

    def test_skills_dir_default(self):
        """
        RED #4: skills_dir 使用默认值
        Given: 没有设置 SKILLS_DIR 环境变量
        When: 访问 config.skills_dir
        Then: 返回 "./skills"
        """
        from src.config.settings import Config

        config = Config.with_defaults()

        assert config.skills_dir == "./skills"

    def test_skills_dir_from_env(self, monkeypatch):
        """
        RED #5: 从环境变量读取 skills_dir
        Given: 设置了 SKILLS_DIR 环境变量
        When: 调用 Config.load()
        Then: 返回指定的目录
        """
        monkeypatch.setenv("SKILLS_DIR", "/custom/skills/path")

        from src.config.settings import Config

        config = Config.load()

        assert config.skills_dir == "/custom/skills/path"

    def test_config_is_dataclass(self):
        """
        RED #6: Config 是不可变的数据类
        Given: Config 对象
        When: 尝试修改属性
        Then: 抛出 FrozenInstanceError
        """
        from src.config.settings import Config

        config = Config.with_defaults()

        with pytest.raises(Exception):  # FrozenInstanceError
            config.api_key = "new-key"

    def test_embedding_config_defaults(self):
        """
        RED #7: embedding 配置使用默认值
        Given: 没有设置 EMBEDDING 相关环境变量
        When: 访问 embedding 配置
        Then: 返回预定义的默认值
        """
        from src.config.settings import Config

        config = Config.with_defaults()

        assert config.embedding_model == "BAAI/bge-m3"
        assert config.embedding_dimensions == 1024

    def test_embedding_config_from_env(self, monkeypatch):
        """
        RED #8: 从环境变量读取 embedding 配置
        Given: 设置了 EMBEDDING_MODEL 和 EMBEDDING_DIMENSIONS 环境变量
        When: 调用 Config.load()
        Then: 返回指定的配置值
        """
        monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-large")
        monkeypatch.setenv("EMBEDDING_DIMENSIONS", "3072")

        from src.config.settings import Config

        config = Config.load()

        assert config.embedding_model == "text-embedding-3-large"
        assert config.embedding_dimensions == 3072

    def test_embedding_api_config_defaults(self):
        """
        RED #9: embedding API 配置使用默认值（None）
        Given: 没有设置 EMBEDDING_API_KEY 和 EMBEDDING_BASE_URL 环境变量
        When: 访问 embedding API 配置
        Then: 返回 None（将使用默认 OpenAI 配置）
        """
        from src.config.settings import Config

        config = Config.with_defaults()

        assert config.embedding_api_key is None
        assert config.embedding_base_url is None

    def test_embedding_api_config_from_env(self, monkeypatch):
        """
        RED #10: 从环境变量读取独立的 embedding API 配置
        Given: 设置了 EMBEDDING_API_KEY 和 EMBEDDING_BASE_URL 环境变量
        When: 调用 Config.load()
        Then: 返回指定的配置值
        """
        monkeypatch.setenv("EMBEDDING_API_KEY", "embedding-key-456")
        monkeypatch.setenv("EMBEDDING_BASE_URL", "https://embedding.api.com")

        from src.config.settings import Config

        config = Config.load()

        assert config.embedding_api_key == "embedding-key-456"
        assert config.embedding_base_url == "https://embedding.api.com"

    def test_embedding_fallback_to_default_config(self, monkeypatch):
        """
        RED #11: 当未设置独立 embedding API 时，回退到默认配置
        Given: 设置了 OPENAI_API_KEY 但未设置 EMBEDDING_API_KEY
        When: 使用 embedding 配置
        Then: 应该使用 OPENAI_API_KEY 作为回退
        """
        monkeypatch.setenv("OPENAI_API_KEY", "default-openai-key")
        monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)

        from src.config.settings import Config

        config = Config.load()

        # embedding_api_key 应该为 None，使用时需要回退
        assert config.embedding_api_key is None
        assert config.api_key == "default-openai-key"
