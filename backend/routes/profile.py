"""个人资料接口占位路由。

当前仅用于预留前端资料同步接口，不包含真实持久化逻辑。
所有端点默认返回 501，供前后端协作时明确协议边界。
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, request

from backend.routes.auth import login_required

bp = Blueprint("profile", __name__)


def _reserved_response(method: str, path: str, extra: dict[str, Any] | None = None):
    payload: dict[str, Any] = {
        "error": "个人资料接口已预留，暂未接入服务端持久化实现",
        "code": "profile_api_reserved",
        "reserved": True,
        "method": method,
        "path": path,
    }
    if extra:
        payload.update(extra)
    return jsonify(payload), 501


@bp.route("/profile", methods=["GET"])
@login_required
def get_profile():
    claims = getattr(request, "auth_claims", {})
    return _reserved_response(
        "GET",
        "/api/user/profile",
        {
            "data": {
                "id": claims.get("sub"),
                "display_name": claims.get("name"),
                "avatar_url": None,
                "profile_tags": [],
                "bio": None,
                "profile_updated_at": None,
            }
        },
    )


@bp.route("/profile", methods=["PATCH"])
@login_required
def patch_profile():
    data = request.get_json(silent=True) or {}
    return _reserved_response(
        "PATCH",
        "/api/user/profile",
        {
            "accepted_fields": [
                "display_name",
                "profile_tags",
                "bio",
                "avatar_url",
                "profile_updated_at",
            ],
            "received_fields": sorted(data.keys()),
        },
    )


@bp.route("/profile/avatar", methods=["POST"])
@login_required
def upload_profile_avatar():
    avatar = request.files.get("avatar")
    return _reserved_response(
        "POST",
        "/api/user/profile/avatar",
        {
            "accepted_content_type": "multipart/form-data",
            "accepted_field": "avatar",
            "received_file": avatar.filename if avatar else None,
        },
    )
