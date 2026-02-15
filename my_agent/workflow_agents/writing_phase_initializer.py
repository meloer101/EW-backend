"""WritingPhaseInitializer — 写作阶段入口初始化代理。

在 writing_pipeline 内作为第一个子代理运行，确保在 writer_agent 首次执行前，
session state 中已根据 paper_outline 设置好 section_order 与 current_section_id
（提纲第一节）。与 init_writing_phase 工具共用 ensure_writing_phase_state 逻辑，
协调者是否先调 init_writing_phase 均可：已初始化则幂等跳过。
"""

import logging
from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event

from my_agent.phase_tools import ensure_writing_phase_state


class WritingPhaseInitializer(BaseAgent):
    """在写作循环开始前，根据提纲确保 current_section_id 等状态已设置。

    将提纲中第一节（按 display_number 排序后的第一个叶子节）设为 current_section_id，
    避免 writer_agent 首次运行时因缺少该 context 变量而报错。
    """

    def __init__(self, name: str = "writing_phase_initializer"):
        super().__init__(name=name)

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        """根据 paper_outline 确保写作状态已初始化。"""
        state = ctx.session.state
        result = ensure_writing_phase_state(state)

        if result["status"] == "error":
            logging.warning(
                f"[{self.name}] {result['message']} "
                "Writer may fail if current_section_id is required."
            )
        else:
            logging.info(
                f"[{self.name}] {result['message']} "
                f"current_section_id={state.get('current_section_id', '')}"
            )

        yield Event(author=self.name)


writing_phase_initializer = WritingPhaseInitializer(name="writing_phase_initializer")
