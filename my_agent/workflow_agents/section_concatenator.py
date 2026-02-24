"""SectionConcatenator — 将 draft_sections 拼接为 draft_text（Phase 2）。

在 writing_pipeline 的最后一步运行，按 section_order 顺序拼接所有节正文。
也在 consistency_pipeline 最后一步运行（重新拼接修补后的版本）。
"""

import json
import logging
from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions

logger = logging.getLogger(__name__)


class SectionConcatenator(BaseAgent):
    """将 draft_sections 按 section_order 拼接为 draft_text。

    写入 state["draft_text"]，供 GlobalReviser / Formatter 消费。
    """

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state

        draft_sections = state.get("draft_sections") or {}
        if isinstance(draft_sections, str):
            try:
                draft_sections = json.loads(draft_sections)
            except json.JSONDecodeError:
                draft_sections = {}

        section_order: list = state.get("section_order") or sorted(
            draft_sections.keys()
        )

        parts = []
        missing = []
        for section_id in section_order:
            text = draft_sections.get(section_id, "")
            if text:
                parts.append(text.strip())
            else:
                missing.append(section_id)

        if missing:
            logger.warning(
                "[SectionConcatenator] 以下节在 draft_sections 中缺失，已跳过: %s",
                missing,
            )

        draft_text = "\n\n---\n\n".join(parts)
        state["draft_text"] = draft_text

        logger.info(
            "[SectionConcatenator] 已拼接 %d/%d 节，draft_text 共 %d 字符。",
            len(parts),
            len(section_order),
            len(draft_text),
        )

        # 当 pipeline 被 AgentTool 调用时，只有通过 state_delta 回传的 key 会合并到父 session；
        # 否则 consistency_pipeline / reviser 在父 session 中拿不到 draft_text。
        state_delta = {
            "draft_text": draft_text,
            "draft_sections": state.get("draft_sections"),
            "section_order": section_order,
        }
        yield Event(
            author=self.name,
            actions=EventActions(state_delta=state_delta),
        )
