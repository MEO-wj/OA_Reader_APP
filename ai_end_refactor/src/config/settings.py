"""
配置管理模块 - 从环境变量加载配置

TDD GREEN 阶段：编写最小代码通过测试
"""
import os
from dataclasses import dataclass, field
from typing import ClassVar
from dotenv import load_dotenv

# 确保 .env 被加载
load_dotenv()


class ConfigError(Exception):
    """配置错误异常"""
    pass


@dataclass(frozen=True)
class Config:
    """
    配置数据类

    从环境变量读取配置，支持默认值和验证
    """
    # 默认值（类变量）
    DEFAULT_BASE_URL: ClassVar[str] = "https://api.openai.com/v1"
    DEFAULT_MODEL: ClassVar[str] = "deepseek-v3.2"
    DEFAULT_SKILLS_DIR: ClassVar[str] = "./skills"
    DEFAULT_EMBEDDING_MODEL: ClassVar[str] = "BAAI/bge-m3"
    DEFAULT_EMBEDDING_DIMENSIONS: ClassVar[int] = 1024
    DEFAULT_RERANK_MODEL: ClassVar[str] = "BAAI/bge-reranker-v2-m3"
    DEFAULT_RERANK_MAX_CANDIDATES: ClassVar[int] = 40
    DEFAULT_RERANK_TIMEOUT: ClassVar[float] = 60.0
    DEFAULT_EMBEDDING_TIMEOUT: ClassVar[float] = 30.0  # Embedding 请求超时（秒）
    DEFAULT_LLM_TIMEOUT: ClassVar[float] = 120.0  # LLM 请求超时（秒）
    DEFAULT_LLM_MAX_TOKENS: ClassVar[int] = 1500  # LLM 最大 token 数
    DEFAULT_LLM_TEMPERATURE: ClassVar[float] = 0.1  # LLM 温度参数

    # 配置字段
    api_key: str
    base_url: str
    model: str
    skills_dir: str = field(default_factory=lambda: Config.DEFAULT_SKILLS_DIR)
    # 数据库配置
    db_host: str | None = field(default=None)
    db_port: int | None = field(default=None)
    db_user: str | None = field(default=None)
    db_password: str | None = field(default=None)
    db_name: str | None = field(default=None)
    # Embedding 配置
    embedding_model: str = field(default_factory=lambda: Config.DEFAULT_EMBEDDING_MODEL)
    embedding_dimensions: int = field(default_factory=lambda: Config.DEFAULT_EMBEDDING_DIMENSIONS)
    # 如果使用不同的 embedding API（例如 bge-m3 模型）
    embedding_api_key: str | None = field(default=None)
    embedding_base_url: str | None = field(default=None)
    # Rerank 配置
    rerank_model: str = field(default_factory=lambda: Config.DEFAULT_RERANK_MODEL)
    rerank_max_candidates: int = field(default_factory=lambda: Config.DEFAULT_RERANK_MAX_CANDIDATES)
    rerank_timeout: float = field(default_factory=lambda: Config.DEFAULT_RERANK_TIMEOUT)
    rerank_base_url: str | None = field(default=None)
    rerank_api_key: str | None = field(default=None)
    # LLM 和 Embedding 超时配置
    llm_timeout: float = field(default_factory=lambda: Config.DEFAULT_LLM_TIMEOUT)
    embedding_timeout: float = field(default_factory=lambda: Config.DEFAULT_EMBEDDING_TIMEOUT)
    # LLM 生成参数
    llm_max_tokens: int = field(default_factory=lambda: Config.DEFAULT_LLM_MAX_TOKENS)
    llm_temperature: float = field(default_factory=lambda: Config.DEFAULT_LLM_TEMPERATURE)

    @property
    def effective_rerank_base_url(self) -> str:
        """获取有效的 rerank base URL"""
        return self.rerank_base_url or self.base_url

    @classmethod
    def with_defaults(cls) -> "Config":
        """
        创建使用默认值的配置（不读取环境变量）

        Returns:
            使用所有默认值的 Config 实例
        """
        return cls(
            api_key="",
            base_url=cls.DEFAULT_BASE_URL,
            model=cls.DEFAULT_MODEL,
            skills_dir=cls.DEFAULT_SKILLS_DIR,
            db_host=None,
            db_port=None,
            db_user=None,
            db_password=None,
            db_name=None,
            embedding_model=cls.DEFAULT_EMBEDDING_MODEL,
            embedding_dimensions=cls.DEFAULT_EMBEDDING_DIMENSIONS,
            embedding_api_key=None,
            embedding_base_url=None,
            rerank_model=cls.DEFAULT_RERANK_MODEL,
            rerank_max_candidates=cls.DEFAULT_RERANK_MAX_CANDIDATES,
            rerank_timeout=cls.DEFAULT_RERANK_TIMEOUT,
            rerank_base_url=None,
            rerank_api_key=None,
            llm_timeout=cls.DEFAULT_LLM_TIMEOUT,
            embedding_timeout=cls.DEFAULT_EMBEDDING_TIMEOUT,
            llm_max_tokens=cls.DEFAULT_LLM_MAX_TOKENS,
            llm_temperature=cls.DEFAULT_LLM_TEMPERATURE,
        )

    @classmethod
    def load(cls) -> "Config":
        """
        从环境变量加载配置

        Returns:
            Config 实例

        Raises:
            ConfigError: 配置验证失败时
        """
        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_BASE_URL", cls.DEFAULT_BASE_URL)
        model = os.getenv("OPENAI_MODEL", cls.DEFAULT_MODEL)
        skills_dir = os.getenv("SKILLS_DIR", cls.DEFAULT_SKILLS_DIR)

        # 数据库环境变量
        db_host = os.getenv("DB_HOST")
        db_port_str = os.getenv("DB_PORT")
        try:
            db_port = int(db_port_str) if db_port_str else None
        except ValueError:
            raise ConfigError(f"Invalid DB_PORT value: {db_port_str!r}. Must be an integer.")
        db_user = os.getenv("DB_USER")
        db_password = os.getenv("DB_PASSWORD")
        db_name = os.getenv("DB_NAME")

        # Embedding 环境变量
        embedding_model = os.getenv("EMBEDDING_MODEL", cls.DEFAULT_EMBEDDING_MODEL)
        embedding_dimensions_str = os.getenv("EMBEDDING_DIMENSIONS")
        try:
            embedding_dimensions = int(embedding_dimensions_str) if embedding_dimensions_str else cls.DEFAULT_EMBEDDING_DIMENSIONS
        except ValueError:
            raise ConfigError(f"Invalid EMBEDDING_DIMENSIONS value: {embedding_dimensions_str!r}. Must be an integer.")
        embedding_api_key = os.getenv("EMBEDDING_API_KEY")
        embedding_base_url = os.getenv("EMBEDDING_BASE_URL")

        # Rerank 环境变量
        rerank_model = os.getenv("RERANK_MODEL", cls.DEFAULT_RERANK_MODEL)
        rerank_max_candidates_str = os.getenv("RERANK_MAX_CANDIDATES")
        try:
            rerank_max_candidates = int(rerank_max_candidates_str) if rerank_max_candidates_str else cls.DEFAULT_RERANK_MAX_CANDIDATES
        except ValueError:
            raise ConfigError(f"Invalid RERANK_MAX_CANDIDATES value: {rerank_max_candidates_str!r}. Must be an integer.")
        rerank_timeout_str = os.getenv("RERANK_TIMEOUT")
        try:
            rerank_timeout = float(rerank_timeout_str) if rerank_timeout_str else cls.DEFAULT_RERANK_TIMEOUT
        except ValueError:
            raise ConfigError(f"Invalid RERANK_TIMEOUT value: {rerank_timeout_str!r}. Must be a float.")
        rerank_base_url = os.getenv("RERANK_BASE_URL")
        rerank_api_key = os.getenv("RERANK_API_KEY")

        # LLM 和 Embedding 超时环境变量
        llm_timeout_str = os.getenv("LLM_TIMEOUT")
        try:
            llm_timeout = float(llm_timeout_str) if llm_timeout_str else cls.DEFAULT_LLM_TIMEOUT
        except ValueError:
            raise ConfigError(f"Invalid LLM_TIMEOUT value: {llm_timeout_str!r}. Must be a float.")
        embedding_timeout_str = os.getenv("EMBEDDING_TIMEOUT")
        try:
            embedding_timeout = float(embedding_timeout_str) if embedding_timeout_str else cls.DEFAULT_EMBEDDING_TIMEOUT
        except ValueError:
            raise ConfigError(f"Invalid EMBEDDING_TIMEOUT value: {embedding_timeout_str!r}. Must be a float.")

        # LLM 生成参数
        llm_max_tokens_str = os.getenv("LLM_MAX_TOKENS")
        try:
            llm_max_tokens = int(llm_max_tokens_str) if llm_max_tokens_str else cls.DEFAULT_LLM_MAX_TOKENS
        except ValueError:
            raise ConfigError(f"Invalid LLM_MAX_TOKENS value: {llm_max_tokens_str!r}. Must be an integer.")
        llm_temperature_str = os.getenv("LLM_TEMPERATURE")
        try:
            llm_temperature = float(llm_temperature_str) if llm_temperature_str else cls.DEFAULT_LLM_TEMPERATURE
        except ValueError:
            raise ConfigError(f"Invalid LLM_TEMPERATURE value: {llm_temperature_str!r}. Must be a float.")

        config = cls(
            api_key=api_key,
            base_url=base_url,
            model=model,
            skills_dir=skills_dir,
            db_host=db_host,
            db_port=db_port,
            db_user=db_user,
            db_password=db_password,
            db_name=db_name,
            embedding_model=embedding_model,
            embedding_dimensions=embedding_dimensions,
            embedding_api_key=embedding_api_key,
            embedding_base_url=embedding_base_url,
            rerank_model=rerank_model,
            rerank_max_candidates=rerank_max_candidates,
            rerank_timeout=rerank_timeout,
            rerank_base_url=rerank_base_url,
            rerank_api_key=rerank_api_key,
            llm_timeout=llm_timeout,
            embedding_timeout=embedding_timeout,
            llm_max_tokens=llm_max_tokens,
            llm_temperature=llm_temperature,
        )

        # 验证配置
        config._validate()

        return config

    def _validate(self) -> None:
        """
        验证配置有效性

        Raises:
            ConfigError: 配置无效时
        """
        if not self.api_key:
            # 空的 api_key 允许（测试用），但应该警告
            pass

        # 验证 URL 格式
        if self.base_url and not (self.base_url.startswith("http://") or
                                  self.base_url.startswith("https://")):
            raise ConfigError(f"Invalid OPENAI_BASE_URL: {self.base_url}")

        # 验证 embedding_base_url 格式
        if self.embedding_base_url and not (
            self.embedding_base_url.startswith("http://") or
            self.embedding_base_url.startswith("https://")
        ):
            raise ConfigError(f"Invalid EMBEDDING_BASE_URL: {self.embedding_base_url}")

        # 验证 rerank_base_url 格式
        if self.rerank_base_url and not (
            self.rerank_base_url.startswith("http://") or
            self.rerank_base_url.startswith("https://")
        ):
            raise ConfigError(f"Invalid RERANK_BASE_URL: {self.rerank_base_url}")

        # 验证 model 不为空
        if not self.model:
            raise ConfigError("OPENAI_MODEL cannot be empty")
