"""SectionStorageAgent 定义。

SectionStorageAgent 是一个自定义 BaseAgent，负责接收并累积
通过 SectionReviser 审核的各节草稿，存储到 draft_sections 中，
并在所有节完成后拼接为完整的 draft_text。
"""

import json
import logging
import re
from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event


def _sort_key(display_number: str) -> list[int]:
    """将 display_number（如 "2.1"）转为可排序的整数列表 [2, 1]。"""
    parts = display_number.split(".")
    result = []
    for p in parts:
        match = re.match(r"(\d+)", p)
        result.append(int(match.group(1)) if match else 0)
    return result


class SectionStorageAgent(BaseAgent):
    """接收通过审核的节草稿，累积到 draft_sections。
    
    每次被调用时：
    1. 读取 current_section_id 和 current_section_draft
    2. 将该节保存到 draft_sections[section_id]
    3. 更新 sections[section_id].status 为 'section_passed'
    4. 检查是否所有叶子节都已完成；若是，拼接全文 draft_text
    """

    def __init__(self, name: str = "section_storage_agent"):
        super().__init__(name=name)

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        """存储当前节草稿并检查是否完成所有节。"""
        state = ctx.session.state
        
        # 读取当前节信息
        section_id = state.get("current_section_id", "")
        draft = state.get("current_section_draft", "")
        
        if not section_id or not draft:
            logging.warning(f"[{self.name}] Missing section_id or draft, skipping.")
            yield Event(author=self.name)
            return
        
        # 更新 draft_sections
        draft_sections = state.get("draft_sections", {})
        if not isinstance(draft_sections, dict):
            draft_sections = {}
        draft_sections[section_id] = draft
        state["draft_sections"] = draft_sections
        
        # 更新 outline 中的 status
        outline = state.get("paper_outline", {})
        if isinstance(outline, str):
            try:
                outline = json.loads(outline)
            except (json.JSONDecodeError, TypeError):
                outline = {}
        
        sections = outline.get("sections", {})
        if section_id in sections:
            sections[section_id]["status"] = "section_passed"
            outline["sections"] = sections
            state["paper_outline"] = outline
        
        logging.info(f"[{self.name}] Stored section {section_id}, status updated to section_passed.")
        
        # 检查是否所有叶子节都完成
        leaf_sections = [
            sid for sid, sec in sections.items()
            if sec.get("word_count", 0) > 0
        ]
        passed_sections = [
            sid for sid in leaf_sections
            if sections[sid].get("status") == "section_passed"
        ]
        
        all_done = len(passed_sections) == len(leaf_sections)
        
        if all_done:
            logging.info(f"[{self.name}] All {len(leaf_sections)} sections completed. Assembling full draft.")
            
            # 按 display_number 排序并拼接
            sorted_ids = sorted(
                passed_sections,
                key=lambda sid: _sort_key(sections[sid].get("display_number", sid))
            )
            
            parts = [draft_sections[sid] for sid in sorted_ids if sid in draft_sections]
            full_text = "\n\n".join(parts)
            state["draft_text"] = full_text
            
            yield Event(
                author=self.name,
                content=None,  # 无需文本输出
            )
        else:
            logging.info(
                f"[{self.name}] Progress: {len(passed_sections)}/{len(leaf_sections)} sections completed."
            )
            yield Event(author=self.name)


# 导出实例
section_storage_agent = SectionStorageAgent(name="section_storage_agent")
