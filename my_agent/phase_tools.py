"""ScholarFlow 阶段管理工具函数。

提供显式化的阶段控制函数，供根协调者调用，
实现状态机驱动的工作流编排。
"""

import json
import re
from google.adk.tools.tool_context import ToolContext


def _sort_key(display_number: str) -> list[int]:
    """将 display_number（如 "2.1"）转为可排序的整数列表 [2, 1]。"""
    parts = display_number.split(".")
    result = []
    for p in parts:
        match = re.match(r"(\d+)", p)
        result.append(int(match.group(1)) if match else 0)
    return result


def ensure_writing_phase_state(state: dict) -> dict:
    """根据 paper_outline 确保写作阶段状态已初始化（section_order、current_section_id 等）。

    将提纲中的第一节（按 display_number 排序后的第一个叶子节）设为 current_section_id，
    供 writing_pipeline 第一次进入循环时 writer 使用。幂等：若已初始化则仅返回成功。

    可直接被 init_writing_phase 工具和 WritingPhaseInitializer 代理共用。

    Args:
        state: session.state 或等效的 dict。

    Returns:
        {"status": "success"|"error", "message": str, "section_order": list|None}
    """
    if state.get("section_order") and state.get("current_section_id"):
        return {
            "status": "success",
            "message": "Writing phase already initialized.",
            "section_order": state["section_order"],
        }

    outline_raw = state.get("paper_outline", "")
    outline = outline_raw
    if isinstance(outline_raw, str):
        try:
            outline = json.loads(outline_raw)
        except (json.JSONDecodeError, TypeError):
            return {"status": "error", "message": "Failed to parse paper_outline.", "section_order": None}

    sections = outline.get("sections", {})
    if not sections:
        return {"status": "error", "message": "No sections found in paper_outline.", "section_order": None}

    leaf_sections = [
        (sid, sec.get("display_number", sid))
        for sid, sec in sections.items()
        if sec.get("word_count", 0) > 0
    ]
    leaf_sections.sort(key=lambda x: _sort_key(x[1]))
    section_order = [sid for sid, _ in leaf_sections]

    if not section_order:
        return {
            "status": "error",
            "message": "No leaf sections (word_count > 0) found in outline.",
            "section_order": None,
        }

    state["phase"] = "writing"
    state["section_order"] = section_order
    state["section_index"] = 0
    state["current_section_id"] = section_order[0]
    state["draft_sections"] = state.get("draft_sections") or {}
    state["current_section_draft"] = ""
    state["section_review_result"] = ""
    state["all_sections_complete"] = False

    for sid in section_order:
        sections[sid]["status"] = "pending"
    outline["sections"] = sections
    state["paper_outline"] = outline

    return {
        "status": "success",
        "message": f"Writing phase initialized with {len(section_order)} sections; current_section_id={section_order[0]}.",
        "section_order": section_order,
    }


def init_planning_phase(tool_context: ToolContext) -> dict:
    """初始化规划阶段状态。
    
    设置 phase = "planning"，清空相关状态。
    
    Returns:
        状态描述字典。
    """
    state = tool_context.state
    state["phase"] = "planning"
    state["planning_complete"] = False
    state["paper_outline"] = ""
    state["knowledge_base"] = ""
    
    return {
        "status": "success",
        "message": "Planning phase initialized. Ready to gather knowledge and create outline.",
    }


def init_writing_phase(tool_context: ToolContext) -> dict:
    """初始化写作阶段状态。

    从 paper_outline 中提取叶子节，按 display_number 排序，
    将提纲第一节设为 current_section_id，并初始化 section_order、section_index 等。
    内部调用 ensure_writing_phase_state，与 writing_pipeline 内初始化逻辑一致。

    Returns:
        状态描述字典，包含要写作的节列表。
    """
    return ensure_writing_phase_state(tool_context.state)


def get_phase_status(tool_context: ToolContext) -> dict:
    """获取当前阶段和进度信息。
    
    Returns:
        包含 phase、进度、已完成项等的字典。
    """
    state = tool_context.state
    phase = state.get("phase", "unknown")
    
    result = {"phase": phase}
    
    if phase == "planning":
        result["planning_complete"] = state.get("planning_complete", False)
        result["has_outline"] = bool(state.get("paper_outline", ""))
        result["has_knowledge"] = bool(state.get("knowledge_base", ""))
    
    elif phase == "writing":
        section_order = state.get("section_order", [])
        section_index = state.get("section_index", 0)
        all_complete = state.get("all_sections_complete", False)
        
        result["total_sections"] = len(section_order)
        result["current_section_index"] = section_index
        result["current_section_id"] = state.get("current_section_id", "")
        result["completed_sections"] = section_index
        result["all_sections_complete"] = all_complete
        result["has_full_draft"] = bool(state.get("draft_text", ""))
    
    elif phase == "global_review":
        result["review_passed"] = state.get("review_passed", False)
    
    elif phase == "formatting":
        result["has_formatted_output"] = bool(state.get("formatted_output", ""))
    
    return result


def set_phase(tool_context: ToolContext, phase_name: str) -> dict:
    """显式设置当前阶段。
    
    Args:
        phase_name: 阶段名称，如 "planning", "writing", "global_review", "formatting"。
    
    Returns:
        操作结果字典。
    """
    state = tool_context.state
    state["phase"] = phase_name
    
    return {
        "status": "success",
        "message": f"Phase set to: {phase_name}",
    }
