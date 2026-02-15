# ScholarFlow 第一阶段升级计划

本文档整合提纲结构升级、Section 级撰写与两阶段审稿（双 Reviser 方案）的全部讨论成果，形成**可落地的第一阶段升级计划**。

---

## 一、升级背景与目标

### 1.1 当前系统现状

- **Writer**：单次输出**整篇**论文正文（`draft_text`），审稿和修订都以全文为粒度。
- **Reviser**：一个代理，一次审整篇，输出 JSON（`review_result`）。
- **Planner**：输出树形 `outline_tree`（含 `children`），仅用于展示，不可按节操作。
- **协调层**：阶段三为「一次 Writer → 一次 Reviser → 若不通过最多 3 轮」。
- **子代理数量**：6 个（Intake / Knowledge / Planner / Writer / Reviser / Formatter）。

### 1.2 升级目标

1. **Writer 升级为 Section 级撰写**：按节逐段输出，成本更低、单节失败可定点重写。
2. **Reviser 拆分为两个独立代理**：`section_reviser`（逐节审）与 `global_reviser`（全文审），职责分离。
3. **Planner 输出扁平化**：从树形 `outline_tree` 改为**扁平 sections + 论文级字段**，支持按 section_id 索引与状态追踪。
4. **协调层流程重构**：阶段三改为「按节循环写+审 → 拼接全文 → 全文审 → 按需修订」。
5. 升级后**子代理数量**变为 7 个（Intake / Knowledge / Planner / Writer / SectionReviser / GlobalReviser / Formatter）。

---

## 二、提纲结构升级（Outline Schema v2）

### 2.1 设计原则

- **可操作**：支持按 section 索引、更新状态、单节重写，而非仅展示。
- **自包含**：outline 携带论文级元数据（字数、引用格式、学科等），Writer 主要读 outline 即可。
- **可进化**：version、预留扩展位（local_review、versions），支持比较与回滚。
- **职责清晰**：Planner 只产出结构设计；运行状态（status）由协调层初始化与管理。

### 2.2 Schema 定义

**论文级（顶层）字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `outline_version` | number | 提纲版本号，每次重跑 Planner 时自增 |
| `title` | string | 论文标题 |
| `thesis_statement` | string | 核心论点 / 研究问题 |
| `total_word_count` | number | 目标总字数 |
| `metadata` | object | 写作蓝图元数据（discipline, academic_level, citation_style, language） |

**sections：扁平、可操作**

`sections` 为对象，key = section 的 id（短期用 display_number 如 "1","2","2.1"），value 为：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 稳定主键（短期用编号，长期改 UUID） |
| `display_number` | string | 展示用编号，如 "1", "2.1"；可随结构变化 |
| `title` | string | 节标题 |
| `goal` | string | 本节写作目标/要点 |
| `word_count` | number | 本节目标字数 |
| `status` | string | 运行状态（见下文状态流转） |
| `local_review` | null / object | 本节审稿结果（由 SectionReviser 写入） |
| `versions` | [] | 预留：本节历史版本 |

### 2.3 示例 JSON

```json
{
  "outline_version": 1,
  "title": "布罗尼斯拉夫·马林诺夫斯基与现代人类学的奠基及反思",
  "thesis_statement": "本文探讨马林诺夫斯基如何通过功能主义...",
  "total_word_count": 5500,
  "metadata": {
    "discipline": "人类学",
    "academic_level": "master",
    "citation_style": "GB/T 7714",
    "language": "zh"
  },
  "sections": {
    "1": {
      "id": "1",
      "display_number": "1",
      "title": "引言",
      "goal": "研究背景、问题提出、研究意义、方法概述",
      "word_count": 500,
      "status": "pending",
      "local_review": null,
      "versions": []
    },
    "2": {
      "id": "2",
      "display_number": "2",
      "title": "文献综述",
      "goal": "相关理论回顾、已有研究、研究空白",
      "word_count": 800,
      "status": "pending",
      "local_review": null,
      "versions": []
    }
  }
}
```

