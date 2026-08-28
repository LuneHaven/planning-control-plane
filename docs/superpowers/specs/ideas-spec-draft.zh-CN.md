# PCP Spec 补章草案 — IDEA 子系统（想法层）

| 项 | 值 |
| --- | --- |
| 状态 | **草案（Draft，待评审）**——尚未合并主 spec；阶段 1–3 已按本草案实现（计划与执行记录见 docs/superpowers/plans/），仅 §62.3 的 `pcp close` 集成仍候 PLAN 世界 V0.2 |
| 编号 | 章节暂用 §50–§62，需求 ID 暂用 `IDEA-D*`；合并主 spec 时统一重排（当前主 spec 已引用至 §43） |
| 语言 | 草案以中文撰写，标识符/枚举/规则名保持英文原值；合并时的语言对齐待定 |
| 依赖 | 对齐主 spec：§8（节点 schema）、§9/§10（受控枚举）、§12（stores, never judges）、§14（继承方向）、§16（校验协议）、§17（引用校验）、§20/§21（capsule）、§24（进度计数）、§37（数据为源，HTML 为投影） |
| 关联 V0.2 候选 | `pcp close` 集成、`CANCELLED` 终态（PLAN 世界，独立立项，见 §56.3）；`pcp graduate` 已于阶段 3 落地（R4，见附录 D.7） |
| 修订 | R1：依据对现有实现（V0.1.2）的逐条核对结果修订，新增 `IDEA-D58`–`IDEA-D64`，改动清单与代码依据见附录 D。R2：三条 P3 措辞修正（规则边界互斥 / 前缀豁免 / 门禁判据），见附录 D.5。R3：阶段 2 实施发现的三条落地约束 + D.4 的 CI 触发条件标记，见附录 D.6。R4：阶段 3（`pcp graduate`）的实施契约，见附录 D.7。需求 ID 按新增顺序编号，与章节顺序无关，合并主 spec 时统一重排 |

---

## §50 总则

### 50.1 目的

PCP 现有节点体系是**决策后控制系统**：类型是准入后的角色，状态是准入后的进度，scope
护栏是准入时的范围承诺；准入判断本身发生在系统之外。本补章在节点体系之外建立一个
**想法层（IDEA 子系统）**，承载"承诺之前的思考"，补齐规划漏斗的入口：

```
捕获（无门槛）→ 存续（落盘不丢）→ 分诊（按时刻过目）→ 毕业判定（进或不进 PLAN 世界）
```

**IDEA-D1** 想法层管理的是未承诺的思考，不是任务、不是知识库、不是第二张规划图。
**IDEA-D2** 一个想法进入规划图的唯一途径是毕业（§55）；毕业之外的任何机制不得
使想法影响节点、capsule、进度计数或焦点。

### 50.2 双世界单桥定位

**IDEA-D3** 体系为双世界、单桥结构：

- **IDEA 世界**（承诺之前）：捕获、论据积累、分诊、毕业判定；
- **PLAN 世界**（承诺之后）：即现有节点体系，语义零改动；
- **毕业桥**是唯一的跨世界动作，且只由想法侧发起（`outcome` 边，§54.1）。

```
【IDEA 世界 · 承诺之前】                【PLAN 世界 · 承诺之后 = 现有节点体系】

捕获(OPEN) → 论据积累(§52) → 分诊(§57) → 毕业桥 ──outcome──► 节点(试点/立项)
   ▲                                                            │
   └────────── 新想法 ◄──relates_to(诞生上下文)── 落地/收尾/受阻节点 ┘
```

关联是**语义闭环、表示开环**（§56.1）：迭代闭环在查询与分诊时刻闭合，数据结构上
节点永不反向引用想法。

### 50.3 哲学对齐

**IDEA-D4** 想法层沿用两条既有哲学：

1. **stores, never judges**（对齐 §12）：系统存储、继承、展示想法与论据，对"论证
   是否充分"的最高干预是**展示**——R1 后连 WARNING 也不产生（§52.4），永不裁决，
   永不阻断。
2. **链接而不拥有**（对齐 authority boundary）：论据 `ref` 只链仓库内路径；仓库
   之外的对标对象（竞品、成熟产品）用 `note` 描述，不链接、不复制、不判定其内容。

### 50.4 非目标（硬边界）

**IDEA-D5** 明确不做，且实现与后续版本均不得引入：

- 标签体系、想法间互链（含 `builds_on`/`supersedes` 类的 idea→idea 边）；
- 想法全文检索、分页、语义搜索、自动摘要、自动聚类；
- 把 `IDEA` 加入 `NodeType`；
- capsule 任何模式携带想法内容（compact 与 full 均不得）；
- 想法成为 `current_focus`；
- 基于时间的想法规则（如"OPEN 超过 N 天告警"）；
- 想法的评论、协作、多人指派。

本条只约束想法层。README 路线图中的 V0.2 候选（如"搜索 / 过滤"）针对节点侧，
不受本条约束。

---

## §51 Idea 实体与存储

### 51.1 存储布局

**IDEA-D6** 想法存放于 `.planning/ideas/`，一文件一想法，文件名 `<id>.yaml`。

**IDEA-D7** `ideas/` 目录可选：缺失时 loader 静默跳过，不产生任何 issue；既有
无想法项目的命令与构建输出按不变量 §59.4 的分阶段口径保持不变（阶段 1 字节级，
阶段 2 结构与可见内容级）。

**IDEA-D8** 不提供内联清单（不做 `ideas.yaml`，明确不对称于 `roadmap.yaml`）：
想法高频诞生，单文件使 git 合并冲突保持线性。

**IDEA-D9** `ideas/` 属规划数据源，随仓库提交（对齐 §37：dist 是可丢弃投影，
ideas 与 nodes 一样是源）。`pcp init` 阶段 1 不创建该目录（首个想法到达时自建）。

### 51.2 字段表

**IDEA-D10** Idea 实体字段（枚举字段存原始字符串，由 validator 做成员校验——
对齐 §8 Node 的既有设计）：

| 字段 | 类型 | 默认 | 语义 |
| --- | --- | --- | --- |
| `id` | str，必填 | — | 想法 id，字符集沿用 `NODE_ID_RE`（`^[A-Za-z0-9][A-Za-z0-9._-]*$`）；建议 `IDEA-` 前缀（约定，不校验） |
| `title` | str，必填 | — | 一行标题；缺失时 ERROR 并回退为 id（镜像 `missing-title`） |
| `detail` | str | `""` | 想法原文，自由文本，捕获时不要求结构 |
| `status` | str | `OPEN` | 生命周期状态，枚举见 §53.1 |
| `relates_to` | list[str] | `[]` | 诞生上下文：节点 id 列表（§54.1） |
| `benchmark_sources` | list[entry] | `[]` | 对标论据（§52.1） |
| `methodology_sources` | list[entry] | `[]` | 方法论论据（§52.1） |
| `outcome` | null \| {node, note} | `null` | 毕业去向（§55.2） |
| `created` | str | `""` | 自由字符串，不校验格式（与节点 `last_updated` 一致）；建议 ISO 8601（`YYYY-MM-DD`） |
| `last_updated` | str | `""` | 同上；同时是列表排序键，空值与非 ISO 值的排序行为由 IDEA-D61 裁定 |

论据条目结构（两个论据槽通用）：

```
entry ::= { ref?: <仓库相对路径>, note?: <自由文本> }   # ref 与 note 至少一项非空
```

