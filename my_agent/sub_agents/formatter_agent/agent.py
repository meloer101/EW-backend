"""FormatterAgent 定义。

FormatterAgent 负责将通过审核的论文草稿格式化为最终版本。
"""

from google.adk.agents import LlmAgent

from ...config import scholar_model
from .prompt import FORMATTER_AGENT_PROMPT


formatter_agent = LlmAgent(
    name="formatter_agent",
    model=scholar_model,
    description=(
        "格式化专家：将通过审核的论文草稿格式化为最终版本。"
        "处理引用格式替换（将 [[REF:ref_id]] 转为正规引文格式），"
        "生成参考文献列表，统一排版格式，"
        "输出用户可以直接使用的完整 Markdown 格式论文。"
    ),
    instruction=FORMATTER_AGENT_PROMPT,
    output_key="final_paper",
)