### 2.4 技术债

- **主键稳定性**：短期用编号既做 id 又做排序；用户插入/调序/合并时编号会变，导致版本与审稿引用断裂。长期应拆为**稳定 id（UUID）+ display_number（可变）**。
- **status 职责**：理想由协调层在写作阶段初始化；v1 可允许 Planner 预填 "pending"。

---

## 三、整体流程（目标形态）

```
阶段一：需求收集（Intake） → 阶段二：论文规划（Planner）
    ↓
提纲确认，对 sections 按 display_number 排序
    ↓
协调层初始化：各 section.status = "pending"
    ↓
┌────────────────────────────────────────────────────────────────┐
│ 内循环：对每个 section_id（按顺序）                               │
│                                                                │
│   1. Writer(section_id) → 产出本节正文                          │
│      └─ 写入 draft_sections[section_id]                        │
│                                                                │
│   2. SectionReviser(section_id) → 本节审稿                     │
│      └─ 写入 sections[section_id].local_review                 │
│                                                                │
│   3. 若本节未通过 → 重试 Writer(section_id)（单节最多 N 轮）     │
│      若通过 → 继续下一节                                        │
└────────────────────────────────────────────────────────────────┘
    ↓
所有 section 通过 → 拼接 draft_sections → 完整 draft_text
    ↓
GlobalReviser(draft_text, user_requirements, paper_outline) → review_result
    ↓
判断 review_result：
  ├─ 通过 → Formatter → 交付
  ├─ 特定段落不通过 → 按 section_id 定点回调 Writer 重写对应段落
  │   └─ 更新 draft_sections → 重新拼接 draft_text → 再次 GlobalReviser
  └─ 全文不通过 → 全文重写（对所有 section 重调 Writer 或视情况处理）
      └─ 重新拼接 draft_text → 再次 GlobalReviser
    ↓
最终通过 → Formatter → 交付用户
```

---

## 四、各模块改造详情

### 4.1 Planner（提纲生成器）

**改造内容**：

- 输出从树形 `outline_tree`（含 `children`）改为**扁平 `sections` + 论文级字段**（与上文 Schema v2 一致）。
- 保证 `display_number` 唯一且可排序（如 "1" → "2" → "2.1" → "2.2" → "3"）。
- 新增输出字段：`outline_version`、`thesis_statement`、`total_word_count`、`metadata`。
- 各 section 含 `id`、`display_number`、`title`、`goal`、`word_count`；预留 `status`（可预填 "pending"）、`local_review`（null）、`versions`（[]）。

**对协调层的影响**：

- Planner 的输出仍写入 `paper_outline`（output_key 不变），但 schema 从树形改为扁平。
- 协调层需能按 display_number 排序得到写作顺序。

### 4.2 Writer（论文写手 → Section 级撰写）

**改造内容**：

- 从「单次输出整篇」改为「按 section_id 单节撰写」。
- **输入**：从 state 读取——
  - `paper_outline`（完整提纲，用于了解全局结构与本节规格）
  - `knowledge_base`（参考资料）
  - `user_requirements`（用户需求）
  - `current_section_id`（当前要写的节 id，协调层在调用前写入 state）
  - `draft_sections`（已完成的节的正文，用于上下文衔接）
  - `section_review`（可选，若为修订轮，读取 local_review 或 GlobalReviser 的反馈）
- **输出**：**仅本节正文**，写入 `draft_sections[section_id]`（output_key 改为写分节存储）。
- 修订轮行为：
  - **SectionReviser 未通过**：重写本节，读取 `sections[section_id].local_review` 中的反馈。
  - **GlobalReviser 指定特定段落**：根据 `review_result` 中的 section_id 信息，重写指定节。
  - **GlobalReviser 全文不通过**：重写全部节（或协调层批量重调 Writer）。

### 4.3 SectionReviser（逐节审稿 —— 新增代理）

**代理定位**：在内循环中与 Writer 配对，每写完一节就审该节。

