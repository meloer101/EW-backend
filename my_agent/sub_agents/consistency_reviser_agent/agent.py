"""ConsistencyReviserAgent 定义（Phase 2 Phase B）。

全文一致性检查代理：读取 draft_text 和 paper_outline，
输出结构化修改指令列表（modification_instructions）供 Local Patcher 消费。
"""

from google.adk.agents import LlmAgent

from ...config import scholar_model
from .prompt import CONSISTENCY_REVISER_AGENT_PROMPT


consistency_reviser_agent = LlmAgent(
    name="consistency_reviser_agent",
    model=scholar_model,
    description=(
        "全文一致性审查专家：检查跨章节的术语、重复论点、引用格式、"
        "风格和逻辑衔接问题，输出结构化修改指令列表（JSON 格式），"
        "供 Local Patcher 对指定节做局部修补。"
    ),
    instruction=CONSISTENCY_REVISER_AGENT_PROMPT,
    output_key="modification_instructions",
)
