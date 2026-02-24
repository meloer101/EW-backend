# ScholarFlow 论文编译器升级计划（Phase 2）

本文档在「按节撰写 + 双 Reviser」的基础上，面向**万字级论文**与**可编排的多阶段构建**，给出「论文编译器」模型的完备升级思路与实施计划。不替代 [phase1-upgrade-plan.md](phase1-upgrade-plan.md)，与之衔接并可分阶段落地。

---

## 一、升级动因与目标

### 1.1 问题

- **单次生成长度上限**：即便提高 `max_output_tokens`，万字论文（约 1.5 万+ tokens）仍会触及模型/API 上限，单次「整篇生成」不可行。
- **全文塞给 Writer 的代价**：若按节写但每节都把「全文已写部分」塞进 context，随节数增加会爆上下文，且重复传输成本高。
- **全文一次性审稿/重写**：GlobalReviser 若对万字稿做「全文重写」建议或执行，同样会爆 token，且难以做细粒度、可局部修补的反馈。

### 1.2 目标

1. **任务拆解**：将论文拆成带元数据的「节」单元，对每个单元标注目标、长度、依赖等，由 Writer 与 Reviser 按节编写与评价，再汇总。
2. **记忆压缩**：写某一节时，不把前文全文塞给 Writer，而是用**压缩上下文**（全文 thesis 摘要、前文关键结论摘要、术语表、本节目标与长度预算）模拟「长时记忆压缩」。
3. **一致性关口**：全部节写完后不做「直接拼接即交付」，而是增加**一致性检查**（术语、重复论点、引用、风格），输出**修改指令**，再**局部修补**，避免整篇重写。
4. **可编排构建**：整体视为 **DAG + 记忆压缩 + 迭代精修** 的多阶段流程，而不是单次生成。

---

## 二、目标架构：四层「论文编译器」模型

采用你提出的「宏观规划 → 中观结构 → 微观写作 → 一致性关口」四层结构，并与现有 ADK 能力对齐。

### 2.1 第一层：宏观规划层 —— Planner Agent（prompt 升级）

**职责**：由现有 **Planner Agent** 承担，只做一件事——产出**机器可读的论文结构树**，不是自然语言大纲。**不新增独立 Architect 代理**，通过 **Planner 的 prompt 升级** 即可。

**输出形态**：纯 JSON，可视为「论文蓝图」，供后续所有层消费。在现有 Schema v2 上通过 **Planner prompt** 扩展，要求产出以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `section_id` | string | 稳定主键（建议后续改为 UUID，短期可与 display_number 一致） |
| `display_number` | string | 展示用编号，如 "1", "2.1" |
| `title` | string | 节标题 |
| `section_goal` | string | 本节写作目标/要点（与现有 `goal` 对齐） |
| `required_arguments` | string[] | 本节必须覆盖的论证点（可选，machine-readable） |
| `required_evidence` | string[] | 本节建议引用的证据/文献类型（可选） |
| `tone` | string | 本节语气：formal / accessible / critical 等，可与 metadata 继承 |
| `length_budget` | number | 本节字数预算（与现有 `word_count` 对齐） |
| `dependencies` | string[] | 依赖的 section_id 列表（用于未来 DAG 排序或校验） |

**与现有 phase1 的关系**：phase1 的 Planner 已产出扁平 `sections` + `thesis_statement`、`total_word_count`、`metadata`。本层在 **同一 Planner Agent** 的 prompt 中明确要求输出上述扩展字段（required_arguments、required_evidence、tone、dependencies），保证全局唯一可解析、可排序、可依赖。

**关键点**：此层是「全局记忆的替代品」——后续层只依赖这份机器可读 JSON，无需再解析自然语言大纲。

---

### 2.2 第二层：中观结构层 —— Section Memory Builder（压缩上下文）

**职责**：在写**某一节之前**，动态构建该节所需的「压缩上下文」，而不是把前文**正文全文**塞给 Writer。前文结构与关键意图由**完整提纲**提供，无需对已写正文再做摘要。

**压缩上下文内容建议**：

| 内容 | 说明 | 来源 |
|------|------|------|
| **thesis_summary** | 全文核心论点/研究问题的一句话或短段摘要 | `paper_outline.thesis_statement`（+ 可选 1–2 句扩展） |
| **paper_outline（完整提纲）** | 全文结构及各节目标/要点，用作「前文与整体」的替代 | 直接使用 `paper_outline`，不另做摘要 |
| **terminology_glossary** | 全文关键术语表（可选，避免概念漂移） | 从 outline / metadata 中抽取，或由轻量逻辑维护 |
| **current_section_spec** | 当前节的完整规格 | 从 `paper_outline.sections[current_section_id]` 取 goal、length_budget、required_arguments 等 |

