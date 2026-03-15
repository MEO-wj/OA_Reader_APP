"""AI问答API路由模块。

该模块将请求转发给 ai_end 服务处理。
"""

from __future__ import annotations

import logging
from flask import Blueprint, jsonify, request
import requests

from backend.config import Config
from backend.routes.auth import login_required

# 初始化蓝图
bp = Blueprint('ai', __name__)

# 设置日志
logger = logging.getLogger(__name__)

# 配置
config = Config()

# ai_end 服务地址
AI_END_URL = config.ai_end_url or "http://localhost:4421"


def _forward_to_ai_end(endpoint: str, data: dict) -> tuple[dict, int]:
    """转发请求到 ai_end 服务。

    Args:
        endpoint: API 端点（不含前缀）
        data: 请求数据

    Returns:
        (响应数据, HTTP状态码)
    """
    url = f"{AI_END_URL}/{endpoint}"
    try:
        response = requests.post(url, json=data, timeout=120)
        response.raise_for_status()
        return response.json(), response.status_code
    except requests.exceptions.RequestException as e:
        logger.error(f"调用 ai_end 服务失败: {e}")
        return {"error": "AI服务不可用"}, 503


@bp.route('/ask', methods=['POST'])
@login_required
def ask_question():
    """基于向量的问答API（转发到 ai_end）。

    请求体：
        {"question": "你的问题", "top_k": 3, "display_name": "张三"}

    返回：
        包含回答和相关文章的JSON响应
    """
    try:
        data = request.get_json()

        if not data or 'question' not in data:
            return jsonify({"error": "请求参数错误，缺少question字段"}), 400

        question = data['question']
        top_k_hint = data.get('top_k', 3)
        display_name = data.get('display_name')

        # 获取用户信息
        user_claims = getattr(request, "auth_claims", {})
        user_id = str(user_claims.get("sub") or "")

        # 转发到 ai_end
        ai_data = {
            "question": question,
            "top_k": top_k_hint,
            "display_name": display_name,
            "user_id": user_id,
        }

        result, status_code = _forward_to_ai_end("ask", ai_data)
        return jsonify(result), status_code

    except Exception as e:
        logger.error(f"AI问答转发失败: {e}")
        return jsonify({"error": "AI问答失败"}), 500


@bp.route('/clear_memory', methods=['POST'])
@login_required
def clear_memory():
    """清空用户的AI短记忆缓存（转发到 ai_end）。"""
    try:
        user_claims = getattr(request, "auth_claims", {})
        user_id = str(user_claims.get("sub") or "")

        if not user_id:
            return jsonify({"error": "用户信息缺失"}), 400

        result, status_code = _forward_to_ai_end("clear_memory", {"user_id": user_id})
        return jsonify(result), status_code

    except Exception as e:
        logger.error(f"AI记忆清理转发失败: {e}")
        return jsonify({"error": "AI记忆清理失败"}), 500


@bp.route('/embed', methods=['POST'])
@login_required
def create_embedding():
    """生成文本的向量嵌入（转发到 ai_end）。

    请求体：
        {"text": "要生成嵌入的文本"}

    返回：
        包含向量嵌入的JSON响应
    """
    try:
        data = request.get_json()

        if not data or 'text' not in data:
            return jsonify({"error": "请求参数错误，缺少text字段"}), 400

        text = data['text']

        # 转发到 ai_end
        result, status_code = _forward_to_ai_end("embed", {"text": text})
        return jsonify(result), status_code

    except Exception as e:
        logger.error(f"生成向量嵌入转发失败: {e}")
        return jsonify({"error": "生成向量嵌入失败"}), 500
