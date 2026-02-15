"""ScholarFlow 状态管理工具函数。

提供给根协调者使用的 FunctionTool，用于在按节写作与审稿流程中
管理 session state：设置当前节 ID、保存节草稿、保存节审稿结果、
拼接全文、初始化写作阶段等。

这些工具通过 ToolContext 操作 state，遵循 ADK 推荐的状态更新模式。
"""

import json
import re
from typing import Optional

from google.adk.tools import ToolContext


# ──────────────────────────────────────────────
# 辅助：display_number 排序 key
# ──────────────────────────────────────────────
def _sort_key(display_number: str) -> list[int]:
    """将 display_number（如 "2.1"）转为可排序的整数列表 [2, 1]。"""
    parts = display_number.split(".")
    result = []
    for p in parts:
        # 提取数字部分
        match = re.match(r"(\d+)", p)
        result.append(int(match.group(1)) if match else 0)
    return result


# ──────────────────────────────────────────────
# 工具 1：设置当前操作的 section ID
# ──────────────────────────────────────────────
def set_current_section(tool_context: ToolContext, section_id: str) -> dict:
    """设置当前要撰写或审稿的 section ID。
    在调用 writer_agent 或 section_reviser 之前必须先调用此工具。

    Args:
        section_id: 要操作的节 ID，如 "1", "2.1"。
    """
    tool_context.state["current_section_id"] = section_id
    # 清除上一节的临时数据，避免残留
    tool_context.state["current_section_draft"] = ""
    tool_context.state["section_review_result"] = ""
    return {
        "status": "success",
        "message": f"当前节已设置为 {section_id}",
    }


# ──────────────────────────────────────────────
# 工具 2：保存当前节草稿到 draft_sections
# ──────────────────────────────────────────────
def save_section_draft(tool_context: ToolContext) -> dict:
    """将 writer_agent 输出的当前节草稿保存到 draft_sections 中，
    并更新该节的状态为 'written'。
    必须在 writer_agent 返回之后调用。
    """
    section_id = tool_context.state.get("current_section_id", "")
    draft = tool_context.state.get("current_section_draft", "")

    if not section_id:
        return {"status": "error", "message": "current_section_id 未设置"}
    if not draft:
        return {"status": "error", "message": "current_section_draft 为空"}

    # 更新 draft_sections
    draft_sections = tool_context.state.get("draft_sections", {})
    if not isinstance(draft_sections, dict):
        draft_sections = {}
    draft_sections[section_id] = draft
    tool_context.state["draft_sections"] = draft_sections

    # 更新 section status
    outline = tool_context.state.get("paper_outline", {})
    if isinstance(outline, str):
        try:
            outline = json.loads(outline)
        except (json.JSONDecodeError, TypeError):
            outline = {}
    sections = outline.get("sections", {})
    if section_id in sections:
        sections[section_id]["status"] = "written"
        outline["sections"] = sections
        tool_context.state["paper_outline"] = outline

    return {
        "status": "success",
        "message": f"节 {section_id} 的草稿已保存，状态更新为 written",
    }


# ──────────────────────────────────────────────
# 工具 3：保存当前节的审稿结果
# ──────────────────────────────────────────────
def save_section_review(tool_context: ToolContext) -> dict:
    """将 section_reviser 输出的审稿结果保存到 paper_outline 的
    sections[section_id].local_review 中，并更新状态。
    必须在 section_reviser 返回之后调用。
    """
    section_id = tool_context.state.get("current_section_id", "")
    review_raw = tool_context.state.get("section_review_result", "")

    if not section_id:
        return {"status": "error", "message": "current_section_id 未设置"}
    if not review_raw:
        return {"status": "error", "message": "section_review_result 为空"}

    # 尝试解析 review JSON
    review = review_raw
    if isinstance(review_raw, str):
        try:
            review = json.loads(review_raw)
        except (json.JSONDecodeError, TypeError):
            review = review_raw  # 保留原始字符串

    # 更新 outline
    outline = tool_context.state.get("paper_outline", {})
    if isinstance(outline, str):
        try:
            outline = json.loads(outline)
        except (json.JSONDecodeError, TypeError):
            outline = {}
    sections = outline.get("sections", {})
    if section_id in sections:
        sections[section_id]["local_review"] = review
        # 判断是否通过
        passed = False
        if isinstance(review, dict):
            passed = review.get("passed", False)
        sections[section_id]["status"] = "section_passed" if passed else "written"
        outline["sections"] = sections
        tool_context.state["paper_outline"] = outline

    passed_str = "通过" if (isinstance(review, dict) and review.get("passed")) else "未通过"
    return {
        "status": "success",
        "message": f"节 {section_id} 的审稿结果已保存，审稿{passed_str}",
        "section_passed": isinstance(review, dict) and review.get("passed", False),
    }


