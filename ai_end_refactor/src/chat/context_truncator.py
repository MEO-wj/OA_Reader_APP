"""
工具输出智能截断模块（方案 B）

针对不同工具类型实现差异化截断策略：
- skill content: 不截断（通常小，且高价值）
- read_reference: 语义边界截断（按段落）
- search_documents: 按配置限制返回数量，摘要长度
- grep_document: 限制匹配数，每条内容长度
- 其他工具: 统一硬上限
"""
import re
from copy import deepcopy
from dataclasses import dataclass


@dataclass
class TruncationResult:
    """截断结果"""
    content: str  # 截断后的内容
    truncated: bool  # 是否被截断
    original_size: int = 0  # 原始大小（字符数）
    returned_size: int = 0  # 返回大小（字符数）
    hint: str = ""  # 提示信息


# 截断阈值配置
_SKILL_CONTENT_MAX_CHARS = 10000  # 技能内容上限（实际不截断）
_READ_REFERENCE_MAX_CHARS = 5000  # read_reference 上限
_SEARCH_DOCUMENTS_MAX_RESULTS = 10  # search_documents 最大结果数（优化：从3提升到10，减少二次搜索）
_SEARCH_DOCUMENTS_MAX_SUMMARY_CHARS = 200  # 每条结果摘要上限
_GREP_DOCUMENT_MAX_MATCHES = 3  # grep_document 最大匹配数
_GREP_DOCUMENT_MAX_CONTENT_CHARS = 500  # 每条匹配内容上限
_GENERIC_TOOL_MAX_CHARS = 2000  # 其他工具上限


def truncate_tool_output(
    tool_type: str,
    tool_name: str,
    content: str,
) -> dict:
    """
    根据工具类型截断输出

    Args:
        tool_type: 工具类型（skill、read_reference、search_documents、grep_document 等）
        tool_name: 工具名称
        content: 原始内容

    Returns:
        包含 content 和 meta 的字典
    """
    original_size = len(content)

    # 技能内容不截断
    if tool_type == "skill":
        return {
            "content": content,
            "truncated": False,
            "original_size": original_size,
            "returned_size": original_size,
        }

    # read_reference: 按段落截断
    if tool_type == "read_reference":
        result = _truncate_by_paragraph(content, _READ_REFERENCE_MAX_CHARS)
        return {
            "content": result.content,
            "truncated": result.truncated,
            "original_size": result.original_size,
            "returned_size": result.returned_size,
            "hint": result.hint,
        }

    # 其他工具：统一截断
    if original_size > _GENERIC_TOOL_MAX_CHARS:
        truncated = content[:_GENERIC_TOOL_MAX_CHARS]
        hint = f"\n\n[内容过长已截断，原文 {original_size} 字符，返回前 {_GENERIC_TOOL_MAX_CHARS} 字符。如需完整内容请使用 grep_document 搜索关键词。]"
        return {
            "content": truncated + hint,
            "truncated": True,
            "original_size": original_size,
            "returned_size": _GENERIC_TOOL_MAX_CHARS,
            "hint": hint.strip(),
        }

    return {
        "content": content,
        "truncated": False,
        "original_size": original_size,
        "returned_size": original_size,
    }


