"""KnowledgeAgent 定义。

KnowledgeAgent 负责根据论文主题和提纲，搜索并整理相关学术资料。
首轮 MVP 版本提供基础的知识整理能力。
"""

from google.adk.agents import LlmAgent

from ...config import scholar_model
from .prompt import KNOWLEDGE_AGENT_PROMPT


knowledge_agent = LlmAgent(
    name="knowledge_agent",
    model=scholar_model,
    description=(
        "学术研究员：根据论文主题和提纲，搜索整理相关学术理论、"
        "文献资料和研究成果，为论文写作提供知识支撑。"
        "输出包含核心理论、各章节参考文献和推荐资料的知识库（JSON格式）。"
    ),
    instruction=KNOWLEDGE_AGENT_PROMPT,
    output_key="knowledge_base",
)
