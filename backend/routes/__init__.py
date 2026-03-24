"""API路由模块。

该模块包含所有API路由的蓝图定义，包括认证、文章、个人资料和AI问答等功能。
"""

# 导入各个路由蓝图
from . import auth, articles, ai, profile

__all__ = ['auth', 'articles', 'ai', 'profile']
