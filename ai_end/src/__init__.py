"""通用 AI Agent 后端"""

from .config import Config, ConfigError
from .core import SkillSystem, SkillParser, SkillInfo
from .ui import Colors, print_step, print_success, print_error

__version__ = "0.2.0"
__all__ = [
    "Config", "ConfigError",
    "SkillSystem", "SkillParser", "SkillInfo",
    "Colors", "print_step", "print_success", "print_error",
]
