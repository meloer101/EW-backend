"""OutlineCompletionChecker — 大纲完整性检查代理。

在 planning_pipeline 中，检查 paper_outline 是否完整，
决定是否继续收集知识或退出循环进入写作阶段。
"""

import json
import logging
from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions


class OutlineCompletionChecker(BaseAgent):
    """检查 paper_outline 完整性并控制规划循环。
    
    判断标准：
    1. outline 包含至少 3 个叶子节（word_count > 0）
    2. 所有必需字段都已填充（title, thesis_statement, sections）
    3. total_word_count 合理（> 1000）
    
    若完整：escalate 退出循环，进入写作阶段。
    若不完整：继续循环（knowledge_agent 会补充信息）。
    """

    def __init__(self, name: str = "outline_completion_checker"):
        super().__init__(name=name)

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        """检查大纲完整性。"""
        state = ctx.session.state
        
        outline_raw = state.get("paper_outline", "")
        outline = outline_raw
        
        if isinstance(outline_raw, str):
            try:
                outline = json.loads(outline_raw)
            except (json.JSONDecodeError, TypeError):
                outline = {}
        
        if not isinstance(outline, dict):
            logging.info(f"[{self.name}] Outline not yet created, continuing loop.")
            yield Event(author=self.name)
            return
        
        # 检查必需字段
        title = outline.get("title", "")
        thesis = outline.get("thesis_statement", "")
        sections = outline.get("sections", {})
        total_wc = outline.get("total_word_count", 0)
        
        if not title or not thesis or not sections:
            logging.info(
                f"[{self.name}] Outline incomplete (missing title/thesis/sections), continuing loop."
            )
            yield Event(author=self.name)
            return
        
        # 统计叶子节数量
        leaf_sections = [
            sid for sid, sec in sections.items()
            if isinstance(sec, dict) and sec.get("word_count", 0) > 0
        ]
        
        if len(leaf_sections) < 3:
            logging.info(
                f"[{self.name}] Outline has only {len(leaf_sections)} leaf sections (need >= 3), continuing loop."
            )
            yield Event(author=self.name)
            return
        
        if total_wc < 1000:
            logging.info(
                f"[{self.name}] Total word count {total_wc} too low (need >= 1000), continuing loop."
            )
            yield Event(author=self.name)
            return
        
        # 大纲完整，退出循环
        logging.info(
            f"[{self.name}] Outline is complete: {len(leaf_sections)} sections, "
            f"{total_wc} words. Escalating to exit planning loop."
        )
        state["planning_complete"] = True
        yield Event(author=self.name, actions=EventActions(escalate=True))


# 导出实例
outline_completion_checker = OutlineCompletionChecker(
    name="outline_completion_checker"
)