**设计取舍**：**不**对 `draft_sections[已完成的 section_id]` 做 LLM 摘要（即不引入 Summarizer Agent）。理由：摘要会额外消耗 token 与延迟，且提纲本身已包含各节的 title、section_goal 等，足以让 Writer 把握前文在全文中的位置与逻辑关系；用**整体 outline 作为前文结构/关键结论的替代**即可，在控制 token 与速度的前提下保持整体性。

**实现方式**：

- **不新建 Summarizer Agent**。Section Memory Builder 为**无 LLM 的纯逻辑**：从 state 读取 `paper_outline`、`current_section_id`，拼装 `compressed_context`（thesis_summary、current_section_spec、可选 terminology_glossary）；**同时**将完整 `paper_outline` 单独提供给 Writer（见 2.3），不塞入 compressed_context 以保持结构清晰。
- 术语表（若保留）：可从 outline 的 section_goal / metadata 中抽取关键词，或由后续一致性层维护；随节递增更新可选。

**与 phase1 的差异**：phase1 的 Writer 输入包含 `draft_sections`（已写节**正文**全文）。本层改为 Writer **不**读已写节的正文全文，只读**完整提纲 paper_outline**（把握整体关联）+ **compressed_context**（thesis_summary、current_section_spec 等），从而控制 token、支持万字级。

---

### 2.3 第三层：微观写作层 —— Writer Agent（局部生成）

**职责**：**只做指定部分的撰写**，每次仅输出当前节正文；但**依然接收完整提纲**，以把握论文论述的**整体性关联**。

**输入（来自 state）**：

- **`paper_outline`（完整提纲）**：全文结构、各节 title / section_goal / length_budget 等。Writer **始终接收完整提纲**，便于理解前文与后文在全文中的位置与逻辑关系，保证论述连贯。
- `compressed_context`：含 `thesis_summary`、`current_section_spec`（当前节 goal、length_budget、required_arguments、tone 等），可选 `terminology_glossary`。
- `knowledge_base`（本节可引用的资料）
- `user_requirements`（学科、引用格式等）

**不注入**：`draft_sections`（已写节的**正文全文**），以避免随节数增长爆 token；前文「写了什么」通过提纲中各节的 section_goal / title 来把握即可。

**输出**：与 phase1 一致——**仅当前节正文**，写入 `draft_sections[section_id]`。

**与 phase1 的差异**：Writer 仍读**完整 paper_outline**，但**不再**读完整 `draft_sections`（已写节正文）；只读提纲 + 压缩上下文 + 知识库 + 用户需求。这样既控制 token（不传长文前稿），又保持整体性（提纲可见）。

---

### 2.4 第四层：一致性关口 —— Consistency Pass（指令式修订 + 局部修补）

**职责**：全部节写完后，**不直接拼接即交付**，而是先做一致性检查，产出**修改指令**，再**仅对涉及节做局部修补**，避免整篇重写导致再次爆 token。

**一致性检查维度**（与你描述对齐）：

- **术语一致性**：同一概念在不同节中的表述是否统一。
- **重复论点检测**：不同节是否重复论证同一观点。
- **引用统一**：引用格式、参考文献列表是否一致。
- **风格统一**：语气、人称、时态等是否与 metadata 要求一致。

**实现形态**：

- **Consistency Reviser Agent**（可复用或扩展 GlobalReviser）：  
  - **输入**：全文摘要（thesis_summary + 各节摘要）、各节正文（`draft_sections`）、一致性规则描述（术语表、引用格式等）。  
  - **输出**：**修改指令列表**，而非重写全文。例如：  
    `{ "section_id": "2.1", "issue_type": "terminology", "location": "第二段首句", "instruction": "将「XXX」改为与术语表一致的「YYY」" }`  
    或：  
    `{ "section_id": "3", "issue_type": "duplicate_argument", "instruction": "删除与 2.2 节重复的论点，仅保留一处展开" }`  
  - 这样 Reviser 的输出是「短指令」，token 可控；下游只对指定 section 做**局部修补**。

- **Local Patcher**：根据指令列表，对 `draft_sections[section_id]` 做修订。可以：  
  - 再调一次 **Writer**，但输入仅为「该节当前正文 + 本条修改指令」，要求只做局部修改并返回**整节修订版**（单节 token 可控）；或  
  - 若 ADK 支持，用轻量「修补」工具（如只替换某段）减少 token。  
  - 修补完成后更新 `draft_sections`，可选择性再跑一次 Consistency Reviser（仅对修改过的节或全文摘要再检查），迭代 1–2 轮即可。

