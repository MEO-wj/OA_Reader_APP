# tests/acceptance/utils/sse_collector.py
import json
import httpx
import time
from typing import Any


class SSEEventCollector:
    """SSE 事件全量收集与解析"""

    async def collect_chat_events(self, base_url: str, message: str) -> dict[str, Any]:
        """
        全量收集聊天接口的所有事件和数据

        返回:
        {
            "start_time": ISO时间戳,
            "end_time": ISO时间戳,
            "duration_ms": 耗时毫秒,
            "request": {"message": "用户输入"},
            "events": [
                {"type": "start", "timestamp": ..., "data": {...}},
                {"type": "skill_call", "timestamp": ..., "skill": "...", "description": "..."},
                {"type": "tool_call", "timestamp": ..., "tool": "...", "arguments": "{...}"},
                {"type": "tool_result", "timestamp": ..., "tool": "...", "result": "{...}"},
                {"type": "delta", "timestamp": ..., "content": "完整合并的回复"},
                {"type": "done", "timestamp": ..., "usage": {...}}
            ],
            "skills_called": ["skill1", "skill2"],
            "tools_called": [
                {"name": "tool1", "arguments": "{...}", "result": "{...}"}
            ],
            "response": "完整回复",
            "usage": {"prompt_tokens": ..., "completion_tokens": ..., "total_tokens": ...}
        }
        """
        start_time = time.time()
        start_time_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(start_time))

        events = []
        skills_called = []
        tools_called = []
        response_parts = []
        usage = {}

        pending_tool_calls: dict[str, dict] = {}

        # delta 合并处理
        delta_start_time = None
        delta_content_parts = []
        current_event_type = None

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{base_url}/chat",
                json={"message": message},
                timeout=120.0,
            ) as response:

                async for chunk in response.aiter_text():
                    chunk_timestamp = time.time()
                    chunk_time_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(chunk_timestamp))

                    if not chunk.strip():
                        continue

                    for line in chunk.split("\n"):
                        if not line.strip():
                            continue

                        if line.startswith("event: "):
                            new_event_type = line[7:].strip()

                            # 如果从 delta 切换到其他事件，需要先保存累积的 delta
                            if current_event_type == "delta" and new_event_type != "delta":
                                if delta_content_parts:
                                    events.append({
                                        "type": "delta",
                                        "timestamp": delta_start_time,
                                        "content": "".join(delta_content_parts),
                                    })
                                    delta_content_parts = []
                                    delta_start_time = None

                            current_event_type = new_event_type

                        elif line.startswith("data: "):
                            data_str = line[6:].strip()
                            event_data = None
                            if data_str:
                                try:
                                    event_data = json.loads(data_str)
                                except json.JSONDecodeError:
                                    event_data = {"raw": data_str}

                            # 根据事件类型处理
                            if current_event_type == "start":
                                events.append({
                                    "type": "start",
                                    "timestamp": chunk_time_iso,
                                    "data": event_data,
                                })

                            elif current_event_type == "skill_call":
                                skill_name = event_data.get("skill", "") if event_data else ""
                                description = event_data.get("description", "") if event_data else ""
                                events.append({
                                    "type": "skill_call",
                                    "timestamp": chunk_time_iso,
                                    "skill": skill_name,
                                    "description": description,
                                })
                                if skill_name and skill_name not in skills_called:
                                    skills_called.append(skill_name)

                            elif current_event_type == "tool_call":
                                tool_name = event_data.get("tool", "") if event_data else ""
                                arguments = event_data.get("arguments", "") if event_data else ""
                                events.append({
                                    "type": "tool_call",
                                    "timestamp": chunk_time_iso,
                                    "tool": tool_name,
                                    "arguments": arguments,
                                })
                                if tool_name:
                                    pending_tool_calls[tool_name] = {
                                        "name": tool_name,
                                        "arguments": arguments,
                                    }

                            elif current_event_type == "db_operation":
                                operation = event_data.get("operation", "") if event_data else ""
                                message_text = event_data.get("message", "") if event_data else ""
                                events.append({
                                    "type": "db_operation",
                                    "timestamp": chunk_time_iso,
                                    "operation": operation,
                                    "message": message_text,
                                })

                            elif current_event_type == "tool_result":
                                tool_name = event_data.get("tool", "") if event_data else ""
                                result = event_data.get("result", "") if event_data else ""
                                events.append({
                                    "type": "tool_result",
                                    "timestamp": chunk_time_iso,
                                    "tool": tool_name,
                                    "result": result,
                                })
                                if tool_name in pending_tool_calls:
                                    tool_info = pending_tool_calls[tool_name]
                                    tools_called.append({
                                        "name": tool_name,
                                        "arguments": tool_info["arguments"],
                                        "result": result,
                                    })
                                    del pending_tool_calls[tool_name]
                                else:
                                    tools_called.append({
                                        "name": tool_name,
                                        "arguments": "",
                                        "result": result,
                                    })

                            elif current_event_type == "delta":
                                content = event_data.get("content", "") if event_data else ""
                                if content:
                                    if delta_start_time is None:
                                        delta_start_time = chunk_time_iso
                                    delta_content_parts.append(content)
                                    response_parts.append(content)

                            elif current_event_type == "done":
                                # 先保存可能残留的 delta
                                if delta_content_parts:
                                    events.append({
                                        "type": "delta",
                                        "timestamp": delta_start_time,
                                        "content": "".join(delta_content_parts),
                                    })
                                    delta_content_parts = []
                                    delta_start_time = None

                                usage = event_data.get("usage", {}) if event_data else {}
                                events.append({
                                    "type": "done",
                                    "timestamp": chunk_time_iso,
                                    "usage": usage,
                                })

                            elif current_event_type == "error":
                                error_msg = event_data.get("message", "") if event_data else ""
                                events.append({
                                    "type": "error",
                                    "timestamp": chunk_time_iso,
                                    "error": error_msg,
                                })

                            else:
                                events.append({
                                    "type": current_event_type,
                                    "timestamp": chunk_time_iso,
                                    "data": event_data,
                                })

        # 处理可能残留的 delta（流结束但没有 done 事件）
        if delta_content_parts:
            events.append({
                "type": "delta",
                "timestamp": delta_start_time,
                "content": "".join(delta_content_parts),
            })

        end_time = time.time()
        end_time_iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(end_time))

        return {
            "start_time": start_time_iso,
            "end_time": end_time_iso,
            "duration_ms": int((end_time - start_time) * 1000),
            "request": {"message": message},
            "events": events,
            "skills_called": skills_called,
            "tools_called": tools_called,
            "response": "".join(response_parts),
            "usage": usage,
        }