- **输入**：从 state 读取——
  - `draft_sections[current_section_id]`（当前节正文）
  - `paper_outline`（提纲，获取该节的 goal、word_count 等规格）
  - `user_requirements`（用户需求，含学术等级、写作风格等）
  - `current_section_id`（当前审稿的节 id）
- **输出**：与现有 Reviser 类似的 JSON 格式，但范围限于**本节**：

```json
{
  "section_id": "2.1",
  "passed": true,
  "overall_score": 8,
  "dimension_scores": {
    "evidence_sufficiency": 8,
    "structure_quality": 7,
    "language_quality": 8,
    "length_adequacy": 9,
    "citation_completeness": 7,
    "originality": 8
  },
  "issues": [],
  "overall_comment": "本节论述充分，结构清晰。",
  "action_suggestion": "ok"
}
```

- 输出写入 `paper_outline.sections[section_id].local_review`。
- **判断标准**：与现有 Reviser 一致（score >= 7 且无严重问题 → passed; 5-6 → revise; < 5 → rewrite）。
- **未通过时**：协调层对该节重调 Writer（传入 local_review 作为修订参考），重审，单节最多 N 轮（建议 2-3 轮）。

### 4.4 GlobalReviser（全文审稿 —— 新增代理，替代原 Reviser）

**代理定位**：在内循环**外**接收完整草稿，做全局质量审查。

- **输入**：从 state 读取——
  - `draft_text`（完整草稿，由协调层拼接）
  - `user_requirements`（用户需求）
  - `paper_outline`（完整提纲，含 thesis_statement、metadata、各 section 规格）
- **输出**：与现有 `review_result` 完全兼容的 JSON：

```json
{
  "passed": false,
  "overall_score": 6,
  "dimension_scores": { ... },
  "issues": [
    {
      "type": "structure_problem",
      "section": "2.1",
      "description": "第 2.1 节论证与第 3 节存在重复",
      "suggestion": "合并或重新划分两节的论述范围"
    },
    {
      "type": "length_issue",
      "section": "global",
      "description": "全文总字数仅达目标的 78%",
      "suggestion": "扩充主体论述部分"
    }
  ],
  "overall_comment": "整体结构基本合理，但章节衔接和总字数仍需改善。",
  "action_suggestion": "revise"
}
```

- 输出写入 `review_result`（output_key 与现有一致）。
- **审查重点**（与 SectionReviser 的分工）：
  - **章节衔接与逻辑连贯性**：跨节过渡、前后呼应。
  - **整体结构合理性**：全文布局与提纲的对齐度。
  - **总字数达标性**：total_word_count 的满足度。
  - **全文一致性**：术语统一、论点一致、引用风格一致。
  - **原创性与深度**：全文层面的学术贡献评估。
- **未通过时的处理逻辑**（由协调层执行）：
  1. **issues 中指定了 section_id** → 按 section_id 定点回调 Writer 重写对应段落 → 更新 draft_sections → 重新拼接 draft_text → 再次 GlobalReviser。
  2. **issues 为全局性问题（section = "global" 或全文 action_suggestion = "rewrite"）** → 全文重写：对所有（或大部分）section 重调 Writer → 重新拼接 → 再次 GlobalReviser。
  3. 最多执行 N 轮（建议 3 轮）。

### 4.5 SectionReviser 与 GlobalReviser 的审查维度分工

| 审查维度 | SectionReviser | GlobalReviser |
|----------|:-:|:-:|
| 论证充分性（evidence_sufficiency） | ✅ 本节论证是否充分 | ✅ 全文论证体系是否完整 |
| 结构合理性（structure_quality） | ✅ 本节段落逻辑 | ✅ 全文章节布局与衔接 |
| 语言规范性（language_quality） | ✅ 本节语言 | ✅ 全文术语与表达一致性 |
| 篇幅适当性（length_adequacy） | ✅ 本节 vs 目标字数 | ✅ 总字数 vs total_word_count |
| 引用完整性（citation_completeness） | ✅ 本节引用 | ✅ 全文引用覆盖与一致性 |
| 原创性（originality） | ⬜ 不评估 | ✅ 全文层面的独立思考 |
| 章节衔接 | ⬜ 不评估 | ✅ 跨节过渡与逻辑连贯 |
| 论点一致性 | ⬜ 不评估 | ✅ 与 thesis_statement 对齐 |

