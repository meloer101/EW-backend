# ScholarFlow — 项目架构与工程说明

本文档从工程视角描述 ScholarFlow 的整体架构、数据流、状态与扩展性，面向后续维护与迭代决策。

---

## 一、项目整体架构

### 1.1 模块划分

系统采用 **单根协调者 + 多专业子代理** 的编排模式，子代理以 **工具（AgentTool）** 形式挂载在根代理上，由根代理在对话中按阶段调用。

| 层级 | 模块 | 职责 |
|------|------|------|
| **入口层** | `my_agent/agent.py` | 导出 `root_agent`（即 scholar_flow_coordinator），供 ADK Runner / Web 调用 |
| **编排层** | 根协调者 (LlmAgent) | 需求收集、阶段切换、子代理调用顺序与次数约束；用户可见的对话与进度说明 |
| **配置层** | `config.py` | 统一 LLM 实例（LiteLlm + DeepSeek）、应用常量 |
| **能力层** | 6 个子代理 | Intake / Knowledge / Planner / Writer / Reviser / Formatter，各司其职，无互相调用 |

代码结构按「每个子代理一个目录」组织：

- 每个子代理目录含：`__init__.py`、`agent.py`（LlmAgent 定义）、`prompt.py`（instruction 文案）。
- 根目录：`agent.py`（根代理 + AgentTool 列表）、`prompt.py`（协调者 instruction）、`config.py`。

### 1.2 调用关系

- **唯一入口**：用户消息 → ADK Runner → `root_agent`（即 scholar_flow_coordinator）。
- **协调者 → 子代理**：协调者通过 **LLM 决策 + 工具调用** 调用子代理；每次调用对应一次 AgentTool 执行，子代理在 **独立子 Session** 中运行，读入父 Session 的 state 副本，结束时通过 `state_delta` 回写父 Session。
- **子代理之间**：无直接调用；数据依赖全部通过 **父 Session 的 state** 传递（协调者不修改 state，只触发子代理；子代理通过 `output_key` 写入 state，下一环节子代理从 state 读取）。

```
                    ┌─────────────────────────┐
                    │ scholar_flow_coordinator│
                    │   (LlmAgent + 6 tools)  │
                    └───────────┬─────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
  intake_agent           knowledge_agent          planner_agent
  (需求结构化)             (知识/文献整理)            (提纲生成)
        │                       │                       │
        └───────────────────────┴───────────────────────┘
                                │
                                │  state: user_requirements,
                                │         paper_outline, knowledge_base
                                ▼
  writer_agent  ──►  reviser_agent  ──►  formatter_agent
  (正文撰写)          (审稿)               (格式化与引用)
        │                  │                      │
        │ draft_text       │ review_result        │ final_paper
        └──────────────────┴──────────────────────┘
```

---

## 二、核心写作流程（用户输入 → 最终输出）

整体为 **四阶段线性 + 两处循环** 的流程，由协调者 instruction 规定，无独立工作流引擎。

1. **阶段一：需求收集（Intake）**  
   - 协调者与用户多轮对话，收集主题、学科、字数、引用格式、学术等级、写作风格等。  
   - 无子代理调用；信息停留在对话上下文中，待阶段二前可调用 intake_agent 做一次结构化（输出写入 `user_requirements`）。

2. **阶段二：论文规划**  
   - 依次调用：`intake_agent`（可选，将需求结构化）→ `knowledge_agent`（文献/理论整理，可无提纲首轮）→ `planner_agent`（生成提纲）。  
   - 设计上 Knowledge 与 Planner 可多轮交替（提纲 ↔ 知识）；当前实现由协调者按 prompt 顺序与用户确认提纲后进入阶段三。

3. **阶段三：写作与审稿**  
   - **单次撰写**：调用一次 `writer_agent`，要求其单次输出**整篇**正文，结果写入 `draft_text`。  
   - **单次审稿**：调用一次 `reviser_agent`，读 `draft_text` + `user_requirements` + `paper_outline`，输出 JSON 审稿结果写入 `review_result`。  
   - **修订循环**：若未通过（rewrite/revise），最多 3 轮：每轮仅再调用一次 `writer_agent`（部分修改或全文润色/重写，仍输出整篇）→ 再调用一次 `reviser_agent`。  
   - 通过后进入阶段四。

4. **阶段四：格式化与交付**  
   - 调用一次 `formatter_agent`，读 `draft_text` + `user_requirements` + `knowledge_base`，输出格式化全文写入 `final_paper`。  
   - 协调者被要求在其**下一条对用户的回复**中**完整粘贴** `final_paper`，保证用户看到完整正文。

关键约束（由 prompt 硬性规定）：  
- 工具参数仅允许一句短指令，禁止在参数中传长文；所有长内容依赖 state。  
- 阶段三每轮只允许一次 writer、一次 reviser，避免多次 writer 导致 `draft_text` 被片段覆盖。

---

## 三、Prompt 设计结构

### 3.1 角色划分