**IDEA-D11** 出现在源 YAML 但不在上表中的键，收集进 `unknown_fields`，由
validator 报 `idea-unknown-field` WARNING——镜像节点的未知字段协议，但**不复用**
节点侧的 `unknown-field` 规则名：`ValidationIssue` 只有一列 id，`pcp validate` 把
节点与想法的 issue 混排，而 IDEA-D15 又允许想法 id 与节点 id 撞号；同名规则会使
输出无法分辨该条问题属于哪一层（另见 IDEA-D64 的 message 前缀约定）。

**IDEA-D12** Idea 无三轨、无 objective/scope、无决策分类、无 next_action：
想法不承载任何规划语义，需要这些语义的时机就是毕业的时机。

### 51.3 加载惯例（逐条镜像节点 loader）

**IDEA-D13** 加载行为镜像 `nodes/` 的既有惯例：

| 节点侧先例 | 想法侧对应 |
| --- | --- |
| 仅读取 `nodes/` 顶层 `*.yaml` | 仅读取 `ideas/` 顶层 `*.yaml` |
| 嵌套/错误后缀 → `ignored-node-file` WARNING | `ignored-idea-file` WARNING |
| 按文件名排序加载（确定性） | 同 |
| 非 mapping / 缺 id → `invalid-node` ERROR，丢弃该条 | `invalid-idea` ERROR，丢弃 |
| id 字符集 → `invalid-node-id` ERROR | `invalid-idea-id` ERROR |
| 重复 id → `duplicate-node-id` ERROR，保留首个 | `duplicate-idea-id` ERROR，保留首个 |
| 列表字段非 list / 条目非非空串 → `invalid-field` ERROR | `invalid-idea-field` ERROR |
| YAML 重复键 → 拒绝加载（LoadError） | 复用 `_UniqueKeyLoader` 检测，但**不抛 LoadError**：报 `invalid-idea-file` ERROR 并跳过该文件（IDEA-D58） |
| 记录 `source_file`（仓库相对路径） | 同 |

### 51.3.1 失败域隔离（与节点侧唯一的刻意差异）

**IDEA-D58** 单个想法文件的读取失败**永不阻断项目加载**：YAML 语法错误、重复键、
文件不可读，一律降级为 `invalid-idea-file` **ERROR** issue（消息携带仓库相对路径），
跳过该文件，继续加载其余想法与全部节点。`invalid-idea-file` 只覆盖"文件无法被
解析为 YAML"的失败；**解析成功但顶层不是 mapping 的文件走 `invalid-idea`**（镜像
节点先例：合法 YAML 非 mapping → `invalid-node`），两条规则的触发条件互斥。

理由：节点侧抛 `LoadError` 是合理的——节点是已承诺数据，读不出来就没有计划可谈。
但想法是零门槛捕获的未承诺数据，若沿用 `LoadError`，一个手写想法文件的缩进错误
会让 `pcp status` / `pcp context` / `pcp build` 全部退出 2，即**未承诺的思考有权
瘫痪计划本体**，与 IDEA-D2、IDEA-D27 的隔离承诺直接矛盾。隔离必须同时成立于语义
层与失败域（不变量 §59.6）。

`project.yaml`、`roadmap.yaml`、`nodes/` 的既有 `LoadError` 行为不变。

### 51.4 命名空间

**IDEA-D14** 想法 id 与节点 id 共用字符集规则但**独立命名空间**：跨世界引用是
带类型的（`relates_to`/`outcome.node` 只指向节点 id），校验按目标类型分别进行。

**IDEA-D15** 想法 id 与既有节点 id 相同时报 `idea-id-collides-with-node`
WARNING（混淆风险提示，不 ERROR——两个命名空间语义上不冲突）。

---

## §52 论据模型

### 52.1 两个论据槽

**IDEA-D16** 想法携带两类先验论据，分工为**现象层 / 原理层**：

| 槽 | 存什么 | 回答什么 |
| --- | --- | --- |
| `benchmark_sources` | 现象证据：成熟产品实证做了什么、怎么做的 | "是什么" |
| `methodology_sources` | 原理证据：从产品体系解耦出的方法原理，可跨域抽象、与具体产品解耦 | "为什么成立" |

对标与方法论是**流水线关系**而非并列关系：一次产品对标同时产出现象记录（进
benchmark）与解耦出的原理（进 methodology）。

### 52.2 条目结构与外部世界

**IDEA-D17** 每条论据 = `ref`（可选，仓库相对路径）+ `note`（可选，自由文本），
至少一项非空，否则 `invalid-idea-source` ERROR。

**IDEA-D18** `note` 是外部世界的唯一入口：对标对象（竞品、成熟产品）天然在仓库
之外，PCP 描述之、不链接之——这是 authority 哲学在论据上的复刻。`ref` 不得是
绝对路径或逃逸仓库（§52.3）。

### 52.3 ref 校验

**IDEA-D19** `ref` 的校验严重度镜像 evidence 类引用（§17 先例）：

- 逃逸仓库 / 绝对路径 → `idea-source-escapes-repo` **ERROR**；
- 指向的文件缺失 → `idea-source-missing` **WARNING**（论据允许引用尚待补全的笔记）。

**IDEA-D20** 想法论据不参与 authority roots 分类（想法不构成 canonical 语境）。

### 52.4 蓝海与后验补位

**IDEA-D21** 论据槽全空是**合法状态**（捕获零门槛）。先验真空（蓝海：现有垂域
无成熟对标）时，正确的论证方式是后验补位：**试点即论据**——以假设形态早毕业为
INVESTIGATION 节点（§55.1），用受控的小范围落地生产证据。

**IDEA-D22** 论据是否充分**不进入校验**：论据槽全空不产生任何 issue，只在
`pcp ideas` 与 ideas 页以论据存在性标记（对标 / 方法论 各一个有无点标）呈现。

理由有二，指向同一裁定：其一，按 IDEA-D21 论据全空是合法状态且是捕获常态，逐条
WARNING 会让每个新捕获的想法立刻在 `pcp validate` 与 `pcp build` 输出里各占一行
（`pcp build` 逐条打印 WARNING），与"捕获零门槛"直接冲突；其二，该信息已由
IDEA-D51 的存在性标记表达，重复。判断类信息留在展示层，符合 §12。

（原 `open-idea-without-justification` 规则据此从 §58.1 规则表删除。）

### 52.5 论证指引（informative，不入 schema）

以下创新方法论作为论证叙事写入 `note` 自由文本，不结构化、不校验、不分组：

- **对标重组**：对标 1–n 个成熟产品，取长补短，重组化创新（benchmark 多条 +
  methodology 一条：重组原理）；
- **对标深耕**：深耕特定产品特性，差异化创新（benchmark 一条深耕对象 +
  methodology 一条差异化原理）；
- **蓝海泛化**：跨领域理论方法抽象、泛化（methodology 的 ref 指向跨域理论文档，
  note 说明泛化路径）；
- **蓝海摸索**：自行摸索，以试点产生后验论据（§52.4）。

理由：三种创新模式互有重叠且属于判断；按 §12，判断不结构化。试点产出的经验
后续可反哺为本项目自己的 methodology 论据——论据槽随迭代积累为方法论资产。

---

## §53 生命周期

### 53.1 IdeaStatus

**IDEA-D23** 受控枚举，四个值：