**与 phase1 GlobalReviser 的关系**：phase1 的 GlobalReviser 输出 `review_result`（passed、issues、action_suggestion）。可扩展为：当 `action_suggestion` 为 "revise" 且 issues 为「一致性类」时，将 issues 转为上述**修改指令**格式，走「Consistency Reviser → Local Patcher」流程；若为「结构性/论证性」大改，再走「定点重写整节」或「全文重写」逻辑（此时仍按节写，不一次生成全文）。

---

## 三、整体流程：DAG + 记忆压缩 + 迭代精修

### 3.1 流程概览

```
用户确认需求
      ↓
[ 第一层 ] Planner Agent（prompt 升级）
      → 输出：paper_outline (JSON 结构树，含 section_id, section_goal, length_budget, dependencies, ...)
      ↓
按 dependencies / display_number 确定写作顺序
      ↓
┌─────────────────────────────────────────────────────────────────────────┐
│ 对每个 section_id（按顺序）：                                              │
│                                                                         │
│   [ 第二层 ] Section Memory Builder                                      │
│        → 输入：paper_outline, current_section_id                         │
│        → 拼装 compressed_context（thesis_summary, current_section_spec 等）│
│        → 不调用 Summarizer，不以 draft_sections 做摘要                     │
│        → 写入 state                                                      │
│                                                                         │
│   [ 第三层 ] Writer                                                      │
│        → 输入：完整 paper_outline + compressed_context + knowledge_base  │
│        → 输出：本节正文 → draft_sections[section_id]                      │
│                                                                         │
│   SectionReviser(本节) → local_review                                     │
│        → 未通过则重试 Writer(本节)，最多 N 轮                              │
└─────────────────────────────────────────────────────────────────────────┘
      ↓
拼接 draft_sections → draft_text
      ↓
[ 第四层 ] Consistency Reviser
      → 输入：thesis_summary, 各节摘要或提纲, draft_sections, 一致性规则
      → 输出：modification_instructions[]（section_id, issue_type, instruction）
      ↓
Local Patcher：按指令对指定 section 做局部修补，更新 draft_sections
      ↓
（可选）再跑一次 Consistency Reviser，迭代 1–2 轮
      ↓
GlobalReviser(全文审稿，与 phase1 一致) → 通过则 Formatter → 交付
      ↓
若未通过：定点重写指定节 或 全文按节重写（仍不整篇一次生成）
```

### 3.2 DAG 与依赖

- **dependencies** 在结构树中可选：若某节依赖「2.1 完成后再写 2.2」，可在排序时按 dependencies 做拓扑排序；当前 phase1 已按 `display_number` 线性排序，可视为 DAG 的特例（全序）。
- 后续若支持「并行写互不依赖的节」，可基于 dependencies 生成并行组，由协调层或工作流调度多分支，ADK 可用多 Agent 并行或顺序 Loop 实现。

### 3.3 记忆压缩与 token 控制

- Writer 每节输入：**完整 paper_outline**（结构树，篇幅受节数限制但远小于「已写正文全文」）+ compressed_context（thesis_summary、current_section_spec、可选 terminology_glossary）+ knowledge_base + user_requirements。  
- **不**传入已写节的正文 `draft_sections`，前文与整体关联通过**提纲**（各节 title、section_goal）把握，既控制 token又保持论述整体性。无需 Summarizer，无额外延迟与摘要 token 消耗。

### 3.4 迭代精修

- **节内迭代**：SectionReviser 不通过 → 同节重写（已有）。
- **全文一致性迭代**：Consistency Reviser → 修改指令 → Local Patcher → 可选再检。
- **全文质量迭代**：GlobalReviser 不通过 → 定点重写或全文按节重写（仍用压缩上下文 + 按节写），避免单次「整篇重写」爆 token。

---

## 四、与现有实现及 ADK/Resource 的衔接

### 4.1 与 phase1-upgrade-plan 的对应关系

