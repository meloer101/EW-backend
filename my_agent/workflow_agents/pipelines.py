"""ScholarFlow 写作流水线定义（Phase 2）。

writing_pipeline：按节写作（Initializer → Loop[MemoryBuilder→Writer→SectionReviser→PassChecker] → Concatenator）
consistency_pipeline：一致性修补（ConsistencyReviser → PatchInit → Loop[Controller→Patcher→Storer] → Concatenator）

两个 pipeline 均封装为 SequentialAgent，可被根协调者以 AgentTool 形式调用。
"""

from google.adk.agents import LoopAgent, SequentialAgent

from .writing_phase_initializer import WritingPhaseInitializer
from .section_memory_builder import SectionMemoryBuilder
from .section_pass_checker import SectionPassChecker
from .section_concatenator import SectionConcatenator
from .patch_initializer import PatchInitializer
from .patch_controller import PatchController
from .patch_storer import PatchStorer

from ..sub_agents.writer_agent.agent import writer_agent
from ..sub_agents.section_reviser_agent.agent import section_reviser_agent
from ..sub_agents.consistency_reviser_agent.agent import consistency_reviser_agent
from ..sub_agents.local_patcher_agent.agent import local_patcher_agent

# ──────────────────────────────────────────────────────────────
# writing_pipeline
# ──────────────────────────────────────────────────────────────
#
# 流程：
#   1. WritingPhaseInitializer  — 从 paper_outline 初始化 section_order 等 state
#   2. writing_loop (LoopAgent) — 按节循环写作（最多 60 次迭代，支持 20 节 × 3 次重试）
#      a. SectionMemoryBuilder  — 构建当前节 compressed_context（无 LLM，纯逻辑）
#      b. writer_agent          — 只写当前节，输出 current_section_draft
#      c. section_reviser_agent — 审稿当前节，输出 section_review
#      d. SectionPassChecker    — 若通过：保存草稿、推进节索引或 escalate；若未通过：继续循环
#   3. SectionConcatenator      — 按 section_order 拼接 draft_sections → draft_text
#
# 写完后 state 中有：
#   - draft_sections: {section_id: str, ...}（各节正文）
#   - draft_text: str（拼接全文，供 GlobalReviser / Formatter 消费）

writing_pipeline = SequentialAgent(
    name="writing_pipeline",
    description=(
        "按节写作流水线：将完整论文提纲拆分为节，逐节调用 Writer 写作并经 SectionReviser 审核，"
        "通过后保存草稿，最终拼接为完整 draft_text。"
        "支持万字级论文，通过 compressed_context 控制每节的 token 消耗。"
    ),
    sub_agents=[
        WritingPhaseInitializer(name="writing_phase_initializer"),
        LoopAgent(
            name="writing_loop",
            # 20 节 × 每节最多 3 次重试 = 60；可根据提纲规模适当调整
            max_iterations=60,
            sub_agents=[
                SectionMemoryBuilder(name="section_memory_builder"),
                writer_agent,
                section_reviser_agent,
                SectionPassChecker(name="section_pass_checker"),
            ],
        ),
        SectionConcatenator(name="section_concatenator"),
    ],
)

# ──────────────────────────────────────────────────────────────
# consistency_pipeline
# ──────────────────────────────────────────────────────────────
#
# 流程（在 writing_pipeline 完成后调用）：
#   1. consistency_reviser_agent — 读 draft_text + paper_outline，输出 modification_instructions
#   2. PatchInitializer          — 解析指令列表，初始化 patch_queue
#   3. patch_loop (LoopAgent)    — 逐条执行修改指令（最多 30 次迭代）
#      a. PatchController        — 取出当前指令、当前节文本，或 escalate 退出
#      b. local_patcher_agent    — 对单节做局部修补，输出 patched_section_text
#      c. PatchStorer            — 保存修补结果，推进 patch_idx
#   4. SectionConcatenator       — 重新拼接修补后的 draft_sections → draft_text
#
# 运行后 draft_text 为修补后的全文，可继续交 GlobalReviser 做终审。

consistency_pipeline = SequentialAgent(
    name="consistency_pipeline",
    description=(
        "全文一致性修补流水线：先对 draft_text 做跨节一致性审查，产出结构化修改指令，"
        "再按指令逐节做局部修补（不整篇重写），最终重新拼接为修补后的 draft_text。"
        "处理术语不一致、重复论点、引用格式、风格一致性和逻辑衔接问题。"
    ),
    sub_agents=[
        consistency_reviser_agent,
        PatchInitializer(name="patch_initializer"),
        LoopAgent(
            name="patch_loop",
            # 每条指令一次迭代；设 30 上限足够处理 20 节内的指令
            max_iterations=30,
            sub_agents=[
                PatchController(name="patch_controller"),
                local_patcher_agent,
                PatchStorer(name="patch_storer"),
            ],
        ),
        SectionConcatenator(name="patch_concatenator"),
    ],
)