```
OPEN      已捕获，未分诊（默认）
PARKED    明确搁置（分诊后决定"现在不做"，revisit 线索写在 detail）
PROMOTED  已毕业（outcome 必填，见 §55.5）
DISCARDED 已否决（一句话理由写在 detail，文件保留）
```

否决理由**只写 `detail`**，不得借用 `outcome.note`：`outcome` 的 `node` 字段必填
（IDEA-D32），且非 PROMOTED 状态填 outcome 会触发 `outcome-without-promotion`
（IDEA-D38）——借用该字段必然同时产生一条 ERROR 与一条 WARNING。`outcome` 是毕业
桥专用字段。

### 53.2 迁移规则

**IDEA-D24** 状态是数据、文件即源：迁移由手工编辑 YAML 完成，不设迁移校验、
不设时间规则。规范动作如下：

| 迁移 | 合法性 | 规范动作 |
| --- | --- | --- |
| OPEN → PARKED / DISCARDED / PROMOTED | ✓ | 分诊结论落盘 |
| PARKED → OPEN | ✓ | 恢复（revisit 条件满足） |
| DISCARDED → OPEN | ✓ | 复活（新证据出现）；追溯由 git 历史承载 |
| **PROMOTED → 任意** | **规范禁止** | **毕业后迭代不得通过改回 OPEN 实现**；必须新建想法文件并经节点枢纽建立谱系（§54.2）——改回会抹掉"v1 确实毕业并落地过"的历史事实 |

**IDEA-D25** 枚举成员校验：`invalid-idea-status` ERROR（无效值原样保留，一次
校验报告全部问题——对齐 §10 的 loader 哲学）。

### 53.3 与决策四分类的镜像（informative）

心智模型刻意镜像节点侧：`OPEN ↔ open_decisions`、`PARKED ↔ deferred_decisions`、
`PROMOTED ↔ frozen_decisions`（进入计划本体）。但两个枚举永不互通、互不可赋值。

---

## §54 关联模型

### 54.1 两条类型化边，均在想法侧

**IDEA-D26** 想法与节点的全部结构性关联由且仅由两条边承载：

| 边 | 方向 | 语义 | 基数 |
| --- | --- | --- | --- |
| `relates_to` | 想法 → 节点 | 诞生上下文 / 反向半环（落地反馈产生的新想法挂在此边） | 0..n |
| `outcome.node` | 想法 → 节点 | 毕业去向 / 前向半环 | 0..1 |

**IDEA-D27** 节点侧零字段、零改动：不存在节点→想法的边。这是"读计划不牵扯"
的结构保证，不是纪律约定。

### 54.2 枢纽规则

**IDEA-D28** 想法谱系**永不想法互链**，一律经由节点中转：

```
IDEA-0007 ──outcome──► P-试点节点 ◄──relates_to── IDEA-0021（毕业后迭代）
```

谱系 `IDEA-0007 → P-试点 → IDEA-0021 → 新节点` 由查询重建（"outcome 指向 N 的
想法" ∪ "relates_to 含 N 的想法"），节点是谱系的枢纽。

**IDEA-D29** 毕业前的想法分叉（无节点可挂）不建立结构谱系：新想法是独立文件，
自由文本提及母想法即可。值得结构化的谱系都发生在 PLAN 世界有枢纽之后。

### 54.3 关联查询语义

**IDEA-D30** 默认方向（**向上，祖先**，服务分诊时刻 A）：`pcp ideas --for NODE`
的命中集合 = `relates_to` 含 NODE **或 NODE 的任一祖先**的想法。祖先命中复用 §14
的继承直觉：挂在 P2 上的想法对 P2-A4 的讨论有潜在相关性。查询时按命中来源标注
（自身 / [祖先 id]），镜像 capsule 继承分组的呈现方式。

**IDEA-D60** 子树方向（**向下，后代**，服务分诊时刻 B）：
`pcp ideas --for NODE --subtree` 的命中集合 = `relates_to` 含 NODE **或 NODE 的
任一后代**的想法，同样按命中来源标注（自身 / [后代 id]）。

两个方向都必须提供：时刻 A 是"讨论某节点前，看挂在它与它上游的想法"，时刻 B 是
"收尾某节点前，看挂在它整棵子树上的想法"（§57.3）。祖先方向查不到挂在子节点上的
想法，只有默认方向时时刻 B 没有可执行的命令。

实现约束：两个方向分别复用 `PlanningGraph.ancestors()` 与 `subtree_ids()`。二者
均已对 parent 环做保护，而 parent 环只报 ERROR、不阻断加载，自行遍历 `parent` 链
会死循环（见 §62.2）。

### 54.4 无环性（informative）

想法→节点边存在、节点→想法边不存在，两个世界构成二部图，结构上不可能成环；
validator 的环检测（dependency-cycle / parent-cycle）不受任何影响。迭代只发生
在时间维度上——这正是想要的。

---

## §55 毕业桥

### 55.1 毕业形态

**IDEA-D31** 毕业目标节点的类型自然表达毕业形态（系统不限制目标类型，以下为
规范指引）：

| 形态 | outcome 目标类型 | 语义 |
| --- | --- | --- |
| 早毕业 | `DISCUSSION` / `INVESTIGATION` | 结构化论证在 PLAN 世界进行（scope 护栏、决策分类、来源链接远强于想法侧任何字段） |
| 蓝海毕业 | `INVESTIGATION` | 假设验证；试点节点 scope 刻意收窄（如 14 域中的 1 域），试点是论证手段而非交付目标 |
| 晚毕业 | `STRATEGY` / `IMPLEMENTATION` | 论据已足、目标路径已明，直接立项 |

**方向性指引**：鼓励早毕业——若发现自己在想法里想写 objective/scope，正确动作
不是给 Idea 加字段，而是早毕业。

### 55.2 outcome 语义与基数

**IDEA-D32** `outcome ::= { node: <节点 id, 必填>, note: <自由文本, 可选> }`。
`node` 引用决策 id 时不做裸引用（决策 id 仅节点内唯一，对齐既有 duplicate-decision-id
规则的 per-node 语义），用节点 id + note 说明。

**IDEA-D33** 基数：1 想法 → 1 个 outcome 目标节点（扇出由该节点自己的子树完成）；
N 想法 → 同一目标节点合法（合流）；outcome 目标不做唯一性约束。

### 55.3 论据转录

**IDEA-D34** 毕业时把想法论据索引中带 `ref` 的条目转录为目标节点的
`evidence_sources`（机械动作；阶段 1–2 手工完成，阶段 3 起由 `pcp graduate`
自动执行；见 §62.3 与附录 D.7）。转录是内容复制，不是结构链接——节点侧依旧零字段。

### 55.4 原子性与失败模式

**IDEA-D35** 毕业是两文件手工编辑（新建节点文件 + 编辑想法文件），无事务。
失败模式单向可控：

- 节点已建、想法仍 OPEN：无害不可见（等价于"忘了登记出处"）；
- 想法 PROMOTED、节点不存在：`missing-outcome-target` ERROR，可检出。

与今日 `pcp focus` 的手工编辑同级，可接受；未来 `pcp graduate` 原子化。

### 55.5 毕业相关规则

**IDEA-D36** `status == PROMOTED` 但 `outcome` 为空或缺 `node` →
`promoted-without-outcome` **ERROR**（镜像 done-with-blocking-decision 的组合
一致性先例）。

**IDEA-D37** `outcome.node` 指向未知节点 → `missing-outcome-target` **ERROR**。
目标节点被 supersedes 取代但仍存在 → 合法（历史上下文允许）；被删除 → 本规则
ERROR（镜像 C1 裁定）。