# ──────────────────────────────────────────────
# 工具 4：拼接全文
# ──────────────────────────────────────────────
def assemble_full_draft(tool_context: ToolContext) -> dict:
    """按 display_number 顺序将 draft_sections 中所有节的正文拼接为
    完整的 draft_text。在所有节通过 section 审稿后、调用 global_reviser 前使用。
    """
    draft_sections = tool_context.state.get("draft_sections", {})
    if not isinstance(draft_sections, dict):
        draft_sections = {}

    outline = tool_context.state.get("paper_outline", {})
    if isinstance(outline, str):
        try:
            outline = json.loads(outline)
        except (json.JSONDecodeError, TypeError):
            outline = {}
    sections = outline.get("sections", {})

    # 只拼接在 draft_sections 中有内容的叶子节
    section_ids_with_draft = [
        sid for sid in sections if sid in draft_sections and draft_sections[sid]
    ]
    # 按 display_number 排序
    sorted_ids = sorted(section_ids_with_draft, key=lambda sid: _sort_key(
        sections[sid].get("display_number", sid)
    ))

    parts = []
    for sid in sorted_ids:
        parts.append(draft_sections[sid])

    full_text = "\n\n".join(parts)
    tool_context.state["draft_text"] = full_text

    return {
        "status": "success",
        "message": f"全文已拼接完成，共 {len(sorted_ids)} 个节",
        "total_chars": len(full_text),
    }


# ──────────────────────────────────────────────
# 工具 5：初始化写作阶段
# ──────────────────────────────────────────────
def init_writing_phase(tool_context: ToolContext) -> dict:
    """初始化写作阶段：清空 draft_sections，将所有 section 状态设为 pending。
    在进入阶段三（写作与审稿）前调用一次。
    """
    outline = tool_context.state.get("paper_outline", {})
    if isinstance(outline, str):
        try:
            outline = json.loads(outline)
        except (json.JSONDecodeError, TypeError):
            outline = {}
    sections = outline.get("sections", {})

    # 初始化 status
    for sid in sections:
        sections[sid]["status"] = "pending"
        sections[sid]["local_review"] = None
    outline["sections"] = sections
    tool_context.state["paper_outline"] = outline

    # 清空 draft_sections
    tool_context.state["draft_sections"] = {}
    tool_context.state["draft_text"] = ""
    tool_context.state["review_result"] = ""
    tool_context.state["current_section_id"] = ""
    tool_context.state["current_section_draft"] = ""
    tool_context.state["section_review_result"] = ""

    # 返回按顺序排列的 section 列表，方便协调层按序操作
    sorted_ids = sorted(sections.keys(), key=lambda sid: _sort_key(
        sections[sid].get("display_number", sid)
    ))

    # 过滤出叶子节（word_count > 0 的节才需要撰写）
    leaf_ids = [
        sid for sid in sorted_ids
        if sections[sid].get("word_count", 0) > 0
    ]

    return {
        "status": "success",
        "message": f"写作阶段已初始化，共 {len(leaf_ids)} 个叶子节待撰写",
        "section_order": leaf_ids,
    }


# ──────────────────────────────────────────────
# 工具 6：获取当前写作进度
# ──────────────────────────────────────────────
def get_writing_progress(tool_context: ToolContext) -> dict:
    """获取当前写作进度：已完成节、未完成节、各节状态。
    可在任意时刻调用以了解写作阶段的整体进度。
    """
    outline = tool_context.state.get("paper_outline", {})
    if isinstance(outline, str):
        try:
            outline = json.loads(outline)
        except (json.JSONDecodeError, TypeError):
            outline = {}
    sections = outline.get("sections", {})

    sorted_ids = sorted(sections.keys(), key=lambda sid: _sort_key(
        sections[sid].get("display_number", sid)
    ))

    leaf_ids = [
        sid for sid in sorted_ids
        if sections[sid].get("word_count", 0) > 0
    ]

    progress = {}
    for sid in leaf_ids:
        progress[sid] = {
            "title": sections[sid].get("title", ""),
            "status": sections[sid].get("status", "pending"),
        }

    completed = [sid for sid in leaf_ids if sections[sid].get("status") == "section_passed"]
    pending = [sid for sid in leaf_ids if sections[sid].get("status") != "section_passed"]

    return {
        "total_sections": len(leaf_ids),
        "completed": len(completed),
        "remaining": len(pending),
        "section_order": leaf_ids,
        "details": progress,
    }
