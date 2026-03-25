"""管理 API 测试（通用 documents 版本）"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


class TestTemplateAPI:
    """模板 API 测试"""

    @pytest.mark.asyncio
    async def test_get_documents_template(self, client: AsyncClient):
        """应返回 documents 模板"""
        response = await client.get("/api/admin/templates/documents")
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "documents"
        assert data["format"] == "markdown"
        assert "content" in data

    @pytest.mark.asyncio
    async def test_get_invalid_template(self, client: AsyncClient):
        """不支持的模板类型应返回 404"""
        response = await client.get("/api/admin/templates/policies")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_documents_template_example_not_found(self, client: AsyncClient):
        """documents 示例文件不存在时应返回 404"""
        response = await client.get("/api/admin/templates/documents/example")
        assert response.status_code == 404


class TestDocumentUploadAPI:
    """文档上传 API 测试"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("filename", "content", "mime_type", "expected_source_type"),
        [
            ("test_doc.md", "# 测试文档", "text/markdown", "markdown"),
            ("test_doc.json", '{"name": "测试"}', "application/json", "json"),
        ],
    )
    async def test_upload_document_success(
        self,
        client: AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        filename: str,
        content: str,
        mime_type: str,
        expected_source_type: str,
    ):
        """上传 .md/.json 文件应调用统一导入服务并返回成功"""
        captured: dict[str, str] = {}

        async def fake_import_document_content(title: str, body: str, source_type: str):
            captured["title"] = title
            captured["body"] = body
            captured["source_type"] = source_type
            return {
                "status": "success",
                "message": "导入成功",
                "document": {"id": 1, "title": title, "type": source_type},
                "processing_steps": ["mock-step"],
            }

        monkeypatch.setattr("src.api.admin.import_document_content", fake_import_document_content)

        files = {"file": (filename, content, mime_type)}
        response = await client.post("/api/admin/documents", files=files)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["document"]["id"] == 1
        assert captured["title"] == "test_doc"
        assert captured["body"] == content
        assert captured["source_type"] == expected_source_type

    @pytest.mark.asyncio
    async def test_upload_document_invalid_file_extension(self, client: AsyncClient):
        """非 .md/.json 文件应返回 400"""
        files = {"file": ("test.txt", "content", "text/plain")}
        response = await client.post("/api/admin/documents", files=files)
        assert response.status_code == 400
        assert "只支持 .md 或 .json 文件" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_document_service_error(self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
        """导入服务返回 error 时应映射为 400"""

        async def fake_import_document_content(title: str, body: str, source_type: str):
            return {"status": "error", "message": "内容为空"}

        monkeypatch.setattr("src.api.admin.import_document_content", fake_import_document_content)

        files = {"file": ("empty.md", "", "text/markdown")}
        response = await client.post("/api/admin/documents", files=files)

        assert response.status_code == 400
        assert response.json()["detail"] == "内容为空"

class TestDocumentListAPI:
    """文档列表 API 测试"""

    @pytest.mark.asyncio
    async def test_list_documents_success(self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
        """应通过统一 documents 类型查询列表"""
        captured: dict[str, int | str] = {}

        async def fake_list_documents(document_type: str, limit: int, offset: int):
            captured["document_type"] = document_type
            captured["limit"] = limit
            captured["offset"] = offset
            return {
                "status": "success",
                "documents": [{"id": 1, "title": "doc", "source_type": "markdown", "summary": "s"}],
                "total": 1,
                "limit": limit,
                "offset": offset,
            }

        monkeypatch.setattr("src.api.admin.list_documents", fake_list_documents)

        response = await client.get("/api/admin/documents?limit=10&offset=2")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "success"
        assert data["total"] == 1
        assert data["limit"] == 10
        assert data["offset"] == 2
        assert captured == {"document_type": "documents", "limit": 10, "offset": 2}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("limit", [0, 1001])
    async def test_list_documents_invalid_limit(self, client: AsyncClient, limit: int):
        """limit 越界应返回 400"""
        response = await client.get(f"/api/admin/documents?limit={limit}&offset=0")
        assert response.status_code == 400
        assert "limit 必须在 1-1000 之间" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_list_documents_invalid_offset(self, client: AsyncClient):
        """offset 小于 0 应返回 400"""
        response = await client.get("/api/admin/documents?limit=10&offset=-1")
        assert response.status_code == 400
        assert "offset 必须大于等于 0" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_list_documents_service_error(self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
        """列表服务返回 error 时应映射为 500"""

        async def fake_list_documents(document_type: str, limit: int, offset: int):
            return {"status": "error", "message": "db error"}

        monkeypatch.setattr("src.api.admin.list_documents", fake_list_documents)

        response = await client.get("/api/admin/documents")
        assert response.status_code == 500
        assert response.json()["detail"] == "db error"


class TestDocumentDeleteAPI:
    """文档删除 API 测试"""

    @pytest.mark.asyncio
    async def test_delete_document_success(self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
        """删除成功时应返回 success"""
        captured: dict[str, int | str] = {}

        async def fake_delete_document(document_type: str, document_id: int):
            captured["document_type"] = document_type
            captured["document_id"] = document_id
            return {"status": "success", "message": "删除成功", "document_id": document_id}

        monkeypatch.setattr("src.api.admin.delete_document", fake_delete_document)

        response = await client.delete("/api/admin/documents/123")
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert captured == {"document_type": "documents", "document_id": 123}

    @pytest.mark.asyncio
    async def test_delete_document_invalid_id(self, client: AsyncClient):
        """非法 document_id 应返回 400"""
        response = await client.delete("/api/admin/documents/0")
        assert response.status_code == 400
        assert "document_id 必须大于 0" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_document_not_found(self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
        """删除不存在文档时应返回 404"""

        async def fake_delete_document(document_type: str, document_id: int):
            return {"status": "error", "message": f"未找到 ID 为 {document_id} 的文档"}

        monkeypatch.setattr("src.api.admin.delete_document", fake_delete_document)

        response = await client.delete("/api/admin/documents/999999")
        assert response.status_code == 404
        assert "未找到 ID 为 999999 的文档" in response.json()["detail"]
