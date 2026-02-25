"""SectionMemoryBuilder — 无 LLM 的压缩上下文构建器（Phase 2）。

在每节写作前运行，从 paper_outline 和 current_section_id 构建 compressed_context，
不调用任何 LLM，不对已写正文做摘要，直接用提纲替代前文。
"""

import json
import logging
import re
from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event

logger = logging.getLogger(__name__)


def _parse_json(raw) -> dict:
    """将 JSON 字符串或 dict 解析为 dict（兼容 markdown 代码块）。"""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
    return {}


class SectionMemoryBuilder(BaseAgent):
    """为当前节构建 compressed_context，写入 state["compressed_context"]。

    compressed_context 结构：
    {
      "thesis_summary": "...",
      "current_section_spec": {
        "section_id": "2.1",
        "title": "...",
        "section_goal": "...",
        "length_budget": 1200,
        "required_arguments": [...],
        "required_evidence": [...],
        "tone": "formal"
      },
      "terminology_glossary": [...],  // 可选，来自 metadata
    }

    Writer 同时接收完整 paper_outline（把握整体关联）与本节 compressed_context。
    """

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        state = ctx.session.state

        current_section_id: str = state.get("current_section_id", "")
        paper_outline_raw = state.get("paper_outline")

        if not current_section_id or not paper_outline_raw:
            logger.warning(
                "[SectionMemoryBuilder] current_section_id='%s' 或 paper_outline 缺失，跳过构建",
                current_section_id,
            )
            yield Event(author=self.name)
            return

        paper_outline = _parse_json(paper_outline_raw)
        if not paper_outline:
            logger.warning("[SectionMemoryBuilder] 无法解析 paper_outline，跳过构建")
            yield Event(author=self.name)
            return

        # 兼容两种 schema
        sections: dict = (
            paper_outline.get("sections")
            or paper_outline.get("outline_tree")
            or {}
        )
        current_section: dict = sections.get(current_section_id, {})

        # 从 sections 中读取字段，兼容旧版（goal/word_count）和新版（section_goal/length_budget）
        section_goal = (
            current_section.get("section_goal")
            or current_section.get("goal", "")
        )
        length_budget = (
            current_section.get("length_budget")
            or current_section.get("word_count", 1000)
        )
        display_number = current_section.get(
            "display_number", current_section_id
        )

        # 语气：节级 > metadata > 默认 formal
        metadata = paper_outline.get("metadata", {})
        tone = (
            current_section.get("tone")
            or metadata.get("writing_style", "formal")
        )

        # 判断当前节是否为父节（提纲中存在以其编号为前缀的子节，如 "2" 存在 "2.1"）
        section_prefix = current_section_id + "."
        has_sub_sections = any(
            sid.startswith(section_prefix) for sid in sections.keys()
        )

        current_section_spec = {
            "section_id": current_section_id,
            "display_number": display_number,
            "title": current_section.get("title", ""),
            "section_goal": section_goal,
            "length_budget": length_budget,
            "required_arguments": current_section.get("required_arguments", []),
            "required_evidence": current_section.get("required_evidence", []),
            "tone": tone,
            "has_sub_sections": has_sub_sections,  # 父节标记，供 Writer/Reviser 参考
        }

        compressed_context: dict = {
            "thesis_summary": paper_outline.get("thesis_statement", ""),
            "current_section_spec": current_section_spec,
        }

        # 可选：术语表（来自 metadata）
        glossary = metadata.get("terminology_glossary")
        if glossary:
            compressed_context["terminology_glossary"] = glossary

        state["compressed_context"] = json.dumps(
            compressed_context, ensure_ascii=False, indent=2
        )

        logger.info(
            "[SectionMemoryBuilder] 为节 '%s'（%s）构建 compressed_context 完成",
            current_section_id,
            current_section.get("title", ""),
        )

        yield Event(author=self.name)
