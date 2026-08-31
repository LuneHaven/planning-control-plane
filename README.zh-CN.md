# Planning Control Plane（规划控制平面）

[English](README.md) | 简体中文

**把长期规划留在仓库，而不是聊天记录。**

PCP 是一个用于管理长期 AI 协作规划的命令行工具。它先把项目的目标、
决策、范围和进度保存为 `.planning/` 下的 YAML 数据，并随 Git 一起
版本化，规划因此不再依赖某一次聊天会话；在此基础上，`pcp build`
把这些数据渲染成一个完全离线的静态 Dashboard（仪表盘），帮助你
随时查看当前进展，并从上次中断的位置继续工作。

![规划总览](docs/screenshots/dashboard-zh.png)

## PCP 解决什么问题

长期规划如果只存在于聊天会话中，通常会出现三个问题。

**第一，上下文无法稳定延续。**新会话不知道之前已经确定了哪些约束、
哪些决策，很多背景需要重新解释。

**第二，决策开始漂移。**即使某个结论已经确定，后续讨论仍可能在
不知情的情况下把它重新讨论一遍，没有人会为了确认结论去重读 400
条消息里的第 40 条。根源在于：已经做出的决策没有沉淀为持续可见的
规划状态。

**第三，讨论边界开始扩大。**当上下文和决策都不稳定时，本轮原本
只需要解决一个局部问题的讨论，很容易逐渐扩展到其他问题。

这三个现象指向同一个根因：**长期规划没有成为项目中持续存在的
状态。**

任务追踪器主要回答「谁在做什么」；PCP 记录的是另一层信息：这件事
为什么现在做、有哪些约束、已经决定了什么、这次讨论做到哪里为止、
下一步该继续什么。任务分派照旧留在你的追踪器里。

