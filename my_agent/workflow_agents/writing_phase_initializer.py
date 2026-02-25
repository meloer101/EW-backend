"""WritingPhaseInitializer — 写作阶段状态初始化（Phase 2）。

在 writing_pipeline 的第一步执行，幂等地从 paper_outline 中解析节顺序，
初始化 section_order、current_section_idx、current_section_id、draft_sections。
"""

import json
import logging
import re
from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event

logger = logging.getLogger(__name__)


def _parse_outline(raw) -> dict:
    """将 paper_outline 解析为 Python dict（兼容字符串和 dict 两种输入）。"""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        # 尝试直接 JSON 解析
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # 尝试从 markdown 代码块中提取
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
    logger.error("[WritingPhaseInitializer] 无法解析 paper_outline: %r", str(raw)[:200])
    return {}


def _section_sort_key(section_id: str):
    """将节编号（如 "2.1"）转为可比较的元组（(2, 1)），用于排序。"""
    try:
        return tuple(int(p) for p in section_id.split("."))
    except ValueError:
        return (999,)


class WritingPhaseInitializer(BaseAgent):
    """从 paper_outline 初始化写作阶段所需的 state 变量。

    写入：
    - section_order: list[str]，按 display_number 排序的节 ID 列表
    - current_section_idx: int，当前写作节的索引（从 0 开始）
    - current_section_id: str，当前节 ID
    - draft_sections: dict，始终初始化为空（每次调用都清空，防止旧内容污染）
    - section_retry_counts: dict，各节审稿重试计数（始终从零开始）
    """

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state

        paper_outline_raw = state.get("paper_outline")
        if not paper_outline_raw:
            logger.error(
                "[WritingPhaseInitializer] paper_outline 未在 state 中找到，无法初始化写作阶段"
            )
            yield Event(author=self.name)
            return

        paper_outline = _parse_outline(paper_outline_raw)
        if not paper_outline:
            yield Event(author=self.name)
            return

        # 兼容新版 schema（sections）和旧版（outline_tree）
        sections: dict = (
            paper_outline.get("sections")
            or paper_outline.get("outline_tree")
            or {}
        )

        if not sections:
            logger.error(
                "[WritingPhaseInitializer] paper_outline 中未找到 sections 或 outline_tree 字段"
            )
            yield Event(author=self.name)
            return

        # 按节编号升序排列（支持多级编号如 2.1 < 2.2 < 3）
        section_order = sorted(sections.keys(), key=_section_sort_key)

        # 初始化写作状态（每次调用始终重置，确保干净起点，防止旧内容污染新一轮写作）
        state["section_order"] = section_order
        state["current_section_idx"] = 0
        state["current_section_id"] = section_order[0] if section_order else None
        state["draft_sections"] = {}         # 始终清空，避免上次运行的旧章节混入
        state["section_retry_counts"] = {}   # 重置每节的审稿重试计数

        # 清除上一轮遗留的节级状态
        state.pop("section_review", None)
        state.pop("current_section_draft", None)
        state.pop("compressed_context", None)
        state.pop("sections_to_rewrite", None)  # 清除可能残留的局部重写标记

        logger.info(
            "[WritingPhaseInitializer] 初始化完成：共 %d 节，从 '%s' 开始。顺序: %s",
            len(section_order),
            section_order[0] if section_order else "无",
            section_order,
        )

        yield Event(author=self.name)