| phase1 已有 | 本计划（Phase 2 编译器） |
|-------------|---------------------------|
| Planner 输出 Schema v2（扁平 sections + goal, word_count） | 第一层：**仍由 Planner Agent** 产出，通过 **prompt 升级** 扩展为带 required_arguments、required_evidence、tone、dependencies 的机器可读结构树；不新增 Architect |
| Writer 按 section_id 写，读 draft_sections | 第三层：Writer **仍读完整 paper_outline**（把握整体关联），但**不**读已写节正文 draft_sections；读 compressed_context + knowledge_base |
| SectionReviser 逐节审 | 不变，仍在内循环中 |
| GlobalReviser 全文审、issues 含 section_id | 第四层：增加 **Consistency Reviser** 产出修改指令 + **Local Patcher** 做局部修补；GlobalReviser 仍可保留做「全文质量+结构性」终审 |
| draft_sections → 拼接 → draft_text | 不变；Consistency Pass 在拼接后、或对 draft_sections 按节检查后再拼接 |
| 协调层 / 工作流（LoopAgent）按节调用 Writer → Reviser | 中间插入 **Section Memory Builder** 步骤（每节写前从 outline 拼装 compressed_context，**不调用 Summarizer**） |

### 4.2 与 ADK 的对应关系

- **LoopAgent / SequentialAgent**（参考 deep-search）：内循环「Section Memory Builder → Writer → SectionReviser」可放在同一 LoopAgent 内；外层 SequentialAgent 可为「Planner → [Loop: Builder→Writer→Reviser] → 拼接 → Consistency Reviser → Local Patcher → GlobalReviser → Formatter」。
- **State**：新增或复用 state key，例如 `compressed_context`、`terminology_glossary`、`modification_instructions`；`paper_outline` 扩展为上述结构树（由 Planner 产出）。Writer 读完整 `paper_outline`，不读 `draft_sections` 正文。
- **自定义 BaseAgent**：Section Memory Builder 为**无 LLM 的纯逻辑**（从 paper_outline + current_section_id 拼装 compressed_context，不调用 Summarizer）；Local Patcher 可以是调用 Writer 的「单节修订」模式或小型 Patcher 工具。
- **EscalationChecker 模式**（deep-search）：可用于「本节通过才进入下一节」的流控，与 phase1 的 SectionPassChecker 思路一致。

### 4.3 与 resource/deep-search 的参考点

- **research_pipeline**：SequentialAgent(section_planner → section_researcher → LoopAgent(evaluator → EscalationChecker → enhanced_search_executor) → report_composer)。可类比为：Planner → [Loop: Section Memory Builder → Writer → SectionReviser（+ Escalation/PassChecker）] → 拼接 → Consistency Reviser → Local Patcher → GlobalReviser → Formatter。
- **after_agent_callback**：用于从事件中抽取 grounding、写入 state 等；Section Memory Builder 将 compressed_context 写回 state 供 Writer 读取。

---

## 五、数据契约（建议）

### 5.1 论文结构树（第一层输出）

在 phase1 Schema v2 基础上扩展，例如：

```json
{
  "outline_version": 2,
  "title": "...",
  "thesis_statement": "...",
  "total_word_count": 10000,
  "metadata": { ... },
  "sections": {
    "1": {
      "id": "1",
      "display_number": "1",
      "title": "引言",
      "section_goal": "研究背景、问题提出、研究意义、方法概述",
      "required_arguments": ["研究问题", "研究意义", "方法概述"],
      "required_evidence": ["领域综述", "问题陈述"],
      "tone": "formal",
      "length_budget": 800,
      "dependencies": [],
      "status": "pending",
      "local_review": null,
      "versions": []
    },
    "2.1": {
      "id": "2.1",
      "display_number": "2.1",
      "title": "早期研究",
      "section_goal": "...",
      "required_arguments": ["时间线", "代表学者", "核心观点"],
      "required_evidence": ["经典文献"],
      "tone": "formal",
      "length_budget": 1200,
      "dependencies": ["2"],
      "status": "pending",
      "local_review": null,
      "versions": []
    }
  }
}
```

### 5.2 压缩上下文（第二层输出，供第三层消费）

Writer 同时接收**完整 paper_outline**（见 5.1）与本节 **compressed_context**。compressed_context 示例：

```json
{
  "thesis_summary": "本文探讨……（1–3 句，来自 paper_outline.thesis_statement）",
  "terminology_glossary": [
    { "term": "功能主义", "definition": "……" },
    { "term": "田野调查", "definition": "……" }
  ],
  "current_section_spec": {
    "section_id": "2.1",
    "title": "早期研究",
    "section_goal": "...",
    "length_budget": 1200,
    "required_arguments": ["时间线", "代表学者", "核心观点"],
    "tone": "formal"
  }
}
```

**说明**：前文与整体关联由 Writer 所读的**完整 paper_outline** 提供，无需在此处包含 previous_sections_summary。

### 5.3 一致性修改指令（第四层输出，供 Local Patcher 消费）

