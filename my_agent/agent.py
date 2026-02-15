"""ScholarFlow — 面向文科学生的学术写作助手。

根代理定义文件。ScholarFlowCoordinator 是用户的主要交互入口，
负责与用户对话、判断用户意图、管理阶段切换，并通过工作流代理
（LoopAgent / SequentialAgent）驱动固定流程的子任务执行。

第二阶段架构（显式状态机 + 工作流驱动）：
  1. 对话阶段：IntakeAgent 收集需求
  2. 规划阶段：planning_pipeline (LoopAgent: knowledge ↔ planner)
  3. 写作阶段：writing_pipeline (LoopAgent: writer → reviser → checker → storage)
  4. 全文审稿：GlobalReviser 评审 + 定向修订
  5. 格式化：FormatterAgent 输出最终论文

核心改进：
- 协调者 LLM 仅负责对话和阶段判断，不再微观调度每个工具
- 规划和写作由 LoopAgent 内部按固定顺序执行，流控由自定义 Checker 完成
- 状态显式化：session.state["phase"] 标记当前阶段
- 可观测性：每个阶段/子代理输入输出明确，便于监控和调试

工作流代理：2 个（planning_pipeline / writing_pipeline）
独立子代理：3 个（Intake / GlobalReviser / Formatter）
阶段管理工具：4 个（init_planning_phase / init_writing_phase /
              get_phase_status / set_phase）
"""

from google.adk.agents import LlmAgent
from google.adk.tools.agent_tool import AgentTool

from .config import scholar_model
from .prompt import SCHOLAR_FLOW_COORDINATOR_PROMPT
from .sub_agents.intake_agent.agent import intake_agent
from .sub_agents.global_reviser.agent import global_reviser
from .sub_agents.formatter_agent.agent import formatter_agent
from .workflow_agents.pipelines import planning_pipeline, writing_pipeline
from .phase_tools import (
    init_planning_phase,
    init_writing_phase,
    get_phase_status,
    set_phase,
)


# ──────────────────────────────────────────────
# 根代理：ScholarFlow 协调者
# ──────────────────────────────────────────────
scholar_flow_coordinator = LlmAgent(
    name="scholar_flow_coordinator",
    model=scholar_model,
    description=(
        "ScholarFlow 学术写作助手的总协调者。"
        "负责与用户对话、理解意图、确认阶段，并调用工作流代理"
        "（planning_pipeline / writing_pipeline）和独立子代理"
        "（IntakeAgent / GlobalReviser / FormatterAgent）完成论文生成。"
        "采用显式状态机设计：phase 字段标记当前阶段，"
        "阶段内部由 LoopAgent 按固定流程执行。"
    ),
    instruction=SCHOLAR_FLOW_COORDINATOR_PROMPT,
    tools=[
        # 3 个独立子代理
        AgentTool(agent=intake_agent),
        AgentTool(agent=global_reviser),
        AgentTool(agent=formatter_agent),
        # 2 个工作流代理（LoopAgent）
        AgentTool(agent=planning_pipeline),
        AgentTool(agent=writing_pipeline),
        # 4 个阶段管理工具
        init_planning_phase,
        init_writing_phase,
        get_phase_status,
        set_phase,
    ],
)

# ADK 框架约定：root_agent 是入口智能体
root_agent = scholar_flow_coordinator
