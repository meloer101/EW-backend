"""SectionPassChecker — 审稿流控代理。

自定义 BaseAgent，在写作循环中检查当前节审稿结果，
并根据结果决定：继续下一节、重试当前节或结束循环。
"""

import json
import logging
import re
from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions


def _sort_key(display_number: str) -> list[int]:
    """将 display_number（如 "2.1"）转为可排序的整数列表 [2, 1]。"""
    parts = display_number.split(".")
    result = []
    for p in parts:
        match = re.match(r"(\d+)", p)
        result.append(int(match.group(1)) if match else 0)
    return result


class SectionPassChecker(BaseAgent):
    """检查当前节审稿结果并控制循环。
    
    职责：
    1. 读取 section_review_result，判断当前节是否通过。
    2. 若通过：移动到下一节（更新 current_section_id 和 section_index）。
    3. 若未通过：保持当前节不变（writer 会根据反馈重写）。
    4. 若所有节完成：escalate 退出循环。
    """

    def __init__(self, name: str = "section_pass_checker"):
        super().__init__(name=name)

    async def _run_async_impl(
        self, ctx: InvocationContext
    ) -> AsyncGenerator[Event, None]:
        """检查审稿结果并更新状态或退出循环。"""
        state = ctx.session.state
        
        # 读取审稿结果
        review_raw = state.get("section_review_result", "")
        review = review_raw
        if isinstance(review_raw, str):
            try:
                review = json.loads(review_raw)
            except (json.JSONDecodeError, TypeError):
                review = {}
        
        passed = False
        if isinstance(review, dict):
            passed = review.get("passed", False)
        
        # 读取 section 顺序
        section_order = state.get("section_order", [])
        section_index = state.get("section_index", 0)
        current_section_id = state.get("current_section_id", "")
        
        if not section_order:
            logging.warning(f"[{self.name}] section_order is empty, escalating to exit.")
            yield Event(author=self.name, actions=EventActions(escalate=True))
            return
        
        if passed:
            logging.info(
                f"[{self.name}] Section {current_section_id} passed review."
            )
            
            # 移动到下一节
            next_index = section_index + 1
            
            if next_index >= len(section_order):
                # 所有节完成
                logging.info(
                    f"[{self.name}] All {len(section_order)} sections completed. Escalating to exit loop."
                )
                state["all_sections_complete"] = True
                yield Event(author=self.name, actions=EventActions(escalate=True))
            else:
                # 继续下一节
                next_section_id = section_order[next_index]
                state["section_index"] = next_index
                state["current_section_id"] = next_section_id
                # 清空临时状态
                state["current_section_draft"] = ""
                state["section_review_result"] = ""
                
                logging.info(
                    f"[{self.name}] Moving to next section: {next_section_id} ({next_index + 1}/{len(section_order)})"
                )
                yield Event(author=self.name)
        else:
            logging.info(
                f"[{self.name}] Section {current_section_id} failed review. Writer will revise."
            )
            # 保持 current_section_id 不变，writer 会根据 section_review_result 修订
            yield Event(author=self.name)


# 导出实例
section_pass_checker = SectionPassChecker(name="section_pass_checker")
