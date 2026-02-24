"""SectionReviserAgent 定义（Phase 2）。

对当前节草稿（current_section_draft）进行单节审稿，
输出节级审稿结果到 section_review，供 SectionPassChecker 判断是否通过。
"""

from google.adk.agents import LlmAgent

from ...config import scholar_model
from .prompt import SECTION_REVISER_AGENT_PROMPT


section_reviser_agent = LlmAgent(
    name="section_reviser_agent",
    model=scholar_model,
    description=(
        "节级审稿专家：对当前节草稿从目标达成、论证完整、篇幅、语言、逻辑、"
        "整体关联六个维度进行评审，输出节级审稿结果（JSON 格式，含 passed、"
        "overall_score、issues、action_suggestion）。"
    ),
    instruction=SECTION_REVISER_AGENT_PROMPT,
    output_key="section_review",
)