**IDEA-D38** `outcome` 已填但 `status != PROMOTED` → `outcome-without-promotion`
**WARNING**（毕业准备的过渡态合法：节点已建、状态待翻转）。

**IDEA-D39** `relates_to` 目标不存在 → `missing-idea-relates-target` **ERROR**
（镜像 missing-related-target）。该规则对终态想法同样生效（对齐"DONE 节点仍校验
边"的既有行为）。

---

## §56 迭代闭环

### 56.1 语义闭环，表示开环

**IDEA-D40** IDEA 与 PLAN 在实践中互相迭代（落地产生新思考），但闭环只在语义与
查询层闭合：前向半环 = `outcome`，反向半环 = `relates_to`（诞生上下文），两条边
都挂在想法侧，节点始终是被动的查询对象。带想法开决策讨论 = 粘贴 capsule（永不含
想法）+ 显式执行 `pcp ideas --for NODE`——两次命令 = 两次有意的上下文注入。

### 56.2 三种落地结局 → 机制映射

**IDEA-D41**（informative，机制映射）以"N 个产品领域、1 域试点"为例：

| 结局 | 既有机制 | 判定 |
| --- | --- | --- |
| 1. 确认：体验良好 → 拓展样本 或 想法迭代 | scope 收窄的试点节点 DONE → 拓展兄弟节点（区分试点与推广的只是 scope 宽窄）；或新想法文件经节点枢纽（§54.2） | 原生支持。既有示例即此模式：demo 项目 FD-101"推广按领域逐个进行" + `P2-A4 就绪度预检` |
| 2. 修正：方法或路径不合理 → 重回分析 | 试点节点 BLOCKED + blocking_decisions 记录缺陷 → 新想法（relates_to 挂该节点）→ 再论证再毕业；新路径节点 `supersedes` 旧路径节点（既有边） | 原生支持；受阻节点的重新讨论属于分诊时刻 A（§57.2） |
| 3. 否定：需求偏移 / 风险＞效益 → 终止 | 见 §56.3 | **缺口** |

### 56.3 与 PLAN 世界缺口的交互

**IDEA-D42** 结局三（终止）在现有 11 个节点状态中无诚实归宿：`DEFERRED` 是推迟
不是否决。短期 workaround：`DEFERRED` + 一个 `CLOSURE` 子节点存档终止理由（前提
失效 / 需求偏移 / 风险效益比逆转）。

**IDEA-D43** 根治方案（`CANCELLED` 终态 / `pcp close` 终止工作流）是 PLAN 世界
自身的 V0.2 候选项，**独立于本补章的实施范围**，不得并入想法层交付。交互规则：
**终止同样触发分诊时刻 B**（§57.3）——终止后这个域怎么办，往往正是新想法的来源。

---

## §57 分诊时刻

### 57.1 捕获常开

**IDEA-D44** 捕获无时刻限制：任何会话、任何节点推进阶段产生想法，随手建文件、
`status: OPEN`，等待分诊。落地过程中（IMPLEMENTING 中途）产生的想法同样如此，
不需要独立的分诊触发器。

### 57.2 时刻 A：决策讨论

**IDEA-D45** 进入一次明确的决策讨论（含受阻节点 BLOCKED 后的重新讨论）前，
执行 `pcp ideas --for NODE`，让相关想法浮出——补论据、搁置、否决，或就地吸收进
本次讨论的决策。查询语义见 §54.3。

**IDEA-D62** 分诊查询（`--for`，两个方向同）的默认状态过滤为 **OPEN + PARKED**，
分组展示、PARKED 组在 OPEN 组之后，`--status` 可显式覆盖；PROMOTED 与 DISCARDED
默认不出现。PARKED 必须进入分诊视野：它的 revisit 线索写在 `detail` 里，若两个
制度时刻都只捞 OPEN，PARKED 将再无被读到的时机，"搁置"事实上等于"删除"，与 D1
裁定（不设时限规则，靠制度时刻兜底）矛盾。

### 57.3 时刻 B：计划收尾 / 终止

**IDEA-D46** 节点收尾（DONE）或终止（§56.3）时，对收尾节点执行
`pcp ideas --for NODE --subtree`（IDEA-D60），子树相关的 OPEN 与 PARKED 想法强制
过目：拓展、迭代、搁置或否决。阶段 1–2 该时刻为手工纪律；`pcp close` 集成后成为
制度化的收尾步骤（§62.3）。

---

## §58 校验规则

### 58.1 规则总表

**IDEA-D47** 想法层规则全集（复用 `ValidationIssue`，`node_id` 字段携带想法 id；
文件级规则拿不到 id，`node_id` 为 `None`、消息携带仓库相对路径。排序沿用既有
key：severity → id → rule → message）：

| 规则名 | 层 | 严重度 | 触发 | 镜像先例 |
| --- | --- | --- | --- | --- |
| `invalid-idea-file` | loader | ERROR | 文件无法解析为 YAML：语法错误 / 重复键 / 不可读 → 跳过该文件（IDEA-D58） | （新增；节点侧对应 LoadError，想法侧刻意降级） |
| `invalid-idea` | loader | ERROR | 解析成功但顶层非 mapping / 缺非空 id | invalid-node |
| `missing-idea-title` | loader | ERROR | 缺非空 title（回退 id） | missing-title |
| `invalid-idea-field` | loader | ERROR | relates_to 等列表字段结构错误 | invalid-field |
| `invalid-idea-source` | loader | ERROR | 论据条目非 mapping / ref 与 note 均空 | invalid-decision |
| `invalid-idea-outcome` | loader | ERROR | outcome 非 mapping / 缺非空 node | invalid-decision |
| `invalid-idea-id` | loader | ERROR | id 不符 `NODE_ID_RE` | invalid-node-id |
| `duplicate-idea-id` | loader | ERROR | 重复 id（保留首个） | duplicate-node-id |
| `ignored-idea-file` | loader | WARNING | ideas/ 嵌套或错误后缀的 YAML 未被加载 | ignored-node-file |
| `invalid-idea-status` | validator | ERROR | status 不在 IdeaStatus | invalid-status |
| `missing-idea-relates-target` | validator | ERROR | relates_to 指向未知节点 | missing-related-target |
| `promoted-without-outcome` | validator | ERROR | PROMOTED 无 outcome.node | done-with-blocking-decision |
| `missing-outcome-target` | validator | ERROR | outcome.node 指向未知节点 | missing-*-target |
| `outcome-without-promotion` | validator | WARNING | outcome 已填但 status ≠ PROMOTED | blocked-without-blocker（软一致性先例） |
| `idea-source-escapes-repo` | validator | ERROR | ref 绝对路径 / 逃逸仓库 | reference-escapes-repo |
| `idea-source-missing` | validator | WARNING | ref 指向的文件缺失 | evidence-source-missing |
| `idea-id-collides-with-node` | validator | WARNING | 想法 id 与节点 id 相同 | （新增，混淆风险提示） |
| `idea-unknown-field` | validator | WARNING | 想法文件的未知字段 | unknown-field（**不复用规则名**，见 IDEA-D11） |

