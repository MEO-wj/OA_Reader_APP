"""Flask应用主入口文件。

该文件初始化Flask应用，配置CORS、日志等基础设置，并注册路由。
"""

from __future__ import annotations

import logging
from pathlib import Path
import sys
from typing import Any

from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# 确保脚本运行时能找到 backend 包
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import Config
from backend.db import init_db

# 初始化配置
config = Config()

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 初始化Flask应用
app = Flask(__name__)

# 配置应用
# 1. JWT签名密钥
app.config['SECRET_KEY'] = config.auth_jwt_secret or 'dev-secret'  # 用于JWT签名
# 2. JSON响应支持中文
app.config['JSON_AS_ASCII'] = False  # 支持中文

# 配置CORS
# 支持跨域资源共享，允许前端应用从不同域名访问API
CORS(app, origins=config.cors_allow_origins or ['*'])  # 允许所有来源，生产环境应限制具体域名

# 初始化数据库结构与索引（幂等）
try:
    init_db()
    logger.info("数据库初始化/迁移完成")
except Exception as e:
    logger.error(f"数据库初始化/迁移失败: {e}")

# 配置API限流
# 使用真实客户端IP作为唯一标识，避免反向代理导致同IP限流
def _get_client_ip() -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        ip = forwarded_for.split(",")[0].strip()
        if ip:
            return ip
    real_ip = request.headers.get("X-Real-IP", "").strip()
    if real_ip:
        return real_ip
    return get_remote_address()

rate_limits: list[str] = []
if config.rate_limit_per_day:
    rate_limits.append(f"{config.rate_limit_per_day} per day")
if config.rate_limit_per_hour:
    rate_limits.append(f"{config.rate_limit_per_hour} per hour")

limiter = Limiter(
    _get_client_ip,
    app=app,
    default_limits=rate_limits,
    storage_uri="memory://",
    enabled=bool(rate_limits),
)

# 全局错误处理
@app.errorhandler(400)
def bad_request(error: Any) -> tuple[Any, int]:
    """处理400错误"""
    return jsonify({"error": "请求参数错误"}), 400

@app.errorhandler(401)
def unauthorized(error: Any) -> tuple[Any, int]:
    """处理401错误"""
    return jsonify({"error": "未授权访问"}), 401

@app.errorhandler(403)
def forbidden(error: Any) -> tuple[Any, int]:
    """处理403错误"""
    return jsonify({"error": "禁止访问"}), 403

@app.errorhandler(404)
def not_found(error: Any) -> tuple[Any, int]:
    """处理404错误"""
    return jsonify({"error": "资源不存在"}), 404

@app.errorhandler(500)
def internal_server_error(error: Any) -> tuple[Any, int]:
    """处理500错误"""
    logger.error(f"服务器内部错误: {error}")
    return jsonify({"error": "服务器内部错误"}), 500

# 健康检查端点
@app.route('/api/health', methods=['GET'])
def health_check() -> tuple[Any, int]:
    """健康检查端点"""
    return jsonify({
        "status": "ok",
        "service": "oa-api",
        "version": "0.1.0"
    }), 200

# 导入并注册路由
from backend.routes import articles, auth, ai, profile

app.register_blueprint(auth.bp, url_prefix='/api/auth')
app.register_blueprint(articles.bp, url_prefix='/api/articles')
app.register_blueprint(profile.bp, url_prefix='/api/user')
app.register_blueprint(ai.bp, url_prefix='/api/ai')

# 初始化AI请求队列（在路由注册之后，传入Flask app实例）
try:
    ai._initialize_queue(app)
except Exception as e:
    logger.warning(f"AI队列初始化失败（可能已禁用）: {e}")

if __name__ == '__main__':
    # 开发环境运行
    app.run(host='0.0.0.0', port=4420, debug=True)
