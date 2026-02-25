"""EmailAgent 定义。

EmailAgent 负责将格式化完成的论文通过邮件发送给用户。
使用自定义 FunctionTool 从 session state 读取 final_paper 并调用 AgentMail API 发送，
避免由 LLM 在工具参数中传入长文导致的 JSON 截断或转义错误。
"""

from google.adk.agents import LlmAgent

from ...config import scholar_model
from .prompt import EMAIL_AGENT_PROMPT
from .send_paper_tool import send_paper_to_email_tool


email_agent = LlmAgent(
    name="email_agent",
    model=scholar_model,
    description=(
        "邮件发送专员：将当前会话中的最终论文（final_paper）发送到用户指定邮箱。"
        "只需用户提供收件人邮箱，论文内容由系统自动读取并发送。"
    ),
    instruction=EMAIL_AGENT_PROMPT,
    tools=[send_paper_to_email_tool],
)
