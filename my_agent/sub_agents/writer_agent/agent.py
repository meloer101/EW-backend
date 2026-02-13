"""WriterAgent 定义。

WriterAgent 负责根据提纲、用户需求和参考资料，撰写论文各章节正文。
"""

from google.adk.agents import LlmAgent

from ...config import scholar_model
from .prompt import WRITER_AGENT_PROMPT


writer_agent = LlmAgent(
    name="writer_agent",
    model=scholar_model,
    description=(
        "论文写手：根据论文提纲、用户需求和参考资料，"
        "撰写高质量的学术论文正文。支持逐章节生成，"
        "使用 [[REF:ref_id]] 格式标注引用。"
        "如果收到了审稿反馈（review_result），会根据反馈修改完善内容。"
    ),
    instruction=WRITER_AGENT_PROMPT,
    output_key="draft_text",
)
