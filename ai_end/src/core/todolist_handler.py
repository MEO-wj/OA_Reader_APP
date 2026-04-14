"""
任务步骤检查点处理器 - 校验 todolist 各步骤完成情况
"""

# 各步骤 done 时必须调用的工具集合
REQUIRED_TOOLS: dict[int, set[str]] = {
    1: {"form_memory"},
    2: {"search_articles", "grep_article"},
}


async def check_step(step: int, status: str, called_tools: list[str], reason: str = "") -> dict:
    """
    任务步骤检查点。校验步骤完成情况，不合规则返回错误触发打回。

    Args:
        step: 当前步骤编号 (1, 2, 3)
        status: 步骤状态 (done, skip, start)
        called_tools: 当轮已调用的工具名列表（由 handlers.py 注入）
        reason: 跳过步骤时的理由（status=skip 时必填），done 时可选（调试日志）

    Returns:
        success=True: 步骤通过，message 包含下一步指引
        success=False: 步骤被打回，error 包含打回原因
    """
    if not isinstance(called_tools, list):
        return {
            "success": False,
            "error": f"步骤{step}内部错误：called_tools 参数异常。请联系管理员。",
        }

    if step == 1:
        if status == "start":
            return {"success": True, "message": "步骤1开始。请判断是否需要保存记忆，然后调用相应工具。"}
        if status == "done":
            return _validate_done(step, called_tools, "form_memory", "保存记忆",
                                  "请继续步骤2：判断是否需要查询文章。", reason)
        if status == "skip" and not _is_valid_skip_reason(reason):
            return {
                "success": False,
                "error": f"步骤1跳过理由不合理：'{reason}'。请重新判断是否需要保存记忆。",
            }
        return {"success": True, "message": "步骤1完成。请继续步骤2：判断是否需要查询文章。"}

    if step == 2:
        if status == "start":
            return {"success": True, "message": "步骤2开始。请判断是否需要查询文章，然后调用相应工具。"}
        if status == "done":
            return _validate_done(step, called_tools, "search_articles/grep_article", "查询文章",
                                  "请继续步骤3：整理并总结回答。", reason)
        if status == "skip" and not _is_valid_skip_reason(reason):
            return {
                "success": False,
                "error": f"步骤2跳过理由不合理：'{reason}'。请重新判断是否需要查询文章。",
            }
        return {"success": True, "message": "步骤2完成。请继续步骤3：整理并总结回答。"}

    if step == 3:
        return {"success": True, "message": "请直接输出最终回答。"}

    # 未定义的步骤号：向前兼容，默认通过
    return {"success": True, "message": "请继续下一步。"}


def _validate_done(
    step: int, called_tools: list[str], tool_desc: str,
    action_desc: str, next_hint: str, reason: str = "",
) -> dict:
    """校验 done 状态时必需工具是否被调用。"""
    required = REQUIRED_TOOLS.get(step, set())
    called_set = set(called_tools)

    if not required.intersection(called_set):
        return {
            "success": False,
            "error": f"步骤{step}要求调用{tool_desc}工具，但未检测到调用记录。请先执行{action_desc}再标记完成。",
        }

    message = f"步骤{step}完成。"
    if reason:
        message += f"备注: {reason}。"
    message += next_hint
    return {"success": True, "message": message}


def _is_valid_skip_reason(reason: str) -> bool:
    """校验跳过理由是否充分：不能为空，不能是无意义的短文本（至少5字符）。"""
    if not reason or len(reason.strip()) < 5:
        return False
    return True
