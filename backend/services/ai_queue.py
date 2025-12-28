"""AI请求消息队列处理器。

使用内存队列（threading.Queue）实现AI请求的排队处理，
避免高并发时压垮后端。
"""

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from flask import Flask

logger = logging.getLogger(__name__)


@dataclass
class QueueRequest:
    """队列中的请求项。

    Attributes:
        request_id: 请求唯一标识
        data: 请求数据
        result_future: 结果等待机制（event + holder）
        created_at: 创建时间（Unix时间戳）
    """

    request_id: str
    data: dict[str, Any]
    result_future: dict[str, Any]
    created_at: float = field(default_factory=time.time)


class AIRequestQueue:
    """AI请求消息队列。

    队列满时直接拒绝请求（返回503），不阻塞。
    请求入队后阻塞等待处理结果。

    使用示例:
        queue = AIRequestQueue(app, max_size=20, timeout=30)
        queue.set_handler(lambda data: {"answer": "response"})
        queue.start()
        success, result = queue.enqueue({"question": "hello"})
    """

    def __init__(self, app: Flask, max_size: int = 20, timeout: int = 30):
        """初始化队列。

        Args:
            app: Flask应用实例
            max_size: 队列最大长度
            timeout: 请求处理超时时间（秒）
        """
        self.app = app
        self.queue = queue.Queue(maxsize=max_size)
        self.timeout = timeout
        self.worker_thread: threading.Thread | None = None
        self.running = False
        self.request_handler: Optional[Callable[[dict[str, Any]], dict[str, Any]]] = None

    def set_handler(
        self, handler: Callable[[dict[str, Any]], dict[str, Any]]
    ) -> None:
        """设置请求处理函数（实际调用AI的逻辑）。

        Args:
            handler: 处理请求数据的函数，返回响应数据
        """
        self.request_handler = handler

    def start(self) -> None:
        """启动工作线程。"""
        if self.running:
            return
        self.running = True
        self.worker_thread = threading.Thread(
            target=self._process_queue, daemon=True, name="AIQueueWorker"
        )
        self.worker_thread.start()
        logger.info("AI请求队列工作线程已启动")

    def stop(self) -> None:
        """停止工作线程。"""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        logger.info("AI请求队列工作线程已停止")

    def enqueue(
        self, request_data: dict[str, Any]
    ) -> tuple[bool, str | dict[str, Any]]:
        """入队并等待结果。

        Args:
            request_data: 请求数据

        Returns:
            (success, result) 元组
            - success=True: result是响应数据
            - success=False: result是错误消息
        """
        if not self.running:
            return False, "队列未启动"

        try:
            # 创建结果等待机制
            result_holder = {"done": False, "result": None, "error": None}
            event = threading.Event()

            req = QueueRequest(
                request_id=f"{threading.get_ident()}_{int(time.time() * 1000)}",
                data=request_data,
                result_future={"event": event, "holder": result_holder},
            )

            # 尝试入队（带超时，避免无限阻塞）
            self.queue.put(req, block=True, timeout=5)
            logger.info(f"请求 {req.request_id} 已入队，当前队列深度: {self.queue.qsize()}")

            # 等待处理结果
            if event.wait(timeout=self.timeout):
                if result_holder["error"]:
                    return False, result_holder["error"]
                return True, result_holder["result"]
            else:
                return False, "请求处理超时"

        except queue.Full:
            logger.warning("AI请求队列已满，拒绝新请求")
            return False, "服务繁忙，请稍后再试"
        except Exception as e:
            logger.error(f"入队异常: {e}")
            return False, f"请求入队失败: {str(e)}"

    def _process_queue(self) -> None:
        """工作线程：从队列中取请求并处理。"""
        while self.running:
            try:
                # 从队列获取请求（阻塞1秒，便于检查running状态）
                try:
                    req: QueueRequest = self.queue.get(block=True, timeout=1)
                except queue.Empty:
                    continue

                logger.info(f"开始处理请求 {req.request_id}")
                start_time = time.time()

                try:
                    # 在Flask app context中处理请求
                    with self.app.app_context():
                        result = self._handle_request(req)

                    elapsed = time.time() - start_time
                    logger.info(f"请求 {req.request_id} 处理完成，耗时 {elapsed:.2f}s")

                    # 设置结果
                    future = req.result_future
                    future["holder"]["done"] = True
                    future["holder"]["result"] = result
                    future["event"].set()

                except Exception as e:
                    logger.error(f"处理请求 {req.request_id} 失败: {e}")
                    future = req.result_future
                    future["holder"]["done"] = True
                    future["holder"]["error"] = str(e)
                    future["event"].set()

                finally:
                    self.queue.task_done()

            except Exception as e:
                logger.error(f"工作线程异常: {e}")

    def _handle_request(self, req: QueueRequest) -> dict[str, Any]:
        """实际处理请求（调用AI逻辑）。

        Args:
            req: 队列请求

        Returns:
            响应数据
        """
        if self.request_handler is None:
            return {"error": "未设置请求处理器"}

        return self.request_handler(req.data)

    def get_stats(self) -> dict[str, Any]:
        """获取队列统计信息。

        Returns:
            包含队列统计的字典
        """
        return {
            "queue_size": self.queue.qsize(),
            "queue_max_size": self.queue.maxsize,
            "running": self.running,
        }
