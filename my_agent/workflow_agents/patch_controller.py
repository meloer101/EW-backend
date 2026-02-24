"""PatchController — patch_loop 内的流控节点（Phase B）。

每次循环迭代开始时运行：
- 若 patch_queue 已处理完毕：escalate 退出 patch_loop
- 否则：从队列取出当前指令，设置 current_patch_instruction、
  current_patch_section_id、current_patch_section_text，供 local_patcher_agent 消费
"""

import json
import logging
from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions

logger = logging.getLogger(__name__)


class PatchController(BaseAgent):
    """patch_loop 中的调度节点：设置当前待修改指令，或 escalate 退出循环。"""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state

        patch_queue: list = state.get("patch_queue", [])
        current_idx: int = state.get("current_patch_idx", 0)

        if current_idx >= len(patch_queue):
            logger.info(
                "[PatchController] 所有 %d 条修改指令已处理，escalate 退出 patch_loop。",
                len(patch_queue),
            )
            yield Event(author=self.name, actions=EventActions(escalate=True))
            return

        current_instruction: dict = patch_queue[current_idx]
        section_id: str = current_instruction.get("section_id", "")

        # 取出对应节的当前正文（供 local_patcher_agent 读取）
        draft_sections: dict = state.get("draft_sections") or {}
        if isinstance(draft_sections, str):
            try:
                draft_sections = json.loads(draft_sections)
            except json.JSONDecodeError:
                draft_sections = {}

        section_text = draft_sections.get(section_id, "")

        state["current_patch_instruction"] = json.dumps(
            current_instruction, ensure_ascii=False, indent=2
        )
        state["current_patch_section_id"] = section_id
        state["current_patch_section_text"] = section_text

        logger.info(
            "[PatchController] 执行第 %d/%d 条指令：节 '%s'，类型 '%s'。",
            current_idx + 1,
            len(patch_queue),
            section_id,
            current_instruction.get("issue_type", "unknown"),
        )

        yield Event(author=self.name)
