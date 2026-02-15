"""ScholarFlow 工作流流水线定义。

包含：
- planning_pipeline: LoopAgent，循环执行 knowledge + planner 直到大纲完整。
- writing_pipeline: LoopAgent，先初始化写作状态（提纲第一节为 current_section_id），
  再循环执行 writer + reviser 直到所有节完成。
"""

from google.adk.agents import LoopAgent

# 导入子代理
from my_agent.sub_agents.knowledge_agent import knowledge_agent
from my_agent.sub_agents.planner_agent import planner_agent
from my_agent.sub_agents.writer_agent import writer_agent
from my_agent.sub_agents.section_reviser import section_reviser
from my_agent.sub_agents.section_storage import section_storage_agent

# 导入流控与入口初始化
from .outline_completion_checker import outline_completion_checker
from .section_pass_checker import section_pass_checker
from .writing_phase_initializer import writing_phase_initializer


# 规划流水线：知识收集 → 大纲生成 → 完整性检查 → (循环或退出)
planning_pipeline = LoopAgent(
    name="planning_pipeline",
    description="循环执行知识收集和大纲生成，直到大纲完整。",
    max_iterations=5,  # 防止无限循环
    sub_agents=[
        knowledge_agent,
        planner_agent,
        outline_completion_checker,
    ],
)


# 写作流水线：先初始化（提纲第一节 → current_section_id）→ 写节 → 审稿 → 流控 → 存储
writing_pipeline = LoopAgent(
    name="writing_pipeline",
    description="先确保写作状态已根据提纲初始化（第一节为 current_section_id），再循环执行分节写作和审稿。",
    max_iterations=100,  # 应对多节 + 多次修订
    sub_agents=[
        writing_phase_initializer,
        writer_agent,
        section_reviser,
        section_pass_checker,
        section_storage_agent,
    ],
)
