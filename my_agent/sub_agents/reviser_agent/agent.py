"""ReviserAgent 定义。

ReviserAgent 负责对论文草稿进行审查，评估质量并提出修改建议。
"""

from google.adk.agents import LlmAgent

from ...config import scholar_model
from .prompt import REVISER_AGENT_PROMPT


reviser_agent = LlmAgent(
    name="reviser_agent",
    model=scholar_model,
    description=(
        "审稿专家：对论文草稿进行全面审查，从论证充分性、"
        "结构合理性、语言规范性、篇幅适当性、引用完整性和原创性"
        "六个维度进行评分，输出审稿意见和修改建议。"
        "返回 JSON 格式的审查结果，包含 passed(bool)、overall_score(0-10)、"
        "issues 列表和 action_suggestion(rewrite/revise/ok)。"
    ),
    instruction=REVISER_AGENT_PROMPT,
    output_key="review_result",
)