**IDEA-D64** 想法层每条 issue 的 message 必须以 `idea '<id>': ` 开头；文件级规则
（`invalid-idea-file` / `ignored-idea-file`）无 id 可用，以 `idea '<仓库相对路径>': `
开头。`ValidationIssue` 只有一列 id，`pcp validate` 又把节点与想法的 issue 按同一 key
混排；撞号时（IDEA-D15）无从分辨层次，而规则名的 `idea-` 前缀只覆盖部分规则
（`promoted-without-outcome`、`missing-outcome-target` 等沿用节点侧命名），不足以
承担这个职责。

### 58.2 独立性与向后兼容

**IDEA-D48** 想法规则是独立规则组：只约束想法，**从不反向约束节点**；节点规则
不感知想法。无 `ideas/` 目录的项目，`pcp validate` 输出与引入想法层之前逐字节
相同。

### 58.3 想法层 ERROR 的后果边界

**IDEA-D59** 想法层 ERROR **不阻断 `pcp build`**：构建门禁只看非想法层 ERROR，
想法层 ERROR 与 WARNING 一样打印后继续构建。门禁的层次判定依据是**规则名**：
§58.1 全表的规则名构成封闭集合，实现为"rule ∈ 想法规则名 frozenset"的过滤；
**不得**以 `node_id ∈ project.ideas` 判定——文件级 issue 的 id 为 `None`，且
IDEA-D15 允许想法 id 与节点 id 撞号，该判据两头都会误判。

`pcp validate` 的退出码协议不变（存在任何 ERROR → 退出码 1）：它是审计命令，
"一次报告全部问题"是它的职责。由此产生的不对称是刻意的——`pcp validate` 退出 1
而 `pcp build` 成功，读作"有数据问题待修，但计划投影不受未承诺数据牵连"。若把
`pcp validate` 用作 CI 门禁，想法层 ERROR 会使门禁失败；这可接受（数据错误就是
错误），与构建门禁是两件事。

理由：IDEA-D48 只规定了规则的**作用域**（不反向约束节点），没有规定规则**后果**
的作用域。若不加本条，一个 `promoted-without-outcome` 就能让整个计划站点构建不
出来——未承诺的想法再次获得瘫痪计划本体的权力（与 IDEA-D58 同根）。

---

## §59 不变量（验收基准）

**IDEA-D49** 以下六条为想法层的验收基准，任何阶段的实现均须满足：

1. **capsule 纯净**：`context.py` 零改动；compact/full 任何模式不含想法内容；
2. **节点 schema 纯净**：`Node` 数据类零字段增删；关联只存在于想法侧；
3. **规划语义纯净**：进度计数（§24）、current_focus、ready queue、侧栏规划树
   均零感知想法；
4. **向后兼容**（分阶段，阶段 2 刻意收窄）：
   - **阶段 1**：无 `ideas/` 的既有项目，全部命令输出与 `pcp build` 产物**字节级
     不变**；
   - **阶段 2**：无 `ideas/` 的既有项目，`pcp build` 产物的**页面结构与可见内容
     不变**，且不新增页面、不新增导航入口（IDEA-D63）；允许的唯一差异是每页内嵌
     的 i18n payload 多出想法相关词条。

   收窄理由：`i18n.runtime_payload()` 把整张 `TRANSLATIONS` 原样序列化并嵌入
   **每一个**页面（运行时语言切换的单一翻译源），因此只要新增任何想法词条，所有
   项目的所有页面字节都会变。可选项只有三个：放弃运行时切换的单源设计（代价远
   大于收益）、按项目裁剪 payload（引入"同一份词表在不同项目产出不同页面"的复杂
   度）、承认这一处增量。取第三条，并把验收基准写成可执行的形式；
5. **确定性**：有想法的项目，同数据 + 同 PCP 版本 = 字节级相同的构建输出；
6. **失败域隔离**：任何想法文件的内容错误（YAML 语法、schema、引用）都不得使
   `pcp status` / `pcp context` / `pcp build` 失败或退出非零（IDEA-D58、IDEA-D59）。

---

## §60 CLI 面

**IDEA-D50** 想法层子命令（写入面维持极小：`ideas` 只读；想法的创建/编辑为手工
编辑 YAML；毕业自阶段 3 起可由 `pcp graduate` 代写两处编辑——与 `init`/`focus`
同级的第三条写命令，见附录 D.7）：

```
pcp ideas [--status OPEN|PARKED|PROMOTED|DISCARDED]    # 按状态分组列表（默认：全部状态）
pcp ideas --for NODE [--status ...]                    # 关联查询·祖先方向（时刻 A，IDEA-D30）
pcp ideas --for NODE --subtree [--status ...]          # 关联查询·子树方向（时刻 B，IDEA-D60）
```

参数与退出码语义：

- `--status` 可重复以选多个状态；与 `--for` 组合时取交集；
- 默认状态过滤：无 `--for` 时为全部状态，有 `--for` 时为 OPEN + PARKED（IDEA-D62）；
- `--subtree` 只在 `--for` 存在时有意义，单独给出报用法错误（退出码 2）；
- `--for` 指向未知节点 → 业务失败（退出码 1）；
- `ideas/` 不存在或想法集为空 → 正常退出（退出码 0），打印一行空态说明，不报错。

**IDEA-D51** 列表语义：按状态分组（OPEN → PARKED → PROMOTED → DISCARDED）。
每行展示：id、状态、标题、relates_to 紧凑形式、论据存在性标记（对标 / 方法论的
有/无 点标，IDEA-D22）、last_updated。

**IDEA-D61** 组内排序键为 `(last_updated 为空, last_updated 升序, id 升序)`——
**有时间戳的按时间升序在前（陈年想法浮顶），空时间戳的排在该组末尾**（展示，不
裁决；替代时限规则，对齐 D1 裁定）。

`last_updated` 是不校验的自由字符串（IDEA-D10）：若直接按字符串升序，默认值 `""`
会让"没填时间的想法"而不是"陈年想法"浮顶，恰好背离本条意图，故把空值单独排在
组末。非 ISO 8601 写法（如 `2026/8/5`）之间的相对顺序未定义——这是不校验格式的
已知代价，文档化即可，不引入日期解析。

CLI 与 ideas 页使用**同一排序**（IDEA-D54），避免同一份数据在两处顺序不一致。

**IDEA-D52** `pcp focus <idea-id>` 与 `pcp context <idea-id>` 报业务失败
（退出码 1），错误消息在既有 "unknown node" 基础上追加提示：该 id 是 IDEA 记录，
由 `pcp ideas` 管理。两个命令都要加：`pcp context IDEA-0007` 是同样自然的误输入，
而"capsule 永不含想法"（IDEA-D5）恰恰是此时需要告知用户的那件事。

**IDEA-D53** `pcp status` 输出零想法信息（不变量 3）。退出码协议（0/1/2）不变。

---

## §61 UI 投影

**IDEA-D54** 生成站点新增独立 `ideas.html` 页 + 侧栏独立入口（位于规划树之外的
独立区段，MVP 不带计数徽标）。按状态分组（OPEN / PARKED / PROMOTED / DISCARDED），
组内排序与 CLI 一致（IDEA-D61）；每条想法展示：id+状态+标题、detail、两组论据
（ref 为文本）、relates_to（链接到节点页）、outcome（链接到毕业节点）、
created/last_updated。

**IDEA-D63** 投影条件化：项目无 `ideas/` 目录或想法集为空时，**不生成
`ideas.html`、不渲染侧栏入口**，`pcp build` 的文件计数与 dist 内容按不变量 §59.4
处理。侧栏与 topbar 由 `base.html` 全站共享，无条件新增入口会改动每一个页面（含
全部节点页）；条件化是不变量 4 在阶段 2 还能守住的部分。