- **System 等价**：所有 Agent 的「身份 + 任务 + 输入输出说明」均写在 **LlmAgent 的 `instruction`** 中，由 ADK 在调用时作为系统侧指令注入；无独立的 system/user 分离文件。
- **User 等价**：每轮对话中，用户消息与协调者收到的 tool 返回内容由 ADK 组成为多轮 user/assistant 消息；子代理收到的「用户消息」为 AgentTool 构造的简短 request（如「请根据提纲与知识库撰写正文」）。
- **Tool**：子代理以 **AgentTool** 形式暴露给协调者；工具声明由 ADK 根据子代理的 `description` 与默认 schema（无自定义 input_schema 时为单参数 `request` 字符串）自动生成，协调者通过自然语言决策后调用对应工具并传入短指令。

### 3.2 State 注入方式

- 子代理 instruction 中通过 **占位符** 注入 session state：`{key}` 为必填（缺失会报错），`{key?}` 为可选（缺失时注入空或占位）。  
- 当前使用的 key：`user_requirements`、`paper_outline`、`knowledge_base`、`draft_text`、`review_result`、`final_paper`；其中 `paper_outline?`（knowledge_agent）、`review_result?`（writer_agent）、`draft_text?`（writer_agent 修订轮）为可选，以支持「首轮无提纲 / 首轮无审稿 / 修订时才有上一稿」等语义。

### 3.3 Schema 与输出格式

- **子代理**：除 Reviser 在 prompt 中约定输出 JSON（passed、overall_score、issues、action_suggestion 等）外，其余子代理输出为自由文本或自然语言描述的 JSON（如提纲、知识库、草稿、最终稿）；无 Pydantic/JSON Schema 约束，由下游 LLM 或人工解析。  
- **协调者**：无结构化输出 schema；流程与阶段完全由 instruction 中的自然语言规则描述，无独立 DSL 或规则引擎。

---

## 四、状态管理方式

### 4.1 实际形态

- **存储**：依赖 ADK 的 **Session State**（键值对、可序列化）。Runner 使用项目下的 Session 存储（如 `my_agent/.adk/session.db` 或内存），由 ADK 管理持久化与加载。  
- **结构**：**扁平 key**，无分层命名空间。主要 key：  
  - `user_requirements`（intake 输出）、  
  - `paper_outline`（planner 输出）、  
  - `knowledge_base`（knowledge 输出）、  
  - `draft_text`（writer 输出）、  
  - `review_result`（reviser 输出）、  
  - `final_paper`（formatter 输出）。  
- **更新**：子代理通过 ADK 的 `output_key` 将当次 LLM 回复**整块写入**对应 key（覆盖式），AgentTool 再将子 Session 的 `state_delta` 合并回父 Session。  
- **无**：显式 State Manager、分层 config/artifact/control、快照/回滚、dirty 标记、按 task 的写日志；PRD 中的「StatePatch + 合并 + 审计」契约未实现。

### 4.2 与 PRD 的差异

PRD 建议的 State Schema（config / knowledge / artifact / control 四层、outline.tree、sections 按节、task_status_map 等）当前未采用；实现采用「少量扁平 key + 单稿全文」的简化形态，以降低首版复杂度和与 ADK 默认行为的契合度。

### 4.3 提纲结构升级（规划中）与技术债

- **第一阶段升级计划**：提纲扁平化（Schema v2）、Writer 升级为 Section 级撰写、Reviser 拆分为 SectionReviser + GlobalReviser（双代理两阶段审稿）的完整方案见 **[docs/phase1-upgrade-plan.md](docs/phase1-upgrade-plan.md)**。包括：Schema 定义（扁平 sections + 论文级字段）、流程重构、State 形状、各代理改造详情与实施步骤。
- **主键稳定性（技术债）**：当前/短期可用编号（"1","2.1"）既作 section 身份又作展示顺序；用户插入/调序/合并会导致重排编号、主键变化，进而影响版本、审稿引用、日志。长期应拆为**稳定 id**（如 UUID）+ **display_number**（可变），仅编号随结构变。
- **status 职责**：理想做法是 planner 只产出结构设计，**status 由协调层在进入写作阶段时初始化**；v1 可为实现便利允许 planner 预填 "pending"。
- **下一架构转折点**：当前 Writer 仍**单次输出整篇**、Reviser 为单代理；第一阶段升级后将实现 **Section 级撰写（Writer 按节产出）** + **双代理审稿（SectionReviser 逐节审 + GlobalReviser 全文审）**，届时可操作 outline 与 section status 的价值才会完全发挥。

---

## 五、现有功能模块清单

