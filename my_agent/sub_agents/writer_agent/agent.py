"""WriterAgent 定义。

WriterAgent 负责根据提纲、用户需求和参考资料，按节撰写论文正文。
每次调用仅撰写 current_section_id 指定的一个 section，
输出写入 state['current_section_draft']。
"""

from google.adk.agents import LlmAgent

from ...config import scholar_model
from .prompt import WRITER_AGENT_PROMPT


writer_agent = LlmAgent(
    name="writer_agent",
    model=scholar_model,
    description=(
        "论文写手：按节撰写论文正文。每次调用根据 current_section_id "
        "撰写指定节的内容，参考提纲（paper_outline）、知识库（knowledge_base）"
        "和已完成的节（draft_sections）保持上下文衔接。"
        "如果有审稿反馈（section_review_result 或 review_result），"
        "会根据反馈修改本节内容。"
        "使用 [[REF:ref_id]] 格式标注引用。"
    ),
    instruction=WRITER_AGENT_PROMPT,
    output_key="current_section_draft",
)
