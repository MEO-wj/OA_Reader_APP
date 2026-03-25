"""管理 API - 文档上传和管理接口"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.api.document_service import (
    delete_document,
    import_document_content,
    list_documents,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

# 模板目录
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates" / "documents"


# ============================================================================
# 请求/响应模型
# ============================================================================


class DocumentUploadResponse(BaseModel):
    """文档上传响应"""
    status: str
    message: str
    document: dict[str, Any] | None = None
    processing_steps: list[str] | None = None


class DocumentListResponse(BaseModel):
    """文档列表响应"""
    status: str
    documents: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


class ErrorResponse(BaseModel):
    """错误响应"""
    status: str = "error"
    message: str


# ============================================================================
# 模板接口（保留用于兼容性）
# ============================================================================


@router.get("/templates/{document_type}")
async def get_template(document_type: str):
    """获取文档模板

    Args:
        document_type: 文档类型（仅支持 documents）

    Returns:
        模板信息
    """
    if document_type != "documents":
        raise HTTPException(status_code=404, detail=f"不支持的模板类型: {document_type}")

    return {
        "type": "documents",
        "description": "通用文档模板",
        "format": "markdown",
        "content": "# 文档标题\n\n文档内容..."
    }


@router.get("/templates/{document_type}/example")
async def get_template_example(document_type: str):
    """获取示例文件下载

    Args:
        document_type: 文档类型

    Returns:
        示例文件下载
    """
    if document_type != "documents":
        raise HTTPException(status_code=404, detail=f"不支持的模板类型: {document_type}")

    raise HTTPException(status_code=404, detail="示例文件不存在")


# ============================================================================
# 文档上传接口（统一）
# ============================================================================


@router.post("/documents", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile):
    """上传文档

    Args:
        file: 文件（支持 .md 或 .json）

    Returns:
        上传结果
    """
    if not file.filename.endswith((".md", ".json")):
        raise HTTPException(status_code=400, detail="只支持 .md 或 .json 文件")

    try:
        content = (await file.read()).decode("utf-8")
        title = file.filename.rsplit(".", 1)[0]  # 移除扩展名

        # 根据文件类型设置 source_type
        source_type = "markdown" if file.filename.endswith(".md") else "json"

        result = await import_document_content(title, content, source_type)

        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result.get("message"))

        return DocumentUploadResponse(**result)

    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件编码错误，请使用 UTF-8 编码")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传失败: {e}")


# ============================================================================
# 文档列表接口
# ============================================================================


@router.get("/documents", response_model=DocumentListResponse)
async def get_documents(
    limit: int = 100,
    offset: int = 0
):
    """获取文档列表

    Args:
        limit: 返回数量 (默认 100)
        offset: 偏移量 (默认 0)

    Returns:
        文档列表
    """
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="limit 必须在 1-1000 之间")

    if offset < 0:
        raise HTTPException(status_code=400, detail="offset 必须大于等于 0")

    result = await list_documents("documents", limit, offset)

    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message"))

    return DocumentListResponse(**result)


# ============================================================================
# 文档删除接口
# ============================================================================


@router.delete("/documents/{document_id}")
async def delete_document_endpoint(document_id: int):
    """删除文档

    Args:
        document_id: 文档 ID

    Returns:
        删除结果
    """
    if document_id < 1:
        raise HTTPException(status_code=400, detail="document_id 必须大于 0")

    result = await delete_document("documents", document_id)

    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("message"))

    return result

