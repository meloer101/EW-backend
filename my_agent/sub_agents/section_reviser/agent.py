"""SectionReviser 定义。

SectionReviser 负责对单个 section 的草稿进行审查，
在内循环中与 Writer 配对使用。
输出写入 state['section_review_result']。
"""

from google.adk.agents import LlmAgent

from ...config import scholar_model
from .prompt import SECTION_REVISER_PROMPT


section_reviser = LlmAgent(
    name="section_reviser",
    model=scholar_model,
    description=(
        "逐节审稿专家：对当前指定节（current_section_id）的草稿进行审查，"
        "从论证充分性、结构合理性、语言规范性、篇幅适当性、引用完整性"
        "五个维度进行评分。输出 JSON 格式的节级审查结果，"
        "包含 passed(bool)、overall_score(0-10)、issues 列表和 "
        "action_suggestion(rewrite/revise/ok)。"
    ),
    instruction=SECTION_REVISER_PROMPT,
    output_key="section_review_result",
)