def _truncate_by_paragraph(content: str, max_chars: int) -> TruncationResult:
    """
    按段落边界截断内容

    策略：
    - 保留前面完整段落
    - 省略中间
    - 保留最后一部分（如果可能）

    Args:
        content: 原始内容
        max_chars: 最大字符数

    Returns:
        TruncationResult
    """
    if len(content) <= max_chars:
        return TruncationResult(
            content=content,
            truncated=False,
            original_size=len(content),
            returned_size=len(content),
        )

    # 按段落分割（## 标题或空行分隔）
    paragraphs = re.split(r'\n(?=## )|\n\n+', content)

    if len(paragraphs) <= 2:
        # 段落太少，直接硬截断
        truncated = content[:max_chars]
        hint = f"\n\n[截断提示] 原文 {len(content)} 字符，返回 {max_chars} 字符。"
        # 应用最终收口，确保总长度不超过 max_chars
        final_content, final_hint, final_size = _enforce_hard_cap(truncated, hint, max_chars)
        return TruncationResult(
            content=final_content + final_hint,
            truncated=True,
            original_size=len(content),
            returned_size=final_size,
            hint=final_hint.strip(),
        )

    # 保留首段 + 尾段
    first_para = paragraphs[0]
    last_para = paragraphs[-1]

    # 计算可用空间
    available = max_chars - len(first_para) - len(last_para) - 100  # 留 100 字符给省略提示

    if available > 0:
        middle_count = min(len(paragraphs) - 2, (available // 50) + 1)
        kept_paragraphs = [first_para] + paragraphs[1:1 + middle_count] + [last_para]
    else:
        kept_paragraphs = [first_para]

    result_content = "\n\n".join(kept_paragraphs)
    omitted = len(paragraphs) - len(kept_paragraphs)

    hint = f"\n\n[截断提示] 原文共 {len(paragraphs)} 个章节，已省略中间 {omitted} 个章节（原文 {len(content)} 字符）。如需中间章节内容，请使用 grep_document 搜索关键词。"

    # 应用最终收口，确保总长度不超过 max_chars
    final_content, final_hint, final_size = _enforce_hard_cap(result_content, hint, max_chars)

    return TruncationResult(
        content=final_content + final_hint,
        truncated=True,
        original_size=len(content),
        returned_size=final_size,
        hint=final_hint.strip(),
    )


def _enforce_hard_cap(content: str, hint: str, max_chars: int) -> tuple[str, str, int]:
    """
    强制确保 content + hint 不超过 max_chars（硬上限）。

    优先保留 hint，必要时裁剪 content。

    Args:
        content: 截断后的正文内容
        hint: 提示信息
        max_chars: 硬上限字符数

    Returns:
        (最终内容, 最终提示, 实际总长度)
    """
    combined = content + hint
    if len(combined) <= max_chars:
        return content, hint, len(combined)

    # hint 优先保留，裁剪 content
    if len(hint) >= max_chars:
        # hint 太长，只能截断 hint
        truncated_hint = hint[:max_chars]
        return "", truncated_hint, max_chars

    # 裁剪 content 给 hint 留空间
    available_for_content = max_chars - len(hint)
    truncated_content = content[:available_for_content]
    return truncated_content, hint, max_chars


def truncate_search_documents_result(response: dict) -> dict:
    """
    截断 search_documents 结果

    Args:
        response: 原始响应 {"results": [...], "status": ..., "count": ..., ...}

    Returns:
        截断后的响应（保留所有原始字段）
    """
    # 深拷贝整个 response，保留所有字段
    truncated_response = deepcopy(response)

    results = truncated_response.get("results", [])
    original_count = len(results)

    # 限制结果数量（使用深拷贝避免修改原始数据）
    limited_results = deepcopy(results[:_SEARCH_DOCUMENTS_MAX_RESULTS])

    # 限制每条结果的摘要长度
    for result in limited_results:
        summary = result.get("summary", "")
        if len(summary) > _SEARCH_DOCUMENTS_MAX_SUMMARY_CHARS:
            result["summary"] = summary[:_SEARCH_DOCUMENTS_MAX_SUMMARY_CHARS] + "..."

    # 更新 results 字段
    truncated_response["results"] = limited_results

    # 添加截断元数据
    if original_count > _SEARCH_DOCUMENTS_MAX_RESULTS:
        truncated_response["_meta"] = {
            "truncated": True,
            "original_count": original_count,
            "returned_count": len(limited_results),
            "hint": f"只返回前 {_SEARCH_DOCUMENTS_MAX_RESULTS} 条结果（共 {original_count} 条）",
        }

    return truncated_response


def truncate_grep_document_result(response: dict) -> dict:
    """
    截断 grep_document 结果

    Args:
        response: 原始响应

    Returns:
        截断后的响应（保留所有原始字段）
    """
    if response.get("status") != "success":
        return response

    # 深拷贝整个 response，避免修改原始数据
    truncated_response = deepcopy(response)

    matches = truncated_response.get("data", {}).get("matches", [])
    original_count = len(matches)

    # 限制匹配数量（使用深拷贝避免修改原始数据）
    limited_matches = deepcopy(matches[:_GREP_DOCUMENT_MAX_MATCHES])

    # 限制每条匹配的内容长度
    for match in limited_matches:
        content = match.get("content", "")
        if len(content) > _GREP_DOCUMENT_MAX_CONTENT_CHARS:
            match["content"] = content[:_GREP_DOCUMENT_MAX_CONTENT_CHARS] + "..."

    # 更新 data 字段
    if "data" not in truncated_response:
        truncated_response["data"] = {}
    truncated_response["data"]["matches"] = limited_matches

    # 添加截断元数据
    if original_count > _GREP_DOCUMENT_MAX_MATCHES:
        truncated_response["_meta"] = {
            "truncated": True,
            "original_count": original_count,
            "returned_count": len(limited_matches),
            "hint": f"只返回前 {_GREP_DOCUMENT_MAX_MATCHES} 条匹配（共 {original_count} 条）",
        }

    return truncated_response