PCP 与规范文档之间也有一条边界：**PCP 管「规划」，不管「规范」。**
产品、治理、架构和实现的规范仍归你的正式文档所有；PCP 只记录规划
过程中形成的结构、决策和进度，通过链接引用这些规范（见
[权威边界](#权威边界authority-boundary)）。

## 核心思路

PCP 的核心可以概括成先后衔接的三件事。

### 1. 先把规划变成项目的一部分

**规划数据是源头，HTML 只是投影。**规划数据以 YAML 形式保存在
`.planning/` 中，并随仓库一起提交；Dashboard 只是这些数据的展示
结果，可以随时删除并重新生成。需要随仓库长期保存的只有规划数据，
页面随时可以重建。

### 2. 再让规划沿层级持续继承

规划节点组成一棵树，从 `PROGRAM`、`PHASE`、`STRATEGY` 一直到更
具体的工作节点。父节点已经冻结的决策，以及已经声明的范围边界，
会自动继承到子节点并保持显示。这样，规划越往下细化，就越不需要
重新解释已经确定的约束和决策。

### 3. 最后让下一次会话可以从中断处继续

任意时刻只有一个当前焦点（Current Focus），表示当前真正需要推进
的节点。`pcp context` 根据这个节点生成 **Context Capsule（上下文
胶囊）**：一段紧凑、自包含的恢复状态。把它粘贴到新的 AI 会话（或
发给同事），即可直接从当前状态继续工作，不需要翻找历史聊天记录。

此外，PCP 的输出是确定性的，并且完全离线：相同的规划数据加相同的
PCP 版本，产生字节级一致的输出；生成的页面不引用任何 CDN 或远程
字体，也不发出任何网络请求，双击打开即可使用。

## 一个完整的工作循环

一次完整的工作过程可以概括为一条链：读取状态 → 恢复上下文 → 工作
→ 固化结果 → 校验 → 进入下一个焦点。

```text
读取当前焦点（pcp build → 打开 Dashboard）
    ↓
恢复上下文（pcp context → 把胶囊粘贴到新的 AI 会话）
    ↓
只在当前分支工作（讨论结论作为决策写进节点 YAML）
    ↓
把属于规范的结论回写到规范文档，节点里只保留链接
    ↓
更新节点状态（status / 三条轨道 / next_action / last_updated）
    ↓
校验并重建（pcp validate → pcp build，CI 用 pcp build --check）
    ↓
切换焦点（pcp focus <下一个节点>），进入下一轮循环
```

循环的每一步产物都落盘，因此可以在任意位置中断，之后随时恢复。

## 功能一览

**核心规划模型**

- **规划图**：节点以树组织，支持依赖、阻塞、关联、取代四种关系，
  整图校验（含环检测）
- **四类决策**：Frozen / Open / Blocking / Deferred，分类存储、
  沿树继承，不会静默丢失
- **范围边界**：每个节点显式声明本轮要做与不做的事，祖先声明的
  条目继承并显示
- **三条独立轨道**：讨论、回写、实施三项状态分别记录，互不推导

**工作定位与恢复**

- **当前焦点**：当前最应该推进的唯一节点，在 Dashboard 与规划
  树中高亮显示
- **上下文胶囊**：`pcp context` 输出可直接粘贴的恢复状态，节点页
  提供一键复制

**展示与治理**

- **静态 Dashboard**：确定性生成、完全离线，支持深色模式，内容
  按需分层展开
- **中英双语界面**：English 与 简体中文，在浏览器内即时切换
- **权威边界**：PCP 只管规划本身，规范文档归仓库所有，只链接、
  不取代
- **想法层**：`.planning/ideas/` 捕获尚未承诺的想法，损坏的想法
  文件不阻断规划

## 安装

需要 Python 3.11+。推荐用 pipx 或 uv 安装（独立环境，不受 PEP 668
externally-managed 限制）：

```bash
pipx install planning-control-plane     # 或：uv tool install planning-control-plane
pcp --help
```

`pip install planning-control-plane` 也可以（建议放在虚拟环境里）。运行时
依赖只有 PyYAML 和 Jinja2。

## 快速开始

在你自己的仓库里：

```bash
cd my-project

pcp init          # 生成 .planning/{project.yaml, roadmap.yaml, nodes/, .gitignore}
```

创建第一个规划节点 `.planning/nodes/N1.yaml`：

```yaml
id: N1
title: 确定部署方案
type: DISCUSSION
status: DISCUSSING

objective: >
  在程序级已冻结的约束下，决定本服务的部署方式。

scope:
  - 部署工具链
  - 环境拓扑
out_of_scope:
  - 应用重构
  - 团队人员安排

next_action: >
  对照就绪标准比较两个候选工具链。

discussion_status: IN_PROGRESS
writeback_status: N/A
implementation_status: N/A
last_updated: 2026-08-18
```

然后：

```bash
pcp focus N1      # 设定当前焦点（写入 project.yaml）
pcp validate      # 结构 + 一致性校验
pcp build         # 生成 .planning/dist/
```

用浏览器打开 `.planning/dist/index.html`（直接双击即可，站点完全离线）。
继续在终端里：

```bash
pcp status        # 概览：焦点、阻塞、进度计数
pcp context       # 当前焦点的上下文胶囊
```

如果想直接体验现成示例，可以看
[`examples/demo-project-zh`](examples/demo-project-zh)。这是一个虚构的
示例仓库，含一棵七个节点的中文规划树，可立即 `pcp build`；
[`examples/demo-project`](examples/demo-project) 是同类场景的英文版本。
两者是各自独立的规划数据，不是彼此的翻译（原因见
[界面语言](#界面语言)）。

## 核心能力

其中大部分能力在下面五节展开，界面语言与权威边界见后文各自章节。

### 规划图：结构与继承

规划节点组成一棵树：`PROGRAM → PHASE → STRATEGY → …`，一直到最
具体的工作节点。节点类型是受控枚举：`PROGRAM`、`PHASE`、`STRATEGY`、
`DISCUSSION`、`DECISION`、`INVESTIGATION`、`IMPLEMENTATION`、
`CLOSURE`。

除父子关系外，节点之间还可以声明依赖（`depends_on`）、阻塞
（blocking）、关联（related）、取代（supersedes）关系；PCP 对整张图
做一致性校验，包括环检测。

继承沿着这棵树向下发生：父节点冻结的决策与声明的范围边界，会自动
出现在子节点里并保持显示，让它们始终可见，不必反复重新争论。

### 决策、范围边界与三条轨道

每个节点有四类决策清单：

- *Frozen（已冻结）*：已定；子节点继承，不应无意识推翻
- *Open（未决）*：已识别、未定
- *Blocking（阻塞）*：未解决且阻止收尾（`DONE` + blocking → 校验 ERROR）
- *Deferred（已延期）*：明确推迟

每个节点还显式声明范围边界：`scope`（本轮要做）与 `out_of_scope`
（本轮不做）两个清单；祖先声明的条目会继承下来并显示，标明边界所在。

节点状态表达的是规划生命周期，不是看板：`NOT_STARTED`、`DISCUSSING`、
`INVESTIGATING`、`DECIDED`、`WRITEBACK_PENDING`、`WRITEBACK_DONE`、
`READY`、`IMPLEMENTING`、`BLOCKED`、`DONE`、`DEFERRED`。

每个节点有三条独立轨道：`discussion_status` / `writeback_status` /
`implementation_status` ∈ `NOT_STARTED`、`IN_PROGRESS`、`DONE`、`N/A`。
三项状态之所以分开存放，是因为现实流程并不同步：「讨论完成」不意味
着「规范已经回写」，「规范已经回写」也不意味着「代码已经实施」，
因此任何一项都不由另外两项推导得出。一个纯讨论节点可以是
Discussion `DONE` + Writeback `DONE` + Implementation `N/A`。

### 当前焦点与上下文胶囊

任意时刻只有一个**当前焦点（Current Focus）**，表示当前最应该推进
的节点，在 Dashboard 与规划树中高亮显示。

**上下文胶囊不是摘要，而是一次工作会话的最小恢复状态。**它只为一个
目的存在：让一个新的 AI 会话不经过任何翻找，直接恢复当前节点的
工作。

```bash
pcp context            # 当前焦点的紧凑胶囊
pcp context P2-A4      # 任意节点
pcp context --full     # 追加祖先摘要、关联节点、已延期决策
```

胶囊只携带恢复当前工作所需的内容：该节点的目标、继承的已冻结决
策、范围边界、未决与阻塞决策、来源与三条轨道的状态。把胶囊粘贴到新的 AI 会话作为开场上下文（或发给同事），即可
从当前状态继续工作。节点页的「恢复这项工作」面板展示同一份胶囊，
并带一键复制按钮。

![恢复这项工作](docs/screenshots/node-zh-resume.png)

### 想法层

不是所有想法都应该立刻进入规划。真实项目里经常出现一些刚刚产生的
念头：值得记录下来，但还没有经过讨论，也没有承诺要做。如果一开始
就把这些内容放进规划图，规划本身就会不断膨胀。

因此 PCP 把两者分开：**规划节点表示「已经进入计划的工作」；想法表示
「值得保留、但尚未承诺的内容」。**`.planning/ideas/` 就是这个缓冲层。
记录一个想法可以非常轻量，不要求一开始就具备完整的结构、论据或
方法论依据；只有当一个想法真正进入计划时，它才「毕业」为正式的
规划节点。

```
.planning/ideas/IDEA-0007.yaml     # 每个想法一个文件（直接放在 ideas/ 下，.yaml 后缀）
```

```yaml
id: IDEA-0007
title: Add a trend comparison view to the dashboard
status: OPEN                       # OPEN | PARKED | PROMOTED | DISCARDED
detail: One paragraph. Capture asks for no structure.
relates_to: [P2]                   # 这个想法关联的规划节点
benchmark_sources:                 # 竞品或成熟产品实际怎么做
  - ref: docs/benchmarks/grafana-panels.md
    note: Grafana 的对比面板说明该需求是稳定的
  - note: Stripe 的月环比面板              # 仓库外：只写 note
methodology_sources:               # 方法论依据，与具体产品解耦
  - ref: docs/method/heuristics.md
outcome: ~                         # 想法「毕业」为节点时填写
created: 2026-08-27
last_updated: 2026-08-27
```

想法层遵循四条核心规则：

- **记录零门槛。**`benchmark_sources` 和 `methodology_sources` 完全
  留空也是合法状态，不会触发任何 WARNING，鼓励随手记录。
- **唯一入口。**想法进入规划图必须经过「毕业」（graduate）：先创建
  对应的规划节点，再把想法文件里的 `outcome.node` 指向它。这一步
  可以手工完成，也可以用 `pcp graduate IDEA-0007 --to P2-A5`，后者
  还会把带 `ref` 的论据条目一并复制进节点的 `evidence_sources`。
  节点永远不会反向引用想法，因此读规划时不会牵扯到未完成的想法。
- **想法不会破坏计划。**设计原则是：想法是旁路数据，不能成为规划
  主链路的单点故障。想法文件格式错误时，校验只记一条 issue，然后
  忽略这个想法；`pcp status` / `pcp context` / `pcp build` 照常工作，
  想法层的 ERROR 也不阻断构建。
- **上下文胶囊永不含想法。**`pcp context` 只携带规划数据；想看某个
  节点相关的想法，要显式执行 `pcp ideas --for <node>`。

只有当项目中已有想法时，生成的站点才会多出 `ideas.html` 页与侧栏
入口。

想法层还有一条贯穿的规则：**`id` 是身份，文件名只是索引。**具体到
工具行为：

- 文件名与文件内的 `id` 不一致时，`pcp validate` 报
  `idea-filename-mismatch` 警告，不阻断，改名即可。
- `pcp ideas` 的最后一行会提示下一个可用的编号（`IDEA-<NNNN>`）。
  分配时同时参考已加载的 id 与磁盘上现有的文件名，所以它永远不会
  指向一个已经存在的文件。

### Dashboard：只回答四个问题

![节点详情](docs/screenshots/node-zh.png)

**Dashboard 不试图展示所有信息，只回答四个问题**，并且按你工作时
的自然顺序排列：

```text
现在在哪？             （当前焦点）
    ↓
有什么在阻塞？         （需处理项）
    ↓
焦点周围是什么？       （焦点分支）
    ↓
接下来可以开始什么？   （就绪队列）
```

- **侧栏**承载完整规划树，含状态、焦点标记与展开/折叠。
- **节点页**按控制面优先级排列：sticky header（节点 ID、状态、三条
  轨道、复制上下文）→ 下一步行动 → 目标 → 范围边界 → 决策（阻塞 →
  未决 → 已冻结，继承分组按祖先折叠）→ 关联 → 来源 → 恢复这项工作。
- 会掩盖要点的细节默认折叠（继承的已冻结决策、已延期决策、完整的
  上下文胶囊），条数始终可见。

## `.planning/` 结构

```
.planning/
├── project.yaml    # 项目 id/名称、current_focus、authority roots、ui.locale
├── roadmap.yaml    # 可选的内联节点清单
├── nodes/          # 每个规划节点一个 YAML 文件
└── dist/           # 生成站点（gitignore，可随时丢弃重建）
```

## 节点示例

摘自 `examples/demo-project-zh/.planning/nodes/P2-A4.yaml`：

```yaml
id: P2-A4
title: 推广就绪度预检
type: DISCUSSION
parent: P2-A
status: NOT_STARTED
objective: >
  对第一批推广领域做就绪度预检 ...
scope:
  - 第一批领域的就绪度核对
  - 阻塞问题的上报与升级
out_of_scope:
  - 修改就绪标准（已在 P2-A2 冻结）
open_decisions:
  - id: OD-401
    summary: 佐证材料要到什么程度，才能判定第一批领域已经就绪？
blocking_decisions:
  - id: BD-401
    summary: 推广执行开始之前，是否必须由门禁负责人签字确认？
depends_on: [P2-A3]
canonical_sources:
  - docs/rollout/readiness-criteria.md
evidence_sources:
  - docs/notes/2026-08-15-sequencing-review.md
next_action: >
  先和门禁负责人裁决 BD-401，再逐条走完就绪标准检查清单。
discussion_status: NOT_STARTED
writeback_status: N/A
implementation_status: N/A
last_updated: 2026-08-17
```

## AI Harness 集成

PCP 不只给人使用，也可以让 AI coding harness 按同一套规划流程工作。
要让 AI 正确使用 `pcp`，需要告诉它两类信息，分别由两份资产承载。

**第一类信息是「这个仓库应该怎么工作」。**由 AGENTS.md 段落承载，
在每个仓库执行一次：

```bash
pcp agents >> AGENTS.md
```

它写入仓库自身的规则、文档约定与 PCP 会话工作流。AGENTS.md 是多数
harness 原生支持的开放标准（Codex、Cursor、Gemini CLI、ZCode……）；
Claude Code 只读 `CLAUDE.md`，可以用一个只含 `@AGENTS.md` 的
`CLAUDE.md` 来桥接。

**第二类信息是「PCP 这个工具本身怎么使用」。**由
[`integrations/skills/pcp/SKILL.md`](integrations/skills/pcp/SKILL.md)
承载：它是工具手册，与任何仓库的规则无关。一份内容，多个安装位置：

```bash
# 用户级，跨 harness 共享（ZCode 会扫描 ~/.agents/skills/）
mkdir -p ~/.agents/skills/pcp
curl -fsSL https://raw.githubusercontent.com/LuneHaven/planning-control-plane/main/integrations/skills/pcp/SKILL.md \
  -o ~/.agents/skills/pcp/SKILL.md
```

Claude Code 不扫描 `~/.agents/`，要在 `~/.claude/skills/pcp/` 单独
为它装一份。如果要团队共用，就把 SKILL.md 提交到仓库的
`.agents/skills/pcp/`。Skill 随仓库分发，不随 Python 包安装：它是
harness 资产，不属于 PCP 运行时；运行时适配器与插件仍不在范围内
（见路线图）。

两份资产的分工由此确定：仓库规则只写在 `AGENTS.md`，命令手册只写在
`SKILL.md`，没有需要保持同步的重复内容。

## CLI

| 命令                                                | 作用                                                                                                                    |
| ------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `pcp init`                                        | 生成 `.planning/` 骨架；绝不覆盖已有文件（`--force` 只补建缺失文件）                                                                        |
| `pcp agents`                                      | 打印可直接粘贴的 AGENTS.md 段落，让 AI harness 知道本仓库的 PCP 工作流。只读；用 `pcp agents >> AGENTS.md` 自行追加                                 |
| `pcp validate`                                    | 结构 + 规划一致性校验，逐行输出（`ERROR`/`WARNING` + 节点 + 规则 + 原因）                                                                   |
| `pcp build`                                       | 先校验，再确定性重建 HTML 输出目录                                                                                                  |
| `pcp build --check`                               | 在临时目录重新生成并比对，检测输出是否过期（CI 用）                                                                                           |
| `pcp status`                                      | 终端概览：项目、当前焦点、决策计数、进度计数                                                                                                |
| `pcp context [node] [--full]`                     | 输出上下文胶囊（默认当前焦点）                                                                                                      |
| `pcp focus [node]`                                | 查看或切换当前焦点（对 `project.yaml` 做行级编辑，保留注释）                                                                                |
| `pcp ideas [--status S] [--for NODE [--subtree]]` | 按状态分组列出想法层，`--for` 筛选与某节点相关的想法 |
| `pcp graduate IDEA --to NODE [--note TEXT]` | 将想法正式纳入规划，并记录其来源 |

全局参数 `-p/--project-root PATH` 指定目标仓库根目录（其余命令从该目录
向上查找 `.planning/`）。

退出码：`0` 成功 · `1` 预期失败（如校验错误、未知节点、产物过期）·
`2` 用法/加载错误。

## 界面语言

界面支持 English 与 简体中文。

- **项目默认语言**：`.planning/project.yaml` 的 `ui.locale`：
  ```yaml
  ui:
    locale: zh-CN     # 或 en（默认）
  ```
- **运行时切换**：顶栏有 `English / 中文` 切换控件。切换在浏览器内即时
  完成：不重新 build、不刷新、不联网。偏好保存在 `localStorage`，跨页面
  跳转与刷新后仍然有效；清除后回落到项目默认。`project.yaml` 永不被修改。
- **界面语言与规划数据分离**：标识符与原始值（节点 ID、决策 ID、存储的枚举值）、
  你撰写的文本（标题、摘要、`pcp context` 胶囊）在任何语言下都保持
  原值。详细状态视图同时显示「本地化文案 + 原始枚举」（如
  `未开始 NOT_STARTED`），机器可读的值始终可搜索。

> 语言切换改的只是 PCP 的界面文案；
> 项目自身的规划内容保持作者原文，不会被自动翻译。

正因为界面语言不会改变规划数据，本仓库提供两份示例项目而不是一份：
[`examples/demo-project`](examples/demo-project) 存放英文规划数据，
[`examples/demo-project-zh`](examples/demo-project-zh) 存放中文规划数据。
本文档的中文截图来自中文示例项目，而不是把英文示例切到中文界面得到的。

## 架构

| 层          | 位置                                                      | 归属           |
| ---------- | ------------------------------------------------------- | -------------- |
| PCP engine | `src/planning_control_plane/`（本仓库）                      | 独立的 pip 安装工具 |
| 规划数据       | `<你的仓库>/.planning/{project.yaml, roadmap.yaml, nodes/}` | 你的仓库         |
| 生成的 HTML   | `<你的仓库>/.planning/dist/`                                | 你的仓库（可随时重建）  |

模块：`model.py`（枚举与数据模型）· `loader.py`（容错 YAML 加载）·
`graph.py`（树/图操作）· `validator.py`（校验规则）· `context.py`
（上下文胶囊）· `i18n.py`（界面翻译表，单一来源、逐页内嵌）·
`generator.py` + `templates/`（确定性 HTML 生成）· `cli.py`。

## 权威边界（Authority Boundary）

PCP 的权威仅限**规划结构与规划进度**。产品、治理、架构与实现的
规范语义仍归你项目自己的文档所有；PCP 只链接它们
（`canonical_sources` / `evidence_sources`），不复制、不判定其内容。每张
生成页面都在页脚声明这一点。

## 当前状态

**当前版本：V0.1.3**（已发布到
[PyPI](https://pypi.org/project/planning-control-plane/)），处于可用的
MVP 阶段，并已在真实项目中完成自用验证：引擎、CLI、校验器、胶囊与
双语界面均已可用，自动化测试共 409 项。

## 路线图

明确**不做**：多人协作、服务器/云同步、数据库、GitHub/PR 集成、AI
插件、自动摘要或自动决策、语义搜索、Jira/Notion 替代。

已命名但未实现的扩展点（暂无接口）：`pcp prompt`、`pcp close`、
`pcp reopen`、Git/GitHub 适配器、Claude Code / Codex / ChatGPT 适配器、
多项目工作区。

V0.2 候选项（均未实现，不构成承诺）：

- close / reopen 工作流
- prompt 生成
- 集成状态
- 搜索 / 过滤
- 多项目工作区

## 参与贡献

欢迎 issue 与 pull request。开发环境：

```bash
pip install -e ".[dev]"
python -m pytest
```

## 许可证

[MIT](LICENSE)
