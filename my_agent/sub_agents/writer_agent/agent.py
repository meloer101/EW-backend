"""WriterAgent 定义（Phase 2 升级版）。

WriterAgent 每次只写当前指定节，接收完整提纲与 compressed_context，
不读已写节的正文全文，输出写入 current_section_draft（由 SectionPassChecker 存入 draft_sections）。
"""

from google.genai import types
from google.adk.agents import LlmAgent

from ...config import scholar_model
from .prompt import WRITER_AGENT_PROMPT

# 单节最长约 3000 字 ≈ 4000+ tokens；设 6144 保证充分输出
WRITER_MAX_OUTPUT_TOKENS = 6144

writer_agent = LlmAgent(
    name="writer_agent",
    model=scholar_model,
    description=(
        "论文写手：根据完整提纲（把握整体关联）和当前节压缩上下文，"
        "每次只撰写指定的当前节正文。"
        "使用 [[REF:ref_id]] 格式标注引用。"
        "如果收到了本节审稿反馈（section_review），会针对性修改本节内容。"
    ),
    instruction=WRITER_AGENT_PROMPT,
    output_key="current_section_draft",
    generate_content_config=types.GenerateContentConfig(
        max_output_tokens=WRITER_MAX_OUTPUT_TOKENS,
    ),
)
