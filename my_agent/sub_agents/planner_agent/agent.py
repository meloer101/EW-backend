"""PlannerAgent 定义。

PlannerAgent 负责根据用户需求和可用知识，创建和完善论文提纲。
"""

from google.adk.agents import LlmAgent

from ...config import scholar_model
from .prompt import PLANNER_AGENT_PROMPT


planner_agent = LlmAgent(
    name="planner_agent",
    model=scholar_model,
    description=(
        "论文架构师：根据用户需求和可用的参考资料，"
        "创建详细的论文提纲（JSON格式），包含各章节标题、内容要点和字数分配。"
    ),
    instruction=PLANNER_AGENT_PROMPT,
    output_key="paper_outline",
)