```json
{
  "modification_instructions": [
    {
      "section_id": "2.1",
      "issue_type": "terminology",
      "location": "第二段首句",
      "instruction": "将「XXX」改为与术语表一致的「YYY」"
    },
    {
      "section_id": "3",
      "issue_type": "duplicate_argument",
      "instruction": "删除与 2.2 节重复的论点，仅保留 2.2 中的展开"
    }
  ],
  "overall_consistency_passed": false
}
```

---

## 六、实施阶段建议

### 阶段 A：结构树与压缩上下文（不破坏现有 phase1）

1. **扩展 paper_outline schema**：在现有 sections 上增加 `required_arguments`、`required_evidence`、`tone`、`dependencies`（可选）；**由 Planner Agent 通过 prompt 升级产出**，不新增 Architect。
2. **新增 Section Memory Builder 逻辑**：在每节写前，根据 `paper_outline`、`current_section_id` 拼装 `compressed_context`（thesis_summary、current_section_spec、可选 terminology_glossary）；**不**对 draft_sections 做摘要，**不**引入 Summarizer Agent。
3. **Writer 输入调整**：Writer **继续接收完整 paper_outline**（把握整体关联），并接收 `compressed_context`、knowledge_base、user_requirements；**不再**读已写节正文 `draft_sections`。输出仍为单节正文、写入 `draft_sections[section_id]`。

### 阶段 B：一致性关口与局部修补

5. **Consistency Reviser**：新建或扩展 GlobalReviser；输入为全文摘要 + 各节正文（或仅摘要+关键句），输出为 `modification_instructions`（结构化指令列表）。
6. **Local Patcher**：根据 `modification_instructions` 对指定 section 调用 Writer（「修订模式」：输入=该节正文+指令，输出=修订后整节）或小型修补工具，更新 `draft_sections`。
7. **流程编排**：在「拼接 draft_text」之后、「GlobalReviser」之前或之后，插入 Consistency Reviser → Local Patcher 的 1–2 轮迭代；再交 GlobalReviser 做全文质量终审。

### 阶段 C：DAG 与可扩展性（可选）

8. **dependencies 驱动排序**：若 sections 含 dependencies，协调层或工作流按拓扑排序决定写作顺序；无依赖时退化为 display_number 顺序。
9. **并行写**：对无依赖关系的节可考虑并行调用 Writer（需 state 与并发安全设计），降低总时长。

---

## 七、风险与约束

- **仅靠提纲把握前文**：Writer 不读已写节正文，只读完整提纲；若某节强依赖前文某句具体表述，可能出现衔接偏差。可通过提纲中 section_goal / required_arguments 写细、或后续 Consistency Pass 做术语与重复论点修正来缓解。
- **Consistency Reviser 的指令粒度**：指令过粗则 Patcher 难执行，过细则指令本身很长；建议先做「section 级 + 简短 instruction」。
- **与 phase1 的兼容**：若当前代码仍为「单篇 Writer + 单 Reviser」，可先落地 phase1 的按节写+双 Reviser，再在本计划上叠加 Section Memory Builder 与 Consistency Pass，避免一次改动过大。

---

## 八、小结

| 维度 | 内容 |
|------|------|
| **目标** | 支持万字论文、控制 token、可编排多阶段构建；不依赖单次整篇生成 |
| **四层** | 宏观规划（Planner 产出机器可读结构树，prompt 升级）→ 中观结构（压缩上下文，以**完整提纲**替代前文正文摘要，无 Summarizer）→ 微观写作（Writer 读完整提纲 + 压缩上下文，只写当前节）→ 一致性关口（指令式修订 + 局部修补） |
| **核心机制** | DAG（依赖与排序）+ 记忆压缩（**提纲作为前文/整体替代** + compressed_context，不引入 Summarizer）+ 迭代精修（SectionReviser + Consistency Reviser + Local Patcher） |
| **与 phase1** | 在 phase1 的扁平 sections、按节写、双 Reviser 基础上，Planner prompt 扩展结构树字段、插入 Section Memory Builder（纯逻辑）、Writer 读完整 outline 但不读 draft_sections 正文、新增 Consistency Pass |
| **与 ADK/Resource** | 用 SequentialAgent / LoopAgent 编排；state 存结构树、压缩上下文、修改指令；可参考 deep-search 的 pipeline + EscalationChecker 模式 |

本文档可作为「论文编译器」升级的总体思路与实施顺序参考；具体字段名、state key 与接口可在实现时与 phase1 及现有代码对齐后微调。

---

*文档版本：v1。若与 phase1-upgrade-plan 或 about.md 有冲突，以实际实现与 about.md 为准。*
