"""OAP项目的配置加载器。

该模块提供了一个集中式的配置管理系统，从环境文件和系统环境变量中加载设置，
环境变量的优先级高于基于文件的设置。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from crawler.utils import safe_json_parse

class Config:
    """从环境文件和环境变量加载运行时设置。
    
    配置系统遵循以下优先级顺序：
    1. 默认值（在 __init__ 中设置）
    2. 环境文件中的值（如果存在）
    3. 环境变量（最高优先级）
    
    属性：
        project_root: 项目根目录
        env_file: 环境配置文件的路径
        events_dir: 存储事件数据的目录
        recipient_list_file: 邮件接收者列表的路径
        smtp_server: 用于邮件通知的SMTP服务器
        smtp_port: SMTP服务器端口
        smtp_user: SMTP用户名
        smtp_password: SMTP密码
        api_key: AI服务的API密钥
        ai_base_url: AI聊天完成API的基础URL
        ai_model: 要使用的AI模型名称
        database_url: 数据库连接URL
        embed_base_url: 嵌入服务的基础URL
        embed_model: 嵌入模型名称
        embed_api_key: 嵌入服务的API密钥
        embed_dim: 嵌入向量的维度
    """

    def __init__(self, env_file: str | Path | None = None) -> None:
        """使用默认值初始化配置并从源加载。

        参数：
            env_file: 环境文件的可选自定义路径。
                     如果未提供，则使用 crawler/.env
        """
        # 确定项目根目录（此文件上两级）
        self.project_root = Path(__file__).resolve().parents[1]

        # 设置默认环境文件路径（仅供爬虫使用）
        default_env = Path(__file__).resolve().parent / ".env"
        self.env_file = self._resolve_path(env_file) if env_file else default_env

        # 本地开发的默认配置值
        self.events_dir: Path = self.project_root / "events"  # 事件数据目录
        self.recipient_list_file: Path = self.project_root / "List.txt"  # 邮件接收者
        self.smtp_server: str = "smtp.163.com"  # 通知用的SMTP服务器
        self.smtp_port: int = 465  # SMTP SSL端口
        self.smtp_user: Optional[str] = None  # SMTP用户名
        self.smtp_password: Optional[str] = None  # SMTP密码
        self.api_key: Optional[str] = None  # AI服务API密钥
        self.ai_base_url: str = "https://open.bigmodel.cn/api/paas/v4/chat/completions"  # GLM API URL
        self.ai_model: str = "glm-4.5-flash"  # 默认AI模型
        self.ai_models: list[dict] = []  # 多模型配置（JSON数组）
        self.ai_enable_load_balancing: bool = True  # 是否启用AI负载均衡
        self.database_url: Optional[str] = None  # 数据库连接字符串
        self.embed_base_url: Optional[str] = None  # 嵌入服务URL
        self.embed_model: Optional[str] = None  # 嵌入模型名称
        self.embed_api_key: Optional[str] = None  # 嵌入服务API密钥
        self.embed_dim: int = 1024  # 嵌入向量维度

        # 回填配置
        self.backfill_start_date: Optional[str] = None  # 回填起始日期
        self.backfill_end_date: Optional[str] = None  # 回填结束日期
        self.backfill_batch_size: int = 2  # 每次爬几天
        self.backfill_delay_min: float = 2.0  # 详情页最小延迟(秒)
        self.backfill_delay_max: float = 5.0  # 详情页最大延迟(秒)
        self.backfill_day_delay_min: int = 60  # 天间最小延迟(秒)
        self.backfill_day_delay_max: int = 180  # 天间最大延迟(秒)
        self.backfill_enable_random_delay: bool = True  # 是否启用随机延迟

        # 从所有源加载配置
        self.load()

    # ------------------------------------------------------------------
    # Sender/OA 使用的公共辅助方法
    # ------------------------------------------------------------------
    def load(self) -> None:
        """从文件和环境变量填充配置值。
        
        按以下顺序加载设置：
        1. 从环境文件（如果存在）
        2. 从系统环境变量（覆盖文件值）
        """
        self._load_from_env_file()
        self._override_with_environment()

    def reload(self) -> None:
        """强制重新读取配置源。
        
        当配置文件或环境变量发生变化时很有用。
        """
        self.load()

    def ensure_directories(self) -> None:
        """确保所需目录存在，必要时创建它们。
        
        目前确保 events_dir 目录存在。
        """
        self.events_dir.mkdir(parents=True, exist_ok=True)

    @property
    def ai_headers(self) -> dict[str, str]:
        """为AI API请求生成头信息。
        
        返回：
            包含Content-Type和可选Authorization头的字典
        """
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------
    def _resolve_path(self, value: str | Path) -> Path:
        """将路径解析为绝对路径，如果需要，相对于项目根目录。
        
        参数：
            value: 要解析的路径字符串或Path对象
            
        返回：
            绝对Path对象
        """
        path = Path(value)
        if path.is_absolute():
            return path
        return (self.project_root / path).resolve()

    def _load_from_env_file(self) -> None:
        """从环境文件加载配置值。
        
        支持两种格式：
        1. KEY=VALUE格式（标准）
        2. 简单值行（SMTP_USER、SMTP_PASSWORD、API_KEY的遗留回退）
        
        跳过空行和以#开头的行。
        """
        if not self.env_file.exists():
            return

        # 遗留支持：这些键的简单行格式
        fallback_keys = ["SMTP_USER", "SMTP_PASSWORD", "API_KEY"]
        fallback_index = 0

        try:
            for raw_line in self.env_file.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                # 跳过注释和空行
                if not line or line.startswith("#"):
                    continue

                if "=" in line:
                    # 标准KEY=VALUE格式
                    key, raw_value = line.split("=", 1)
                    key = key.strip().upper()
                    value = raw_value.strip()
                else:
                    # 遗留格式：按顺序的简单值行
                    if fallback_index >= len(fallback_keys):
                        continue
                    key = fallback_keys[fallback_index]
                    value = line
                    fallback_index += 1

                # 将设置应用到相应的属性
                self._apply_setting(key, value)
        except OSError as exc:
            raise RuntimeError(f"无法读取配置文件: {self.env_file}") from exc

    def _override_with_environment(self) -> None:
        """用系统环境变量覆盖配置值。
        
        环境变量的优先级高于环境文件中的值。
        """
        # 可以通过环境变量设置的配置键列表
        keys = [
            "EVENTS_DIR",       # 事件数据目录
            "RECIPIENT_LIST",   # 接收者列表文件路径
            "SMTP_SERVER",      # SMTP服务器地址
            "SMTP_PORT",        # SMTP服务器端口
            "SMTP_USER",        # SMTP用户名
            "SMTP_PASSWORD",    # SMTP密码
            "API_KEY",          # AI服务API密钥
            "AI_BASE_URL",      # AI API基础URL
            "AI_MODEL",         # AI模型名称
            "AI_MODELS",        # AI多模型配置
            "AI_ENABLE_LOAD_BALANCING",  # 是否启用AI负载均衡
            "DATABASE_URL",     # 数据库连接字符串
            "EMBED_BASE_URL",   # 嵌入服务基础URL
            "EMBED_MODEL",      # 嵌入模型名称
            "EMBED_API_KEY",    # 嵌入服务API密钥
            "EMBED_DIM",        # 嵌入向量维度
            "REDIS_HOST",       # Redis主机
            "REDIS_PORT",       # Redis端口
            "REDIS_DB",         # Redis数据库
            "REDIS_PASSWORD",   # Redis密码
            # 回填配置
            "BACKFILL_START_DATE",  # 回填起始日期
            "BACKFILL_END_DATE",    # 回填结束日期
            "BACKFILL_BATCH_SIZE",  # 每次爬几天
            "BACKFILL_DELAY_MIN",   # 详情页最小延迟
            "BACKFILL_DELAY_MAX",   # 详情页最大延迟
            "BACKFILL_DAY_DELAY_MIN",  # 天间最小延迟
            "BACKFILL_DAY_DELAY_MAX",  # 天间最大延迟
            "BACKFILL_ENABLE_RANDOM_DELAY",  # 是否启用随机延迟
        ]
        
        for key in keys:
            value = os.getenv(key)
            if value is not None and value != "":
                self._apply_setting(key, value)

    def _apply_setting(self, key: str, raw_value: str) -> None:
        """将配置设置应用到相应的属性。
        
        参数：
            key: 配置键（大写）
            raw_value: 来自文件或环境的原始字符串值
        """
        value = raw_value.strip()
        
        if key == "EVENTS_DIR":
            # 如有需要，相对于项目根目录解析路径
            self.events_dir = self._resolve_path(value)
        elif key == "RECIPIENT_LIST":
            # 如有需要，相对于项目根目录解析路径
            self.recipient_list_file = self._resolve_path(value)
        elif key == "SMTP_SERVER":
            if value:
                self.smtp_server = value
        elif key == "SMTP_PORT":
            # 转换字符串为整数
            try:
                self.smtp_port = int(value)
            except ValueError:
                pass  # 如果转换失败，保持默认值
        elif key == "SMTP_USER":
            self.smtp_user = value or None
        elif key == "SMTP_PASSWORD":
            self.smtp_password = value or None
        elif key == "API_KEY":
            # 如果存在，移除 "Bearer " 前缀
            token = value.replace("Bearer ", "", 1)
            self.api_key = token or None
        elif key == "AI_BASE_URL":
            if value:
                self.ai_base_url = value
        elif key == "AI_MODEL":
            if value:
                self.ai_model = value
        elif key == "AI_MODELS":
            parsed = safe_json_parse(value, default=None)
            if isinstance(parsed, list):
                self.ai_models = parsed
            else:
                print(f"⚠️ AI_MODELS JSON解析失败: {value}")
        elif key == "AI_ENABLE_LOAD_BALANCING":
            self.ai_enable_load_balancing = value.lower() in ("1", "true", "yes", "on")
        elif key == "DATABASE_URL":
            self.database_url = value or None
        elif key == "EMBED_BASE_URL":
            self.embed_base_url = value or None
        elif key == "EMBED_MODEL":
            self.embed_model = value or None
        elif key == "EMBED_API_KEY":
            self.embed_api_key = value or None
        elif key == "EMBED_DIM":
            # 转换字符串为整数
            try:
                self.embed_dim = int(value)
            except ValueError:
                pass  # 如果转换失败，保持默认值
        elif key == "BACKFILL_START_DATE":
            self.backfill_start_date = value or None
        elif key == "BACKFILL_END_DATE":
            self.backfill_end_date = value or None
        elif key == "BACKFILL_BATCH_SIZE":
            try:
                self.backfill_batch_size = int(value)
            except ValueError:
                pass
        elif key == "BACKFILL_DELAY_MIN":
            try:
                self.backfill_delay_min = float(value)
            except ValueError:
                pass
        elif key == "BACKFILL_DELAY_MAX":
            try:
                self.backfill_delay_max = float(value)
            except ValueError:
                pass
        elif key == "BACKFILL_DAY_DELAY_MIN":
            try:
                self.backfill_day_delay_min = int(value)
            except ValueError:
                pass
        elif key == "BACKFILL_DAY_DELAY_MAX":
            try:
                self.backfill_day_delay_max = int(value)
            except ValueError:
                pass
        elif key == "BACKFILL_ENABLE_RANDOM_DELAY":
            self.backfill_enable_random_delay = value.lower() in ("1", "true", "yes", "on")


__all__ = ["Config"]  # 此模块的公共API
