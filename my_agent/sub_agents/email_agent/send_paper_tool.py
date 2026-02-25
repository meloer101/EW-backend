"""发送论文邮件的 FunctionTool。

论文正文从 session state 的 final_paper 读取，不通过 LLM 传参，避免长文本导致
JSON 截断或转义错误。工具只接收 to_email 与可选 subject。
"""

import os
from typing import Any

from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.tool_context import ToolContext


def _get_agentmail_client():
    """延迟初始化 AgentMail 客户端（按需 import）。"""
    try:
        from agentmail import AgentMail
    except ImportError:
        raise RuntimeError(
            "发送邮件需要安装 agentmail，请执行: pip install agentmail"
        )
    api_key = os.getenv("AGENTMAIL_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("未配置 AGENTMAIL_API_KEY，请在 .env 中设置")
    return AgentMail(api_key=api_key)


def send_paper_to_email(
    to_email: str,
    subject: str = "",
    tool_context: ToolContext = None,  # 由 ADK 注入，不暴露给 LLM
) -> dict[str, Any]:
    """将当前会话中的最终论文（final_paper）发送到指定邮箱。

    论文内容从 session state 的 final_paper 自动读取，无需在参数中传入。
    适用于长论文，避免工具参数过长导致错误。

    Args:
        to_email: 收件人邮箱地址。
        subject: 邮件主题，可选。若为空则使用默认主题。
        tool_context: ADK 注入的上下文，用于读取 session state（勿由调用方传入）。

    Returns:
        包含 success 与 message 或 error 的字典，供 agent 回复用户。
    """
    if not to_email or not str(to_email).strip():
        return {"error": "请提供有效的收件人邮箱地址。"}
    if tool_context is None:
        return {"error": "工具上下文不可用，无法读取论文内容。"}

    final_paper = (tool_context.state.get("final_paper") or "").strip()
    if not final_paper:
        return {
            "error": "当前会话中没有可发送的论文内容（final_paper 为空）。请先完成格式化阶段再发送邮件。"
        }

    inbox_id = os.getenv("AGENTMAIL_INBOX_ID", "m@agentmail.to").strip()
    if not inbox_id:
        return {"error": "未配置发件箱 AGENTMAIL_INBOX_ID。"}

    mail_subject = (subject or "您的学术论文 - ScholarFlow").strip()
    # 纯文本：直接使用全文；HTML：简单包裹便于阅读
    text_body = final_paper
    html_body = f"<pre style=\"white-space: pre-wrap; font-family: inherit;\">{_escape_html(final_paper)}</pre>"

    try:
        client = _get_agentmail_client()
        client.inboxes.messages.send(
            inbox_id=inbox_id,
            to=[str(to_email).strip()],
            subject=mail_subject,
            text=text_body,
            html=html_body,
        )
    except Exception as e:
        return {
            "error": f"发送失败：{getattr(e, 'message', str(e))}。请检查 AGENTMAIL_API_KEY 与发件箱配置。"
        }

    return {
        "success": True,
        "message": f"论文已成功发送至 {to_email}，主题：{mail_subject}。",
    }


def _escape_html(s: str) -> str:
    """将文本中与 HTML 冲突的字符转义。"""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# 供 agent 使用的工具实例；LLM 只需传 to_email、subject，不传论文内容
send_paper_to_email_tool = FunctionTool(send_paper_to_email)
