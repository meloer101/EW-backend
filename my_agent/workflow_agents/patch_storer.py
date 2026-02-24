"""PatchStorer — 保存 local_patcher_agent 的修补结果并推进指令索引（Phase B）。

在 patch_loop 的每次迭代末尾运行：
1. 将 patched_section_text 写回 draft_sections[current_patch_section_id]
2. 递增 current_patch_idx，使 PatchController 在下次迭代处理下一条指令
"""

import json
import logging
from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event

logger = logging.getLogger(__name__)


class PatchStorer(BaseAgent):
    """将修补后的节正文写回 draft_sections，并推进 patch 索引。"""

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state

        section_id: str = state.get("current_patch_section_id", "")
        patched_text: str = state.get("patched_section_text", "")
        current_idx: int = state.get("current_patch_idx", 0)

        if section_id and patched_text:
            draft_sections: dict = state.get("draft_sections") or {}
            if isinstance(draft_sections, str):
                try:
                    draft_sections = json.loads(draft_sections)
                except json.JSONDecodeError:
                    draft_sections = {}

            original_len = len(draft_sections.get(section_id, ""))
            draft_sections[section_id] = patched_text
            state["draft_sections"] = draft_sections

            logger.info(
                "[PatchStorer] 节 '%s' 修补完成：原 %d 字符 → 新 %d 字符。",
                section_id,
                original_len,
                len(patched_text),
            )
        else:
            logger.warning(
                "[PatchStorer] 未收到有效的修补结果（section_id='%s'，patched_text 长度=%d），跳过保存。",
                section_id,
                len(patched_text),
            )

        # 推进指令索引
        state["current_patch_idx"] = current_idx + 1

        # 清理临时 state
        state.pop("patched_section_text", None)
        state.pop("current_patch_instruction", None)
        state.pop("current_patch_section_id", None)
        state.pop("current_patch_section_text", None)

        yield Event(author=self.name)
