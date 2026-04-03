"""分层 API 请求队列（LLM / Embedding）。"""

import asyncio
import inspect
import threading
from dataclasses import dataclass
from functools import partial
from typing import Any, Literal

Lane = Literal["llm", "embedding", "rerank"]


@dataclass
class _QueueTask:
    lane: Lane
    func: Any
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    future: asyncio.Future


class APIQueue:
    """按 lane 控制并发的队列执行器。"""

    def __init__(self, llm_concurrency: int = 2, embedding_concurrency: int = 6, rerank_concurrency: int = 2):
        self._llm_concurrency = llm_concurrency
        self._embedding_concurrency = embedding_concurrency
        self._rerank_concurrency = rerank_concurrency
        self._lane_limits = self._build_lane_limits()
        self._sync_limits = {
            "llm": threading.Semaphore(llm_concurrency),
            "embedding": threading.Semaphore(embedding_concurrency),
            "rerank": threading.Semaphore(rerank_concurrency),
        }
        self._queue: asyncio.Queue[_QueueTask] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._worker_count = llm_concurrency + embedding_concurrency + rerank_concurrency
        self._started = False
        self._worker_loop: asyncio.AbstractEventLoop | None = None
        self._start_lock: asyncio.Lock | None = None
        self._start_lock_loop: asyncio.AbstractEventLoop | None = None
        self._closed = False
        self._close_lock: asyncio.Lock | None = None
        self._close_lock_loop: asyncio.AbstractEventLoop | None = None

    def _build_lane_limits(self) -> dict[Lane, asyncio.Semaphore]:
        return {
            "llm": asyncio.Semaphore(self._llm_concurrency),
            "embedding": asyncio.Semaphore(self._embedding_concurrency),
            "rerank": asyncio.Semaphore(self._rerank_concurrency),
        }

    def _get_start_lock(self, loop: asyncio.AbstractEventLoop) -> asyncio.Lock:
        if self._start_lock is None or self._start_lock_loop is not loop:
            self._start_lock = asyncio.Lock()
            self._start_lock_loop = loop
        return self._start_lock

    def _get_close_lock(self, loop: asyncio.AbstractEventLoop) -> asyncio.Lock:
        if self._close_lock is None or self._close_lock_loop is not loop:
            self._close_lock = asyncio.Lock()
            self._close_lock_loop = loop
        return self._close_lock

    def _reset_for_loop_switch(self, current_loop: asyncio.AbstractEventLoop) -> None:
        """跨事件循环复用时重置 worker 运行态，避免挂在旧 loop 的 task 卡死。"""
        old_loop = self._worker_loop
        if old_loop is not None and old_loop is not current_loop and not old_loop.is_closed():
            for worker in self._workers:
                if worker.done():
                    continue
                try:
                    old_loop.call_soon_threadsafe(worker.cancel)
                except RuntimeError:
                    pass

        self._workers.clear()
        self._queue = asyncio.Queue()
        self._lane_limits = self._build_lane_limits()
        self._started = False
        self._worker_loop = None

    async def _ensure_workers(self) -> None:
        current_loop = asyncio.get_running_loop()
        if self._closed:
            raise RuntimeError("APIQueue has been closed")
        if self._started and self._worker_loop is current_loop:
            return
        if self._started and self._worker_loop is not current_loop:
            self._reset_for_loop_switch(current_loop)

        start_lock = self._get_start_lock(current_loop)
        async with start_lock:
            if self._started and self._worker_loop is current_loop:
                return
            self._workers = [
                asyncio.create_task(self._worker()) for _ in range(self._worker_count)
            ]
            self._started = True
            self._worker_loop = current_loop

    async def _worker(self) -> None:
        while True:
            task = await self._queue.get()
            try:
                semaphore = self._lane_limits[task.lane]
                async with semaphore:
                    loop = asyncio.get_running_loop()
                    result = await loop.run_in_executor(
                        None, partial(task.func, *task.args, **task.kwargs)
                    )
                    if not task.future.done():
                        task.future.set_result(result)
            except Exception as exc:
                if not task.future.done():
                    task.future.set_exception(exc)
            finally:
                self._queue.task_done()

    async def close(self) -> None:
        """关闭队列，取消所有 worker 任务。"""
        current_loop = asyncio.get_running_loop()
        close_lock = self._get_close_lock(current_loop)
        async with close_lock:
            if self._closed:
                return
            self._closed = True
            for worker in self._workers:
                if worker.done():
                    continue
                worker_loop = worker.get_loop()
                if worker_loop is current_loop:
                    worker.cancel()
                elif not worker_loop.is_closed():
                    try:
                        worker_loop.call_soon_threadsafe(worker.cancel)
                    except RuntimeError:
                        pass
            self._workers.clear()
            self._started = False
            self._worker_loop = None

    async def submit(self, lane: Lane, func: Any, *args: Any, **kwargs: Any) -> Any:
        await self._ensure_workers()
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        await self._queue.put(
            _QueueTask(lane=lane, func=func, args=args, kwargs=kwargs, future=future)
        )
        return await future

    async def submit_async(self, lane: Lane, func: Any, *args: Any, **kwargs: Any) -> Any:
        """
        直接在当前事件循环执行异步任务，并复用 lane 并发控制。

        适用于返回 coroutine 或 async generator 的函数。
        """
        await self._ensure_workers()
        semaphore = self._lane_limits[lane]
        result = func(*args, **kwargs)

        if inspect.isawaitable(result):
            async with semaphore:
                return await result

        if hasattr(result, "__aiter__"):
            async def _guarded_stream():
                import logging
                logger = logging.getLogger(__name__)
                try:
                    async with semaphore:
                        async for item in result:
                            yield item
                except Exception as exc:
                    logger.exception(f"Async generator stream error: {exc}")
                    raise  # 重新抛出，让调用方捕获
            return _guarded_stream()

        async with semaphore:
            return result

    def submit_sync(self, lane: Lane, func: Any, *args: Any, **kwargs: Any) -> Any:
        semaphore = self._sync_limits[lane]
        with semaphore:
            return func(*args, **kwargs)


_api_queue: APIQueue | None = None
_api_queue_loop: asyncio.AbstractEventLoop | None = None


def get_api_queue() -> APIQueue:
    global _api_queue, _api_queue_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _api_queue is None:
        _api_queue = APIQueue()
        _api_queue_loop = current_loop
    elif current_loop is not None and _api_queue_loop is not current_loop:
        _api_queue = APIQueue()
        _api_queue_loop = current_loop
    return _api_queue


async def _close_api_queue_internal():
    """在创建 APIQueue 的事件循环内关闭队列。"""
    global _api_queue, _api_queue_loop
    if _api_queue:
        await _api_queue.close()
    _api_queue = None
    _api_queue_loop = None


async def close_api_queue():
    """
    关闭 API 队列

    安全地关闭现有队列并将引用置为 None。
    """
    global _api_queue, _api_queue_loop
    if not _api_queue:
        _api_queue_loop = None
        return

    current_loop = asyncio.get_running_loop()
    loop_for_queue = _api_queue_loop
    if (
        isinstance(loop_for_queue, asyncio.AbstractEventLoop)
        and loop_for_queue is not current_loop
        and loop_for_queue.is_running()
    ):
        future = asyncio.run_coroutine_threadsafe(_close_api_queue_internal(), loop_for_queue)
        await asyncio.to_thread(future.result)
        return

    await _close_api_queue_internal()
