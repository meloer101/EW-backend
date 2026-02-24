"""SectionPassChecker — 节级审稿通过检查器（Phase 2）。

LoopAgent 中的流控节点，根据 section_review 决定：
- 通过：保存当前节草稿，推进到下一节；若为最后一节则 escalate 退出循环
- 未通过：仅 yield Event，循环继续从 SectionMemoryBuilder 重试当前节
"""

import json
import logging
import re
from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions

logger = logging.getLogger(__name__)


def _parse_review(raw) -> dict:
    """解析 section_review JSON，兼容字符串和 dict 输入。"""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
    return {}


class SectionPassChecker(BaseAgent):
    """节级审稿通过检查 & 写作进度管理。

    通过时：
      1. 将 current_section_draft 存入 draft_sections[current_section_id]
      2. 推进 current_section_idx
      3. 若还有下一节：更新 current_section_id，清除节级临时 state，yield Event
      4. 若已是最后一节：escalate，退出 writing_loop

    未通过时：
      仅 yield Event，不修改节索引，LoopAgent 从头重跑（SectionMemoryBuilder 重建 context）
    """

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state

        section_order: list = state.get("section_order", [])
        current_section_idx: int = state.get("current_section_idx", 0)
        current_section_id: str = state.get("current_section_id", "")
        current_section_draft: str = state.get("current_section_draft", "")
        section_review_raw = state.get("section_review")

        # ── 解析审稿结果 ──────────────────────────────────────
        review = _parse_review(section_review_raw) if section_review_raw else {}
        passed = bool(review.get("passed", False))

        if not passed:
            score = review.get("overall_score", "N/A")
            logger.info(
                "[SectionPassChecker] 节 '%s' 审稿未通过（score=%s），重试。",
                current_section_id,
                score,
            )
            yield Event(author=self.name)
            return

        # ── 通过：保存草稿 ─────────────────────────────────────
        draft_sections: dict = state.get("draft_sections") or {}
        if isinstance(draft_sections, str):
            draft_sections = json.loads(draft_sections)

        draft_sections[current_section_id] = current_section_draft
        state["draft_sections"] = draft_sections

        logger.info(
            "[SectionPassChecker] 节 '%s' 审稿通过（score=%s），已保存草稿（%d 字符）。",
            current_section_id,
            review.get("overall_score", "N/A"),
            len(current_section_draft),
        )

        # ── 推进节索引 ─────────────────────────────────────────
        next_idx = current_section_idx + 1

        if next_idx >= len(section_order):
            # 所有节均已完成
            state["current_section_idx"] = next_idx
            logger.info(
                "[SectionPassChecker] 所有 %d 节已完成，escalate 退出 writing_loop。",
                len(section_order),
            )
            yield Event(author=self.name, actions=EventActions(escalate=True))
        else:
            # 移动到下一节，清理节级临时 state
            state["current_section_idx"] = next_idx
            state["current_section_id"] = section_order[next_idx]
            state.pop("section_review", None)
            state.pop("current_section_draft", None)
            state.pop("compressed_context", None)

            logger.info(
                "[SectionPassChecker] 进入下一节 '%s'（%d/%d）。",
                section_order[next_idx],
                next_idx + 1,
                len(section_order),
            )
            yield Event(author=self.name)
