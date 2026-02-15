"""GlobalReviser 定义。

GlobalReviser 负责对完整的论文草稿进行全文审查。
在内循环之外使用，接收完整的 draft_text 进行全局质量把关。
输出写入 state['review_result']。
"""

from google.adk.agents import LlmAgent

from ...config import scholar_model
from .prompt import GLOBAL_REVISER_PROMPT


global_reviser = LlmAgent(
    name="global_reviser",
    model=scholar_model,
    description=(
        "全文审稿专家：对完整论文草稿进行全面审查，"
        "从论证充分性、结构合理性、语言规范性、篇幅适当性、"
        "引用完整性、原创性和论点一致性七个维度进行评分。"
        "重点关注章节衔接、全文一致性、总字数和论点对齐等"
        "逐节审查无法覆盖的全文层面问题。"
        "输出 JSON 格式的全文审查结果，包含 passed(bool)、"
        "overall_score(0-10)、issues 列表（含 section 字段标识问题所在节或 'global'）"
        "和 action_suggestion(rewrite/revise/ok)。"
    ),
    instruction=GLOBAL_REVISER_PROMPT,
    output_key="review_result",
)
