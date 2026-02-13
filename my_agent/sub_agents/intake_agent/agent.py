"""IntakeAgent 定义。

IntakeAgent 负责接收用户的模糊输入，通过结构化分析将其转化为
明确的论文写作需求配置，存入 session state。
"""

from google.adk.agents import LlmAgent

from ...config import scholar_model
from .prompt import INTAKE_AGENT_PROMPT


intake_agent = LlmAgent(
    name="intake_agent",
    model=scholar_model,
    description=(
        "需求分析师：接收用户的模糊论文写作需求，通过结构化分析，"
        "输出完整的写作需求配置（JSON格式，包含主题、学科、类型、字数、引用格式等）。"
    ),
    instruction=INTAKE_AGENT_PROMPT,
    output_key="user_requirements",
)