**IDEA-D55** 想法内容不得出现在：节点页、dashboard 计数、焦点标记、capsule、
侧栏规划树。（不变量 1–3 在投影层的落点。）

**IDEA-D56** i18n：en/zh 双语，本地化文案 + 原始枚举并陈（如 `开放 OPEN`），
对齐 LANG 惯例（语言不碰数据：id、note、detail 恒为作者原文）。构建确定性
（不变量 5）适用于 ideas 页。

---

## §62 实施分期与模块影响面

### 62.1 分期

**IDEA-D57** 三阶段，每阶段独立可发布、可回退：

| 阶段 | 交付 | 验收 |
| --- | --- | --- |
| 1（引擎） | model（Idea/IdeaStatus/Project.ideas）+ loader（ideas/，含 IDEA-D58）+ validator（§58 规则组）+ `pcp ideas`（两个查询方向）+ 测试 | 既有 229 测试全绿；不变量 1/2/3/5/6 成立；不变量 4 按**阶段 1 口径**（字节级不变）成立；必须有失败域用例：存在一个坏 YAML 想法文件时，`pcp status` / `pcp context` / `pcp build` 仍成功 |
| 2（投影） | generator/templates（ideas 页 + 侧栏入口，均按 IDEA-D63 条件化）+ i18n ×2 + README en/zh 更新 | 确定性构建；无想法项目按不变量 4 的**阶段 2 口径**验收（结构与可见内容不变、无新页面与新入口、仅 i18n payload 增量） |
| 3（扩展点，原"命名但未承诺"；`graduate` 已于 R4 落地） | `pcp graduate`（原子毕业+转录）已交付；`pcp close` 集成（时刻 B 制度化）仍候 PLAN 世界 | graduate 验收见 R4；close 集成与 V0.2 候选合流评审 |

### 62.2 模块影响面

| 模块 | 改动 | 关键约束 |
| --- | --- | --- |
| `model.py` | +`IdeaStatus`、+`Idea`、`Project.ideas: dict[str, Idea]` | **`Node` 零改动**（IDEA-D27） |
| `loader.py` | +`parse_idea`、+ideas/ 目录读取 | 目录缺失静默跳过；镜像 §51.3 全表；单文件读取失败降级为 issue，**不抛 `LoadError`**（IDEA-D58） |
| `validator.py` | +`_check_ideas` 规则组 | 独立性（IDEA-D48） |
| `graph.py` | **零改动** | 查询在 cli 层完成，但**必须复用** `ancestors()` / `subtree_ids()`：二者已防 parent 环，自行遍历 `parent` 链会死循环 |
| `context.py` | **零改动** | 不变量 1 的物理保证 |
| `generator.py` + `templates/` | +ideas 页、+侧栏入口（均条件化） | IDEA-D54/D55/D63 |
| `i18n.py` | +想法相关词条 ×2 locale | 语言不碰数据 |
| `cli.py` | +`pcp ideas` 子命令（`--status` / `--for` / `--subtree`）、+`pcp graduate` 写路径（行级手术 + 三段式原子性）、focus 与 context 提示、build 门禁排除想法层 ERROR | `ideas` 只读；`graduate` 为与 `init`/`focus` 同级的第三条写命令（IDEA-D50、附录 D.7）；门禁见 IDEA-D59 |
| 测试 | +`test_ideas*.py`、+`test_graduate.py` | 既有测试零修改 |

### 62.3 V0.2 候选关联

- `pcp graduate`：毕业向导（两文件原子写 + 论据转录自动化）——阶段 3 已实现，
  落地契约见附录 D.7；
- `pcp close` / 时刻 B 集成 / `CANCELLED` 终态：PLAN 世界自身缺口（§56.3），
  与本补章解耦并行。

---

## 附录 A YAML 示例

### A.1 对标型（现象层 + 原理层齐备）

```yaml
# .planning/ideas/IDEA-0007.yaml
id: IDEA-0007
title: 给 dashboard 加趋势对比视图
status: OPEN

detail: >
  想法原文：一段话以内，捕获时不要求任何结构。

relates_to: [P2]

benchmark_sources:
  - ref: docs/benchmarks/grafana-panels.md     # 仓库内路径，校验存在性
    note: Grafana 的 time-compare 面板证明该视图有稳定需求
  - note: Stripe dashboard 的月环比呈现         # 外部参照：仅 note，不链出仓库

methodology_sources:
  - ref: docs/method/heuristics.md
    note: 符合「可观测性前置」原则

outcome: ~

created: 2026-08-27
last_updated: 2026-08-27
```

### A.2 蓝海型（先验真空，试点即论据）

```yaml
# .planning/ideas/IDEA-0012.yaml
id: IDEA-0012
title: 领域自适应的推广顺序自学习
status: PROMOTED

detail: >
  现有垂域无成熟对标；假设：就绪度指标可由历史推广数据自学习。

relates_to: [P2-A]

benchmark_sources: []        # 先验真空：合法（IDEA-D21）
methodology_sources:
  - ref: docs/method/cross-domain-theory.md
    note: 从运筹学的在线学习理论泛化——样本不足时先探索后利用

outcome:
  node: P2-A5                # 早毕业为 INVESTIGATION：1 域试点验证假设
  note: 试点即论据；结论反哺本条 methodology 或另立新想法

created: 2026-08-27
last_updated: 2026-08-27
```

## 附录 B 边界裁定索引

| 编号 | 问题 | 裁定（一句话） | 章节 |
| --- | --- | --- | --- |
| A1 | 节点页反向看出处 | 不做；追溯住在想法侧，节点页查询属于 ideas 页 | §54.1/§61 |
| A2 | id 命名空间 | 共字符集、独立命名空间、跨世界引用带类型 | §51.4 |
| A3 | 毕业基数 | 1→1 目标（扇出走子树）；N→1 合流 | §55.2 |
| A4 | 毕业原子性 | 无事务；失败模式单向可检出 | §55.4 |
| A5 | 内联 ideas.yaml | 不做（合并冲突线性） | §51.1 |
| B1 | 想法 vs 节点 open_decision | scope 检验法：越出当前 scope 即想法 | §50.1（指引） |
| B2 | 早/晚毕业判定 | 不设规则，由目标节点类型表达；鼓励早毕业 | §55.1 |
| B3 | PARKED vs DEFERRED | 不同世界不同词汇，镜像心智、枚举不通 | §53.3 |
| B4 | 想法做 focus | 永不；`focus` 与 `context` 均报错加提示 | §60 |
| B5 | capsule 携带想法 | 任何模式都不；显式命令二次注入 | §56.1 |
| B6 | 毕业后迭代 | 不重开终态；新文件经节点枢纽 | §53.2/§54.2 |
| B7 | 毕业前分叉 | 独立新想法，自由文本提及 | §54.2 |
| B8 | 终止时想法分诊 | 终止触发时刻 B | §56.3/§57.3 |
| B9 | 蓝海空论据 | 合法；不产生 issue，只做展示标记（R1 修订） | §52.4 |
| B10 | 否决理由写在哪 | 只写 `detail`；`outcome` 是毕业桥专用字段 | §53.1 |
| B11 | 时刻 B 的查询方向 | 新增 `--subtree` 子树方向；祖先方向服务时刻 A | §54.3/§57.3 |
| B12 | PARKED 是否进入分诊 | 进入；`--for` 默认状态过滤为 OPEN + PARKED | §57.2 |
| C1 | 引用目标被删/被取代 | 删→ERROR；取代→合法 | §55.5 |
| C2 | 论证充分性的最高干预 | 展示；R1 后连 WARNING 也不产生（见 C7） | §50.3/§52.4 |
| C3 | 校验独立性 | 只约束想法，不反约束节点 | §58.2 |
| C4 | 闭环引环 | 二部图结构无环 | §54.4 |
| C5 | 坏想法文件的影响面 | 降级为 `invalid-idea-file` ERROR 并跳过，永不 `LoadError` | §51.3.1 |
| C6 | 想法层 ERROR 是否阻断 build | 不阻断；`pcp validate` 退出码协议不变 | §58.3 |
| C7 | 论证充分性是否产生 issue | 不产生；判断留在展示层 | §52.4 |
| C8 | 想法 issue 的可分辨性 | message 带 `idea '<id>': ` 前缀（文件级规则以路径代 id）；规则名前缀只覆盖部分规则，不承担此职责 | §58.1 |
| D1 | 想法坟场 | 无时限规则；陈年浮顶 + 两个制度时刻 | §60/§57 |
| D2 | 否决后复活 | 手工改状态；git 历史即追溯 | §53.2 |
| D3 | 规模膨胀 | 状态分组 + `--status` 旗标；不做检索/分页/标签 | §50.4/§60 |
| D4 | 陈年浮顶的排序键 | 空 `last_updated` 排组末；非 ISO 值顺序未定义 | §60 |
| D5 | 阶段 2 的向后兼容口径 | 收窄为结构与可见内容不变 + i18n payload 增量 | §59 |

