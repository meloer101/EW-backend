/Users/m/Documents/EW-backend/draft.jpg
draft.jpg

# ScholarFlow — 产品说明书、Vibe-Coding 指南与操作手册

**目标读者**：Cursor（Vibe coding agent）、首轮开发工程师与产品负责人
**目标**：让 Cursor 在第一次编码时尽可能完整、稳健地搭出可跑通的 MVP（面向学术写作的论文生成系统），并为后续扩展留出明确契约。
参考资料： [https://adk.wiki/](https://adk.wiki/)

---

## 一、概述（产品目标与首轮范围）

**产品定位（简短）**：面向文科学生的学术写作助手，用户可给出模糊目标（如“帮我写一篇关于人类学的论文”），系统通过多轮澄清 + 结构化规划 + 检索支撑 + 分段写作 + 引用格式化 + 审查，最终生成符合用户要求的论文。


**不在首轮范围**（后续迭代）：完善 KnowledgeAgent（RAG）、CitationAgent（完整格式化）、并发调度、前端 UI、复杂规则 DSL、并行章节写作、完整审稿策略自动化。

---

## 二、工程契约（非常重要）

为保证后续可维护、可扩展，Cursor 必须严格遵守以下契约：

1. **Agent 接口契约（必需）**：每个 Agent 接受 `InvocationContext` 与 `session.state`，只输出结构化的 **StatePatch**（JSON），绝不直接写入 Global State。

   * StatePatch 格式示例：

     ```json
     {
       "layer": "artifact",
       "patch": { "sections": {"2.1": "生成的文本..."} },
       "meta": {"agent": "WriterAgent", "task_id": "section_2.1", "success": true}
     }
     ```
2. **State 管理契约**：项目必须实现 State Manager，负责：合并 patch、快照存储、回滚、dirty flags、日志（谁写的、何时、依据哪个 task）
3. **Task Tree 契约**：任务是可序列化的对象（task.id、parent、dependencies、status、output_keys）。Task 状态变化触发规则。
4. **Rule Engine 契约**：规则为 declarative（JSON）或极简 DSL，Orchestrator 只调用规则引擎，不含判断分支逻辑。
5. **日志与审计**：每次 Agent 调用必须记录输入 state snapshot、Agent 输出 patch、耗时、LLM token 使用（若可能）。

遵守这些契约能让系统在后续增加 Agent/规则时不修改 Orchestrator。

---

## 三、核心目录结构（首轮实现建议）

```
每个子代理都单设一个文件夹，下设一个_init_.py,agent.py,prompt.py。
```

---

## 四、State Schema（v0.1 JSON）

**说明**：分四层（Config, Knowledge, Artifact, Control）。首轮实现至少实现 Config / Artifact / Control 三层，Knowledge 层可保留空结构。

```json
{
  "config": {
    "project_id": "p-123",
    "topic": "人类学：仪式研究",
    "discipline": "人类学",
    "paper_type": "课程论文",
    "language": "zh",
    "word_count": 3000,
    "citation_style": "APA"
  },
  "knowledge": {
    "references": [],           // [{id, title, authors, year, url, snippet}]
    "vector_index_meta": {}
  },
  "artifact": {
    "outline": {
      "version": 1,
      "tree": {
        "1": {"title": "引言", "children": []},
        "2": {"title": "文献综述", "children": ["2.1","2.2"]},
        "2.1": {"title": "早期研究", "children": []}
      }
    },
    "sections": {
      "1": {"text": null, "status": "pending"},
      "2.1": {"text": null, "status": "pending"}
    },
    "final_text": null
  },
  "control": {
    "current_task_id": null,
    "task_status_map": {},
    "dirty_flags": {},
    "snapshots": [],
    "last_intent": null,
    "last_action_plan": null
  }
}
```

---

## 五、Task 模型示例（首轮）

```python
class Task:
    id: str
    type: str                # e.g., "outline", "write_section", "review_section"
    parent_id: Optional[str]
    dependencies: List[str]
    output_keys: List[str]   # e.g., ['artifact.sections.1.text']
    status: str              # pending/running/succeeded/failed
    retry_count: int
```

**行为**：标记 node dirty 时只需把对应 task.status -> pending，并把关联 artifact.dirty_flags 置 true。

---

## 六、Rule Engine（首轮最小规则集合）

Rules expressed as JSON array: each rule:

```json
{
  "id": "rule_start_outline",
  "when": {
    "artifact.outline.tree": "empty"
  },
  "then": {
    "activate": ["planner_task"]
  },
  "priority": 10
}
```

首轮包含规则：

* 当 outline empty -> create planner_task（可以由 Writer 用简化 prompt 生成 outline）
* 当 section task pending & dependencies done -> activate writer_agent for that section
* 当 writer_agent outputs section -> activate reviser_agent for that section
* 当 reviser_agent returns score < threshold -> spawn rewrite task (writer) or planner_task depending issue_type

Rule Engine implementation must be simple: pattern check on state keys (dotpath) and boolean/assert comparisons.

---

## 七、Agent 规范（首轮实现：WriterAgent 与 ReviserAgent）

### 1) `base_agent.py`

* 必须包含声明字段：

  * `requires_state_keys: List[str]`
  * `produces_state_keys: List[str]`
  * `name` 与 `description`
* `run_async(ctx)` 调用 litellm_client.complete(...) 并返回 StatePatch dict.

### 2) `writer_agent.py`（职责）

* **输入（requires）**：`artifact.outline.tree`, `artifact.sections[section_id] (meta)`, `config.topic`, `knowledge.references`（可空）
* **行为**：按 section 的 outline 写出段落文本；在文本里用 `[[REF:<ref_id>]]` 占位引用。
* **输出（patch）**：`artifact.sections.<section_id>.text`, `artifact.sections.<section_id>.status = "succeeded"` 或 error meta。

**Writer Prompt（prompt/writer_prompt.txt）**（示例要精准）：

```
你是学术写作助手的段落作者。输入:
- section_id: {section_id}
- section_title: {section_title}
- section_goal: {section_goal}
- outline_context: {outline_context}
- references: {references}
请产出该段落的正文，仅输出纯正文文本（不要包含“引用”列表或标注说明），引用使用占位格式 [[REF:ref_id]]。切记：不要发明未在 references 列表中的文献。
```

### 3) `reviser_agent.py`（职责）

* **输入（requires）**：`artifact.sections.<section_id>.text`, `config` constraints
* **行为**：对段落做规则检查 + LLM 打分，分类问题类型（evidence_insufficient / structure_problem / wording_issue / length_issue）
* **输出（patch）**：`control.review_scores[section_id]`, `control.review_issues[section_id]`，并带 `action_suggestion`（"rewrite"/"ask_user"/"ok"）

**Reviser Prompt（prompts/reviser_prompt.txt）**（示例）：

```
你是论文审查专家。输入:
- text: {section_text}
- config: {word_count, citation_style, audience}
请返回 JSON:
{
  "passed": true/false,
  "score": 0-10,
  "issues": ["evidence_insufficient", ...],
  "suggestion": "rewrite" | "ask_user" | "ok"
}
```

---

## 八、Litellm 与 ADK 约定（环境与封装）

**.env（必须）**:

```
LLM_MODEL=deepseek/deepseek-chat
LLM_MODEL_API_KEY=sk-xxx
LLM_BASE_URL=https://api.deepseek.com
```

**litellm_client.py** 提供：

* `completion(messages, model, temperature)` -> returns text or structured response
* `chat_with_messages(messages)` wrapper
  封装好异常重试（指数退避），并记录 tokens if possible.

ADK:

* 使用 `Agent` 或 `BaseAgent` 按 ADK 样例创建 Agent 实例，但遵守我们 Agent 接口契约（返回 StatePatch，而 ADK 的 event stream 可以传回 patch）

参考 ADK 文档（adk.wiki）中关于 multi-agent / parent-child 的示例实现方式。

---

