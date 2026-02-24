"""LocalPatcherAgent 定义（Phase 2 Phase B）。

根据 current_patch_instruction 和 current_patch_section_text，
对指定节做局部修补，输出修补后的完整节正文到 patched_section_text。
"""

from google.genai import types
from google.adk.agents import LlmAgent

from ...config import scholar_model
from .prompt import LOCAL_PATCHER_AGENT_PROMPT

# 单节修补输出与写作相近，设 6144 tokens 足够
LOCAL_PATCHER_MAX_OUTPUT_TOKENS = 6144

local_patcher_agent = LlmAgent(
    name="local_patcher_agent",
    model=scholar_model,
    description=(
        "局部修补专家：根据一条具体的修改指令，对指定节的正文做精准局部修补，"
        "输出修补后的完整节正文（patched_section_text）。"
        "处理术语不一致、重复论点、引用格式、风格一致性和逻辑衔接等问题。"
    ),
    instruction=LOCAL_PATCHER_AGENT_PROMPT,
    output_key="patched_section_text",
    generate_content_config=types.GenerateContentConfig(
        max_output_tokens=LOCAL_PATCHER_MAX_OUTPUT_TOKENS,
    ),
)
