"""管理 API - 管理接口（预留）"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/admin", tags=["admin"])
