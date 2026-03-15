from __future__ import annotations

from datetime import date, datetime
import importlib.util
from pathlib import Path
import sys
from typing import Any

from flask import Flask

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ARTICLES_PATH = PROJECT_ROOT / "backend" / "routes" / "articles.py"
_spec = importlib.util.spec_from_file_location("articles_route_for_test", ARTICLES_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError("failed to load articles.py for tests")
articles_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(articles_module)


class _FakeCursor:
    def __init__(self, script: list[dict[str, Any]]) -> None:
        self._script = script
        self._index = 0
        self._current: dict[str, Any] | None = None

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, sql: str, params: Any = None) -> None:
        if self._index >= len(self._script):
            raise AssertionError("db script exhausted")
        step = self._script[self._index]
        self._index += 1
        self._current = step

    def fetchall(self) -> list[dict[str, Any]]:
        if self._current is None:
            raise AssertionError("fetchall before execute")
        return self._current.get("fetchall", [])

    def fetchone(self) -> dict[str, Any] | None:
        if self._current is None:
            raise AssertionError("fetchone before execute")
        return self._current.get("fetchone")


class _FakeConnection:
    def __init__(self, script: list[dict[str, Any]]) -> None:
        self._script = script

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._script)


class _FakeDbSession:
    def __init__(self, script: list[dict[str, Any]]) -> None:
        self._script = script

    def __call__(self) -> _FakeConnection:
        return _FakeConnection(self._script)



def _make_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(articles_module.bp, url_prefix="/api/articles")
    return app


def test_today_endpoint_returns_304_when_etag_matches(monkeypatch):
    app = _make_app()
    db_script = [
        {
            "fetchall": [
                {
                    "id": 101,
                    "title": "通知",
                    "unit": "教务处",
                    "link": "https://example.com/101",
                    "published_on": date(2026, 3, 15),
                    "summary": "摘要",
                    "attachments": [],
                    "created_at": datetime(2026, 3, 15, 8, 0, 0),
                }
            ]
        },
        {"fetchone": {"has_more": False}},
    ]
    monkeypatch.setattr(articles_module, "db_session", _FakeDbSession(db_script))

    with app.test_client() as client:
        first = client.get("/api/articles/today")
        assert first.status_code == 200
        etag = first.headers.get("ETag")
        assert etag

        second = client.get("/api/articles/today", headers={"If-None-Match": etag})
        assert second.status_code == 304


def test_articles_endpoint_returns_304_when_etag_matches(monkeypatch):
    app = _make_app()
    db_script = [
        {
            "fetchall": [
                {
                    "id": 88,
                    "title": "通知2",
                    "unit": "学生处",
                    "link": "https://example.com/88",
                    "published_on": date(2026, 3, 14),
                    "summary": "摘要2",
                    "attachments": [],
                    "created_at": datetime(2026, 3, 14, 9, 0, 0),
                }
            ]
        },
        {"fetchone": {"has_more": False}},
    ]
    monkeypatch.setattr(articles_module, "db_session", _FakeDbSession(db_script))

    with app.test_client() as client:
        first = client.get("/api/articles/?before_id=100&limit=20")
        assert first.status_code == 200
        etag = first.headers.get("ETag")
        assert etag

        second = client.get("/api/articles/?before_id=100&limit=20", headers={"If-None-Match": etag})
        assert second.status_code == 304


def test_article_detail_endpoint_returns_304_when_etag_matches(monkeypatch):
    app = _make_app()
    db_script = [
        {
            "fetchone": {
                "id": 7,
                "title": "详细通知",
                "unit": "后勤",
                "link": "https://example.com/7",
                "published_on": date(2026, 3, 10),
                "content": "正文",
                "summary": "摘要",
                "attachments": [],
                "created_at": datetime(2026, 3, 10, 10, 0, 0),
                "updated_at": datetime(2026, 3, 10, 10, 30, 0),
            }
        }
    ]
    monkeypatch.setattr(articles_module, "db_session", _FakeDbSession(db_script))

    with app.test_client() as client:
        first = client.get("/api/articles/7")
        assert first.status_code == 200
        etag = first.headers.get("ETag")
        assert etag

        second = client.get("/api/articles/7", headers={"If-None-Match": etag})
        assert second.status_code == 304