---

## 五、State 形状

### 5.1 新增与调整的 State Key

| Key | 类型 | 说明 |
|-----|------|------|
| `paper_outline` | object | 采用 Schema v2（扁平 sections + 论文级字段）；`sections[id].local_review` 由 SectionReviser 写入 |
| `current_section_id` | string | 协调层在调用 Writer 或 SectionReviser 前写入，指明当前操作的 section |
| `draft_sections` | object | key = section_id，value = 该节正文字符串；Writer 按节写入 |
| `draft_text` | string | 完整正文；协调层在所有节通过后由 draft_sections 按顺序拼接生成 |
| `review_result` | object | GlobalReviser 的全文审稿结果（JSON），与现有结构兼容 |
| `final_paper` | string | Formatter 的最终输出（不变） |

### 5.2 Section Status 流转

```
pending ──Writer──→ written ──SectionReviser──→ section_passed
                        ↑                           │
                        └───── 未通过，重写 ──────────┘
                        
section_passed（全部节通过后） → 拼接 draft_text → GlobalReviser
                                                      │
                              ┌── 通过 ──→ Formatter ──→ 交付
                              │
                              └── 未通过 ──→ 定点重写或全文重写
                                              → 对应 section 回到 written
                                              → 重新拼接 → 再次 GlobalReviser
```

具体 status 值：

| 状态值 | 含义 |
|--------|------|
| `pending` | 未开始写作 |
| `writing` | 正在撰写（可选） |
| `written` | 本节已产出，待 SectionReviser 审稿 |
| `section_passed` | 本节通过 SectionReviser 审稿 |
| `revising` | GlobalReviser 要求修订，正在重写（可选） |

---

## 六、协调层（根 Agent）阶段三重构

### 6.1 新阶段三步骤

1. **初始化**：从 `paper_outline.sections` 按 `display_number` 排序得到写作顺序列表；将各 section.status 设为 "pending"；初始化 `draft_sections = {}`。

2. **内循环——按节写作与审稿**：  
   对每个 section_id（按顺序）：  
   a. 将 `current_section_id` 写入 state。  
   b. 调用 `writer_agent`（短指令：「请撰写当前指定节」）→ Writer 从 state 读 outline/知识库/已写内容，输出本节正文，写入 `draft_sections[section_id]`。  
   c. 调用 `section_reviser`（短指令：「请对当前节进行审稿」）→ 读本节正文与节规格，输出审稿结果，写入 `sections[section_id].local_review`。  
   d. 若 local_review.passed = false 且 action_suggestion = "revise" 或 "rewrite"：重试 b→c（单节最多 2-3 轮）。  
   e. 若通过，继续下一节。

3. **拼接全文**：按 display_number 顺序将 `draft_sections` 拼接为 `draft_text`。

4. **全文审稿**：  
   调用 `global_reviser`（短指令：「请对完整草稿进行全文审稿」）→ 读 `draft_text` + `user_requirements` + `paper_outline`，输出写入 `review_result`。

5. **全文审稿结果处理**：  
   - **通过**（`review_result.passed = true`）→ 进入阶段四（Formatter）。  
   - **特定段落不通过**（issues 中有具体 section_id）→ 对这些 section 重调 Writer（将 review_result 中该节的 issue 作为修订依据）→ 更新 draft_sections → 重新拼接 draft_text → 回到步骤 4。  
   - **全文不通过**（action_suggestion = "rewrite" 或整体性问题）→ 全文重写：对所有 section 重调 Writer → 重新拼接 → 回到步骤 4。  
   - 最多重复 3 轮。