| 模块 | 文件位置 | 功能摘要 |
|------|----------|----------|
| 根协调者 | `agent.py` + `prompt.py` | 四阶段编排、子代理调用约束、用户进度说明、阶段四全文交付 |
| IntakeAgent | `sub_agents/intake_agent/` | 需求澄清与结构化（目标 JSON：topic、discipline、word_count、citation_style 等） |
| KnowledgeAgent | `sub_agents/knowledge_agent/` | 按主题/提纲整理理论与文献建议；支持无提纲首轮与有提纲迭代 |
| PlannerAgent | `sub_agents/planner_agent/` | 根据需求与知识库生成论文提纲（标题树 + 字数分配） |
| WriterAgent | `sub_agents/writer_agent/` | 单次输出整篇正文；修订轮支持部分修改或全文润色/重写，仍输出整篇 |
| ReviserAgent | `sub_agents/reviser_agent/` | 六维度审稿，输出 JSON（passed、score、issues、action_suggestion） |
| FormatterAgent | `sub_agents/formatter_agent/` | 引用替换、参考文献列表、按用户要求的引用格式输出最终 Markdown |
| 配置 | `config.py` | LiteLlm 模型实例、APP_NAME；`.env` 提供 LLM_MODEL / API_KEY / BASE_URL |

未实现（PRD 标注为后续）：RAG/向量检索、完整 CitationAgent、并发调度、独立前端、规则 DSL、按节并行写作、审稿策略自动化。

---

## 六、潜在架构风险

1. **状态覆盖与单稿假设**  
   `draft_text`、`final_paper` 等均为单 key 单值；多轮 writer 若未遵守「单次全文」约束会覆盖为片段。当前通过 prompt 约束「每轮只调一次 writer、且必须输出全文」缓解，但无运行时校验或版本保留。

2. **编排逻辑完全在自然语言 Prompt 中**  
   阶段切换、循环次数、调用顺序和约束均写在协调者 instruction 中，无显式状态机或规则引擎；模型理解偏差或长上下文截断可能导致阶段错乱或多余调用，难以做单元级编排测试。

3. **长文与上下文限制**  
   整篇论文注入子代理 instruction（如 reviser 读 `draft_text`）时，可能触及模型上下文上限或 ADK/平台截断，导致审稿或格式化只看到部分内容；当前无分块或摘要策略。

4. **无统一审计与可观测性**  
   无 PRD 要求的「每次 Agent 调用的 state 快照、patch、耗时、token」日志；排查问题依赖 ADK Web 的 event 与 state 查看，无法做离线审计或成本分析。

5. **审稿结果仅为非结构化文本**  
   Reviser 的 JSON 写在自然语言回复中，未用 response schema 强约束；若格式错误或字段缺失，协调者或 writer 可能误解析，无校验层。

6. **单点模型与单点协调者**  
   所有子代理共用同一 LiteLlm 实例；协调者单点，无降级或并行编排方案。

7. **提纲 section 主键不稳定（见 4.3）**  
   若提纲采用编号作 section 唯一 id，用户改结构后重排编号会破坏版本与审稿引用；升级时需预留稳定 id + display_number 的演进路径。

---

## 七、可扩展性评估

- **新增子代理**：容易。新建目录（agent.py + prompt.py + __init__.py），在根 agent 的 tools 列表增加 `AgentTool(agent=...)`，并在协调者 prompt 中说明调用时机与约束即可；state 可新增 key 供新代理读写。  
- **新增阶段或分支**：中等。需改协调者 prompt（及可能的调用约束），无独立配置或 DSL，易产生 prompt 膨胀与不一致。  
- **结构化 State / 分层 Schema**：需重构。若引入 PRD 式 config/artifact/control 或按节 sections，需统一读写路径、迁移现有扁平 key，并决定由 ADK state 还是外部 State Manager 承载。  
- **规则驱动编排**：需引入新组件。若用 declarative 规则或 DSL 驱动「何时调用谁、依赖哪些 key」，需实现规则引擎与 state 查询层，并逐步从 prompt 中抽离分支逻辑。  
- **RAG / 检索增强**：KnowledgeAgent 内扩展。可在 knowledge_agent 内接入向量库或检索 API，输出仍写 `knowledge_base`，对上游协调者与下游 writer 透明。

---

## 八、当前系统定位：实验级

**结论**：当前实现属 **实验级（MVP / 原型）**，适合验证流程与体验，尚未达到可长期运维的工程级标准。

**理由简述**：

- **契约与状态**：PRD 中的 StatePatch、State Manager、Task Tree、Rule Engine 未落地；状态为扁平 key + 覆盖式更新，无版本、回滚与审计，不利于多人协作与问题回溯。  
- **编排**：编排完全依赖根协调者的大段自然语言 prompt，无显式状态机、规则引擎或可测试的编排单元，变更成本与回归风险较高。  
- **可观测与质量**：无标准化日志、耗时与 token 统计、审稿结果结构化校验，不利于成本控制与质量监控。  
- **鲁棒性**：长文截断、模型输出格式不稳定、单点模型与单点协调者等问题仅通过 prompt 与使用约束缓解，无架构级防护。  
- **正面基础**：模块边界清晰（每代理一目录、职责单一）、配置集中、与 ADK 集成一致，便于在现有结构上逐步引入 State Manager、规则层与审计，向工程级演进。

---

*文档版本：与当前代码状态一致；若 State 设计或编排方式发生结构性变更，建议同步更新本文档。*
