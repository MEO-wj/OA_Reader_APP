"""
任务步骤检查点处理器 - 校验 todolist 各步骤完成情况
"""


async def check_step(step: int, status: str, reason: str = "") -> dict:
    """
    任务步骤检查点。校验步骤完成情况，不合规则返回错误触发打回。

    Args:
        step: 当前步骤编号 (1, 2, 3)
        status: 步骤状态 (done, skip, start)
        reason: 跳过步骤时的理由（status=skip 时必填）

    Returns:
        success=True: 步骤通过，message 包含下一步指引
        success=False: 步骤被打回，error 包含打回原因
    """
    if step == 1:
        if status == "skip" and not _is_valid_skip_reason(reason):
            return {
                "success": False,
                "error": f"步骤1跳过理由不合理：'{reason}'。请重新判断是否需要保存记忆。",
            }
        return {"success": True, "message": "步骤1完成。请继续步骤2：判断是否需要查询文章。"}

    if step == 2:
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


def _is_valid_skip_reason(reason: str) -> bool:
    """校验跳过理由是否充分：不能为空，不能是无意义的短文本（至少5字符）。"""
    if not reason or len(reason.strip()) < 5:
        return False
    return True
