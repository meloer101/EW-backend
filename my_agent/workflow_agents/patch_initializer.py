"""PatchInitializer — 解析 modification_instructions，初始化 patch 队列（Phase B）。

在 consistency_pipeline 的 patch_loop 之前运行，
从 consistency_reviser_agent 的输出中提取修改指令列表。
"""

import json
import logging
import re
from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event

logger = logging.getLogger(__name__)


def _extract_instructions(raw) -> list[dict]:
    """从 modification_instructions state 中提取指令列表。

    支持以下格式：
    - dict: {"modification_instructions": [...], "overall_consistency_passed": bool}
    - list: [{"section_id": ..., ...}, ...]
    - str: JSON 字符串（以上任一格式）
    """
    if isinstance(raw, list):
        return raw

    if isinstance(raw, dict):
        return raw.get("modification_instructions", [])

    if isinstance(raw, str):
        # 尝试直接解析
        try:
            parsed = json.loads(raw)
            return _extract_instructions(parsed)
        except json.JSONDecodeError:
            pass
        # 尝试从 markdown 代码块中提取
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
                return _extract_instructions(parsed)
            except json.JSONDecodeError:
                pass

    logger.warning("[PatchInitializer] 无法解析 modification_instructions: %r", str(raw)[:300])
    return []


class PatchInitializer(BaseAgent):
    """解析 modification_instructions，初始化 patch 执行队列。

    写入：
    - patch_queue: list[dict]，待执行的修改指令列表
    - current_patch_idx: int，当前处理的指令索引（从 0 开始）
    """

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state

        raw = state.get("modification_instructions")
        instructions = _extract_instructions(raw) if raw else []

        # 过滤掉没有 section_id 或 instruction 字段的无效条目
        valid_instructions = [
            instr
            for instr in instructions
            if isinstance(instr, dict)
            and instr.get("section_id")
            and instr.get("instruction")
        ]

        state["patch_queue"] = valid_instructions
        state["current_patch_idx"] = 0
        state.pop("patched_section_text", None)
        state.pop("current_patch_instruction", None)
        state.pop("current_patch_section_id", None)

        logger.info(
            "[PatchInitializer] 共 %d 条有效修改指令（原始 %d 条）。",
            len(valid_instructions),
            len(instructions),
        )

        yield Event(author=self.name)