## 附录 C 术语表

| 术语 | 定义 |
| --- | --- |
| IDEA 世界 / PLAN 世界 | 承诺之前 / 之后的两个体系；边界是"是否已进入规划图"（§50.2） |
| 毕业桥 | 想法进入 PLAN 世界的唯一动作，由 `outcome` 边承载（§55） |
| 枢纽规则 | 想法谱系经节点中转、永不想法互链（§54.2） |
| 分诊时刻 | 相关想法被强制过面的制度性时机：A=决策讨论、B=收尾/终止（§57） |
| 论据槽 | benchmark（现象层）/ methodology（原理层）两个先验论据字段（§52.1） |
| 后验补位 | 蓝海场景以试点生产论据：试点即论据（§52.4） |
| 语义闭环/表示开环 | 迭代闭环在查询与分诊层闭合，数据结构上节点不反向引用想法（§56.1） |
| 失败域隔离 | 想法数据的任何错误都不得使读取计划的命令失败：坏文件降级为 issue 并跳过，想法层 ERROR 不阻断构建（§51.3.1、§58.3、不变量 §59.6） |
| 祖先方向 / 子树方向 | 关联查询的两个方向：向上（服务时刻 A 的决策讨论）与向下（服务时刻 B 的收尾过目）（§54.3） |

## 附录 D 修订记录 R1

本轮修订依据是对现有实现（V0.1.2，8 模块 3704 行，229 个测试）的逐条核对。草案
声称的镜像先例全部属实（`missing-title` 在 loader、`ignored-node-file`、
`evidence-source-missing` 为 WARNING、`reference-escapes-repo` 为 ERROR、
`done-with-blocking-decision` 与 `blocked-without-blocker` 的严重度分工、
`_UniqueKeyLoader`），`Node` 零改动与 `context.py` 零改动在代码层面可行，229 这个
测试基数也已核实。以下是改动项与其代码依据。

### D.1 阻断级改动（原草案自相矛盾或承诺落不了地）

| # | 改动 | 代码依据 |
| --- | --- | --- |
| 1 | 不变量 4 收窄为分阶段口径（§59.4）；新增投影条件化 IDEA-D63（§61） | `i18n.runtime_payload()` 把整张 `TRANSLATIONS` 原样嵌入**每个**页面（`i18n.py` / `templates/base.html` 的 `pcp-i18n` script）；侧栏与 topbar 出自全站共享的 `_base_context()`；`pcp build` 的结束行会打印文件计数。三者叠加使"新增词条与页面后仍字节级不变"不可能成立 |
| 2 | 新增失败域隔离 IDEA-D58（§51.3.1）与 IDEA-D59（§58.3）、不变量 §59.6 | `loader._read_yaml()` 的任何失败都抛 `LoadError`，会使 `pcp status` / `pcp context` / `pcp build` 全部退出 2；`cmd_build` 只要存在任一 ERROR 就拒绝构建。原草案的 IDEA-D48 只约束了规则作用域，未约束规则**后果**的作用域 |
| 3 | DISCARDED 理由只写 `detail`（§53.1） | 原措辞允许写 `outcome.note`，但 IDEA-D32 要求 `outcome.node` 必填、IDEA-D38 对非 PROMOTED 的 outcome 报 WARNING——该路径必然同时触发一条 ERROR 与一条 WARNING |
| 4 | 新增子树方向查询 IDEA-D60（§54.3），§57.3 改用 `--subtree` | 原 §57.3 要求过目"子树相关"的想法，而 §54.3 只定义祖先方向，时刻 B 无命令可执行；`PlanningGraph.subtree_ids()` 已存在，补方向即可 |

### D.2 建议级改动

| # | 改动 | 理由 |
| --- | --- | --- |
| 5 | `open-idea-without-justification` 从规则表删除，改为展示标记（§52.4） | 与"捕获零门槛"冲突，且 `pcp build` 会逐条打印 WARNING；信息与 IDEA-D51 的存在性标记重复 |
| 6 | 新增排序裁定 IDEA-D61（§60），CLI 与 ideas 页统一排序 | `last_updated` 是不校验的自由字符串且默认 `""`，直接字符串升序会让"未填时间"而非"陈年"浮顶；原 §61 的 id 升序与 §60 的时间升序也不一致 |
| 7 | `unknown-field` → `idea-unknown-field`（§51.2/§58.1），新增 message 前缀 IDEA-D64 | `ValidationIssue` 只有一列 id 且节点与想法 issue 混排，撞号时（IDEA-D15）无法分辨层次 |
| 8 | §62.2 补"必须复用 `ancestors()` / `subtree_ids()`" | 二者已防 parent 环，而 parent 环只报 ERROR、不阻断加载；自行遍历会死循环 |
| 9 | 分诊查询默认含 PARKED（IDEA-D62，§57.2） | 两个制度时刻原本都只捞 OPEN，PARKED 再无被读到的时机，与 D1 裁定冲突 |

### D.3 小项

- §61 拼写 `DISCARRED` → `DISCARDED`；
- IDEA-D52 扩展到 `pcp context <idea-id>`（同样自然的误输入）；
- §60 补齐 `--status` 与 `--for` 的组合语义、`--subtree` 的用法约束、空态与退出码；
- §50.4 明确适用范围仅想法层（README 的 V0.2 候选"搜索 / 过滤"针对节点侧）。

### D.4 本轮未改动、需评审确认的裁定

- `pcp validate` 的退出码仍包含想法层 ERROR（§58.3）：把它用作 CI 门禁时，坏想法
  文件会让门禁失败。若认为未承诺数据不应影响 CI，则需要另开一个裁定（例如给
  `pcp validate` 加作用域旗标），本轮**未**引入，以免扩张 CLI 面。