6. **阶段四**：调用 `formatter_agent`(draft_text) → `final_paper` → 展示给用户。

### 6.2 子代理工具列表变更

原 6 个子代理 → 升级为 7 个：

```python
tools=[
    AgentTool(agent=intake_agent),
    AgentTool(agent=planner_agent),
    AgentTool(agent=knowledge_agent),
    AgentTool(agent=writer_agent),
    AgentTool(agent=section_reviser),    # 新增
    AgentTool(agent=global_reviser),     # 新增（替代原 reviser_agent）
    AgentTool(agent=formatter_agent),
]
```

原 `reviser_agent` 删除，由 `section_reviser` + `global_reviser` 替代。

---

## 七、实施步骤

| 序号 | 模块 | 具体工作 |
|:----:|------|----------|
| 1 | **Planner** | 修改 prompt，输出改为 Schema v2（扁平 sections + 论文级字段）；保证 display_number 可排序 |
| 2 | **Writer** | 改为 Section 级撰写模式；接受 current_section_id，读 draft_sections 获取前文上下文；输出仅本节正文；output_key 改为写入 draft_sections |
| 3 | **SectionReviser** | 新建 `sub_agents/section_reviser/` 目录（prompt.py + agent.py + \_\_init\_\_.py）；逐节审稿，输出节级 JSON，写入 sections[id].local_review |
| 4 | **GlobalReviser** | 新建 `sub_agents/global_reviser/` 目录；全文审稿，输出与现有 review_result 兼容的 JSON；issues 中包含 section_id 以支持定点修订 |
| 5 | **协调层** | 阶段三 prompt 重写：按节循环（Writer → SectionReviser）→ 拼接 → GlobalReviser → 定点/全文修订逻辑；工具列表更新为 7 个代理 |
| 6 | **State** | 约定 draft_sections、current_section_id 的读写逻辑；确认 ADK output_key 与 state_delta 的写回方式（draft_sections 可能需要 callback 或自定义 output 逻辑） |
| 7 | **清理** | 删除原 `reviser_agent/` 目录；更新 about.md 与相关文档 |
| 8 | **联调测试** | 单节写+审、全文审、定点修订、全文重写、Formatter 联调 |

---

## 八、扩展预留：用户指定写作层级

后续如需支持「用户指定写作/展示层级」（按章、按节、按段）：

- **Planner**：section 增加 `level`（1=章、2=节、3=段）或 `parent_id`；约定 display_number 的层级规则。
- **协调层**：根据用户选择过滤出「当前可写单元」列表（如只取某 level 的 section），再按顺序执行循环。
- **Writer / SectionReviser**：接口不变（仍以 section_id 为粒度），只是 section 的划分由层级定义决定。

当前方案（以 outline 的每个 section 为最小写作单元）可直接作为「按节」的默认行为，无需改接口即可落地。

---

## 九、关键设计决策一览

| 项 | 决策 | 理由 |
|----|------|------|
| Reviser 拆分 | 拆为 SectionReviser + GlobalReviser 两个独立代理 | 职责分离：逐节审查 vs 全文审查；独立 prompt 与 output_key，各自优化 |
| Writer 粒度 | 按 section_id 单节输出 | 成本控制、单节失败定点重写、与 SectionReviser 配对形成内循环 |
| 全文审不通过 | 区分「定点修订」与「全文重写」 | GlobalReviser 的 issues 含 section_id → 只改问题节；全局性问题 → 全文重写 |
| Section 主键 | 短期用编号；长期改 UUID + display_number | 技术债标注，便于演进 |
| Status 初始化 | 协调层在进入写作阶段时初始化 | Planner 纯设计、协调层管状态，职责分离 |
| Outline 结构 | 扁平 sections + 论文级字段 | 可按 section 操作、可排序、可独立更新状态 |

---

*文档版本：v1。本文档作为第一阶段升级的统一参考；实施过程中若有调整，请同步更新本文档与 about.md。*
