"""AI 请求队列测试。"""

from __future__ import annotations

import sys
import time
import queue
import threading
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ai_end.services.queue import AIRequestQueue, QueueRequest


class TestQueueRequest:
    """QueueRequest 数据类测试。"""

    def test_queue_request_creation(self):
        """测试队列请求创建。"""
        req = QueueRequest(
            request_id="test-123",
            data={"question": "hello"},
            result_future={"event": Mock(), "holder": {}},
        )

        assert req.request_id == "test-123"
        assert req.data == {"question": "hello"}
        assert req.created_at > 0


class TestAIRequestQueueInit:
    """队列初始化测试。"""

    def test_queue_creation(self):
        """测试队列创建。"""
        mock_app = Mock()
        q = AIRequestQueue(mock_app, max_size=10, timeout=20)

        assert q.app == mock_app
        assert q.queue.maxsize == 10
        assert q.timeout == 20
        assert q.running is False

    def test_default_values(self):
        """测试默认值。"""
        mock_app = Mock()
        q = AIRequestQueue(mock_app)

        assert q.queue.maxsize == 20
        assert q.timeout == 30


class TestAIRequestQueueHandler:
    """队列处理器测试。"""

    def test_set_handler(self):
        """测试设置处理器。"""
        mock_app = Mock()
        q = AIRequestQueue(mock_app)

        handler = lambda data: {"answer": "response"}
        q.set_handler(handler)

        assert q.request_handler is handler

    def test_handler_called(self):
        """测试处理器被调用。"""
        mock_app = Mock()
        q = AIRequestQueue(mock_app)

        handler = Mock(return_value={"answer": "test response"})
        q.set_handler(handler)

        result = q._handle_request(
            QueueRequest(
                request_id="test-1",
                data={"question": "hello"},
                result_future={"event": Mock(), "holder": {}},
            )
        )

        handler.assert_called_once_with({"question": "hello"})
        assert result == {"answer": "test response"}

    def test_handler_not_set(self):
        """测试未设置处理器。"""
        mock_app = Mock()
        q = AIRequestQueue(mock_app)

        result = q._handle_request(
            QueueRequest(
                request_id="test-1",
                data={"question": "hello"},
                result_future={"event": Mock(), "holder": {}},
            )
        )

        assert result == {"error": "未设置请求处理器"}


class TestAIRequestQueueStartStop:
    """队列启动停止测试。"""

    def test_start_queue(self):
        """测试启动队列。"""
        mock_app = Mock()
        q = AIRequestQueue(mock_app)

        q.start()

        assert q.running is True
        assert q.worker_thread is not None
        assert q.worker_thread.daemon is True

    def test_start_twice(self):
        """测试重复启动（应该只启动一次）。"""
        mock_app = Mock()
        q = AIRequestQueue(mock_app)

        q.start()
        first_thread = q.worker_thread

        q.start()
        second_thread = q.worker_thread

        assert first_thread == second_thread

    def test_stop_queue(self):
        """测试停止队列。"""
        mock_app = Mock()
        q = AIRequestQueue(mock_app)

        q.start()
        q.stop()

        assert q.running is False

    def test_stop_before_start(self):
        """测试未启动就停止。"""
        mock_app = Mock()
        q = AIRequestQueue(mock_app)

        # 不应抛出异常
        q.stop()


class TestAIRequestQueueEnqueue:
    """入队测试。"""

    def test_enqueue_when_not_running(self):
        """测试队列未运行时入队。"""
        mock_app = Mock()
        q = AIRequestQueue(mock_app)

        success, result = q.enqueue({"question": "hello"})

        assert success is False
        assert result == "队列未启动"


class TestAIRequestQueueStats:
    """队列统计测试。"""

    def test_get_stats(self):
        """测试获取统计信息。"""
        mock_app = Mock()
        q = AIRequestQueue(mock_app, max_size=10)

        stats = q.get_stats()

        assert stats["queue_size"] == 0
        assert stats["queue_max_size"] == 10
        assert stats["running"] is False


class TestAIRequestQueueEdgeCases:
    """边界情况测试。"""

    def test_zero_timeout(self):
        """测试零超时。"""
        mock_app = Mock()
        q = AIRequestQueue(mock_app, max_size=10, timeout=0)

        assert q.timeout == 0

    def test_negative_max_size(self):
        """测试负数 max_size。"""
        mock_app = Mock()
        q = AIRequestQueue(mock_app, max_size=-1)

        # queue.Queue 接受负数但会变成无界队列
        assert q.queue.maxsize == -1
