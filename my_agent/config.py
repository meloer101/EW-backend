"""ScholarFlow 全局配置模块。

集中管理模型配置和其他共享设置，供所有 Agent 使用。
"""

import os

from google.adk.models.lite_llm import LiteLlm


# ──────────────────────────────────────────────
# LLM 模型配置（使用 LiteLlm 作为转换层）
# ──────────────────────────────────────────────
scholar_model = LiteLlm(
    model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
    api_key=os.getenv("LLM_MODEL_API_KEY", ""),
    api_base=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
)

# ──────────────────────────────────────────────
# 应用常量
# ──────────────────────────────────────────────
APP_NAME = "scholar_flow"

# AgentMail 邮件发送（email_agent）：在 .env 中配置
# AGENTMAIL_API_KEY - 必填；AGENTMAIL_INBOX_ID - 发件箱地址，可选，默认 m@agentmail.to
