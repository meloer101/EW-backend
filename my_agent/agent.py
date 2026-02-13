"""ScholarFlow — 面向文科学生的学术写作助手。

根代理定义文件。ScholarFlowCoordinator 是用户的主要交互入口，
负责需求收集与流程编排，通过 AgentTool 调度各专业子代理完成
论文规划、知识检索、写作、审稿和格式化的完整流水线。

架构参考 draft.jpg:
  IntakeAgent → [Loop: KnowledgeAgent ↔ PlannerAgent] →
  [Loop: WriterAgent ↔ ReviserAgent] → FormatterAgent
"""

from google.adk.agents import LlmAgent
from google.adk.tools.agent_tool import AgentTool

from .config import scholar_model
from .prompt import SCHOLAR_FLOW_COORDINATOR_PROMPT
from .sub_agents.intake_agent.agent import intake_agent
from .sub_agents.planner_agent.agent import planner_agent
from .sub_agents.knowledge_agent.agent import knowledge_agent
from .sub_agents.writer_agent.agent import writer_agent
from .sub_agents.reviser_agent.agent import reviser_agent
from .sub_agents.formatter_agent.agent import formatter_agent


# ──────────────────────────────────────────────
# 根代理：ScholarFlow 协调者
# ──────────────────────────────────────────────
scholar_flow_coordinator = LlmAgent(
    name="scholar_flow_coordinator",
    model=scholar_model,
    description=(
        "ScholarFlow 学术写作助手的总协调者。"
        "负责与用户交互收集论文写作需求，并按照"
        "需求收集→论文规划→知识检索→写作→审稿→格式化的流程，"
        "调度各专业子代理完成论文生成。"
    ),
    instruction=SCHOLAR_FLOW_COORDINATOR_PROMPT,
    tools=[
        AgentTool(agent=intake_agent),
        AgentTool(agent=planner_agent),
        AgentTool(agent=knowledge_agent),
        AgentTool(agent=writer_agent),
        AgentTool(agent=reviser_agent),
        AgentTool(agent=formatter_agent),
    ],
)

# ADK 框架约定：root_agent 是入口智能体
root_agent = scholar_flow_coordinator