> **状态（R3 时点）：仍未裁定，且「把 `pcp validate` 接进 CI」是它的触发条件。** 阶段 1、阶段 2 均未改动 `pcp validate` 的退出码协议，`IDEA-D59` 的不对称（validate 退出 1 而 build 退出 0）是刻意的，不变量 §59.6 本就只保 `pcp status` / `pcp context` / `pcp build`。接 CI 时的建议方向是**给 `pcp validate` 加作用域旗标**（D.4 自己提的方案），而不是改默认退出码——人工执行 validate 应保持最大信息量，CI 门禁用旗标绕开想法层。**在裁定之前不得把 `pcp validate` 作为 CI 门禁**，否则一个坏想法文件会让门禁失败。

### D.5 修订记录 R2（P3 措辞修正）

| # | 改动 | 依据 |
| --- | --- | --- |
| 1 | `invalid-idea-file` 收窄为"文件无法解析为 YAML"（语法错误 / 重复键 / 不可读）；"解析成功但顶层非 mapping"归 `invalid-idea`，两规则触发条件互斥（§51.3.1、§58.1） | 节点先例：合法 YAML 非 mapping → `invalid-node`（`parse_node` 对非 dict 数据的处理）；原措辞使两条规则都认领同一触发条件 |
| 2 | IDEA-D64 前缀约定对文件级规则加豁免（以仓库相对路径代 id）；IDEA-D47 同步注明文件级 issue 的 `node_id` 为 `None`；附录 C8 对齐 | `invalid-idea-file` 触发时文件解析失败，`idea '<id>': ` 前缀不可达 |
| 3 | IDEA-D59 补门禁的层次判定依据：规则名 frozenset，禁止按 `node_id ∈ project.ideas` 判定（§58.3） | 文件级 issue 的 id 为 `None`、IDEA-D15 允许撞号，id 判据两头误判；规则名是封闭集，无需给 `ValidationIssue` 加字段 |

### D.6 修订记录 R3（阶段 2 实施发现）

| # | 改动 | 依据 |
| --- | --- | --- |
| 1 | 不变量 §59.4 阶段 2 的「允许的唯一差异是 i18n payload」补一条：`assets/style.css` 允许**只增不改**的想法层样式增量，且全部选择器须以 `.idea-` / `.ideas-` / `.sidebar-extra` 前缀命名 | `style.css` 是全站共享的单一静态资源，由 `build_site()` 逐字节复制进每个项目的 dist（`generator.py:81` 的 `_STATIC_FILES` + `generator.py:780-783` 的复制循环，docstring `generator.py:745` 明写 "copied verbatim"）。想法页与侧栏入口需要样式，而侧栏入口出现在有想法项目的**每一个**页面上（含节点页），因此样式必然作用到全站。选择器前缀约束使这些规则在无想法项目上不匹配任何元素——「页面结构与可见内容不变」的实质因此成立，字节层面则与 i18n payload 属同一类不可避免的共享资源增量。「只增不改」由两道闸合起来固定：`test_idea_css_cannot_restyle_pages_that_have_no_ideas`（新增规则不外溢——前缀 + 禁 at-rule）与 `test_idea_css_is_append_only_over_phase1`（既有规则不被改写——对 `main` 版 stylesheet 的字节前缀断言）。<br><br>**落选方案与否决理由**（照 R1 第 1 条的体例记全，以免后续评审重开同一条杠）：<br>① **条件化独立 `ideas.css`**——字面上最干净（不变量 4 一字不改），但要给 `_STATIC_FILES` 的无条件复制循环开洞、打破 `generator.py:745` "copied verbatim" 的建产线契约，使资产集合随项目而变。那是**主 spec §22 层面**的改动，本补章无权自行修改；用主 spec 的永久复杂度换补章的一行修订，方向反了。<br>② **样式内联进 `ideas.html`**——覆盖不到节点页：侧栏入口出自全站共享的 `base.html`，有想法项目的每个页面都渲染它。<br>③ **放弃侧栏入口、只从 dashboard 进**——既推翻 IDEA-D54，又**不消除冲突**：`ideas.html` 自身的样式照样要进 `style.css`，无想法项目的字节照样变。只有叠加方案 ② 才成立，等于两笔成本换免写一条修订 |
| 2 | IDEA-D54 的「侧栏独立入口」明确为：位于侧栏规划树 `<nav>` 之后的独立 `<nav class="sidebar-extra">` 区段，条件化渲染 | 规划树 `<nav>` 内新增任何条目都会让想法进入侧栏规划树，与不变量 3 冲突 |
| 3 | 记录阶段 2 的排序实现：`IDEA-D61` 的排序键实现为 `model.idea_sort_key()`，CLI 与 ideas 页共用同一函数 | 「CLI 与 ideas 页使用同一排序」若靠两处各写一遍，只能靠纪律维持；提到共享函数后由 `test_idea_sort_key_is_shared_by_cli_and_generator` 固定 |

### D.7 修订记录 R4（阶段 3 实施：`pcp graduate`）

| # | 改动 | 依据 |
| --- | --- | --- |
| 1 | `pcp graduate` v1 的契约：只接线**既有**目标节点（`--to NODE`），不代建节点 | 代建节点意味着代写规划语义（type/parent/objective/scope 均是作者决策，§55.1 的毕业形态选择权在作者）；保持写入面最小（IDEA-D50）。手动流程"先建节点、后登记出处"的顺序因此保留，其半途状态（节点已建、想法仍 OPEN）本就是 §55.4 认定的"无害不可见" |
| 2 | 接受的源状态为 OPEN 与 PARKED；拒绝 PROMOTED（§54.2：毕业后迭代必须新建想法文件，不得重开终态）与 DISCARDED（§53.2：复活先回 OPEN，新证据先落盘再毕业）；非受控枚举值拒绝并指向 `pcp validate` | §53.2 迁移表是规范动作而非校验规则（不设迁移校验），命令作为 spec 原生工具按规范动作执行；PARKED→PROMOTED 虽不在表内，但 PARKED 是未承诺状态，直接毕业等价于"分诊结论：现在做"，不抹除任何历史 |
| 3 | 写入方式为**行级 YAML 手术**（`_top_level_key_span` / `_set_top_level_key` / `_append_to_top_level_list`，均在 `cli.py`）：只替换目标键块，其余字节原样，作者注释与 CRLF 保留（沿用 `pcp focus` 先例）；`evidence_sources` 为 flow 写法（`[a, b]`）时**拒绝执行**并提示改为块写法 | 节点/想法文件是手工 YAML，任何整文件重写（yaml dump）都会摧毁注释与排版；flow 列表的机械追加无法保真，拒绝比猜更强 |
| 4 | 原子性实现为三段式：全部拒绝判定先于首个字节写入；两文件写完后**重新加载真实文件**验证（PROMOTED + `outcome.node` + 证据已入列），失败则恢复两个原始文本；文件系统中途崩溃窗口仍存在，不劣于手工流程 | IDEA-D35 只承诺消除"可检出的半途状态"：pre-write 拒绝消除 `missing-outcome-target` 与状态违规，verify+restore 消除"写坏文件"；跨文件崩溃窗口由 git 承载（数据是源，§37） |
| 5 | 转录目标必须是 `nodes/` 下的独立文件；`roadmap.yaml` 内联节点被拒绝（提示先移出） | 内联节点的 YAML 是列表中的一项，行级手术没有安全的锚点；且每节点一文件本就是仓库惯例（与 IDEA-D8 的同源理由：合并冲突线性） |
