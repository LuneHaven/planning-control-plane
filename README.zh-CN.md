# Planning Control Plane（规划控制平面）

[English](README.md) | 简体中文

**把长期规划的上下文放在仓库里，而不是放在聊天记录里。**

PCP 是一个命令行工具：把 AI 协作项目的规划过程（目标、决策、范围、进度）
存成 `.planning/` 下的 YAML 文件，随 git 提交持久保存；`pcp build` 再把
它们渲染成完全离线的静态 dashboard。

![规划总览](docs/screenshots/dashboard-zh.png)

## PCP 解决什么问题

在聊天会话里讨论长期规划，通常会遇到三类问题：

- **上下文丢失**：新会话（或新的一周）不再记得父级约束和已经做出的决策。
- **决策漂移**：后续讨论无意识推翻已冻结的决策；没人会去重读 400 条
  消息里的第 40 条。
- **范围漂移**：讨论范围悄悄扩大，越过了这一轮本该决策的边界。

任务追踪器回答「谁在做什么」；PCP 回答「讨论的上下文与边界去了哪里」。
任务分派照旧留在你的追踪器里，PCP 只管规划过程。

## 核心思路

1. **规划数据是源头，HTML 只是投影。** Planning Graph 以纯 YAML 的形式
   存放在 `.planning/` 下，随仓库提交。`pcp build` 把它渲染成一个可随时
   删除重建的静态站点。
2. **决策与范围边界沿规划树继承。** 节点构成规划树（`PROGRAM → PHASE →
   STRATEGY → …`）。每个子节点都会**继承并展示**父节点冻结的决策
   （Frozen Decisions）与范围边界（Scope Boundary），让它们始终可见，
   不必反复重新争论。
3. **随时可以从断点继续。** 任一时刻只有一个当前焦点（Current Focus）。
   `pcp context` 输出 **Context Capsule（上下文胶囊）**：一段紧凑、
   自包含的恢复文本，粘贴到新的 AI 会话（或发给同事），即可接着上次
   继续。
4. **确定性输出，完全离线。** 相同的规划数据 + 相同的 PCP 版本 =
   字节级相同的输出。生成页面不引用任何 CDN 或远程字体，也不发出任何
   网络请求；双击打开（`file://`）即可使用。

## 功能

- **Planning Graph（规划图）**：节点之间支持 parent / dependency /
  blocking / related / supersedes 五种边；对整张图做校验（含环检测）
- **Current Focus（当前焦点）**：下一个会话应推进的唯一节点，在
  dashboard 与规划树中高亮显示
- **Frozen / Open / Blocking / Deferred 四类决策**：分类存储、沿树继承、
  不会静默丢失
- **Scope Boundary（范围边界）**：每个节点显式声明本轮要做 / 本轮不做；
  祖先声明的条目会继承下来一并显示，标明边界所在
- **三条独立轨道**：讨论、回写、实施三项状态分别存储，任何一项都不由
  另外两项推导得出
- **Context Capsule**：`pcp context <node>` 输出可直接粘贴的恢复文本；
  节点页有「复制上下文」按钮，一键复制
- **静态 dashboard**：确定性生成、完全离线，支持深色模式；
  内容按需分层展开
- **中英双语界面**：English 与 简体中文，在浏览器内即时切换
- **权威边界**：PCP 只管规划本身；规范文档归你的仓库所有，
  PCP 只链接，不取代
- **想法层**：`.planning/ideas/` 捕获尚未承诺的想法，`pcp ideas` 负责
  列出与筛选；想法文件格式错误只会降级为一条校验 issue，
  绝不影响规划本身

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
pcp context       # 当前焦点的恢复 capsule
```

如果想直接体验现成示例，可以看
[`examples/demo-project-zh`](examples/demo-project-zh)。这是一个虚构的
示例仓库，含一棵七个节点的中文规划树，可立即 `pcp build`；
[`examples/demo-project`](examples/demo-project) 是同类场景的英文版本。
两者是各自独立的规划数据，不是彼此的翻译（原因见
[界面语言](#界面语言)）。

## CLI

| 命令                                                | 作用                                                                                                                    |
| ------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `pcp init`                                        | 生成 `.planning/` 骨架；绝不覆盖已有文件（`--force` 只补建缺失文件）                                                                        |
| `pcp agents`                                      | 打印可直接粘贴的 AGENTS.md 段落，让 AI harness 知道本仓库的 PCP 工作流。只读；用 `pcp agents >> AGENTS.md` 自行追加                                |
| `pcp validate`                                    | 结构 + 规划一致性校验，逐行输出（`ERROR`/`WARNING` + 节点 + 规则 + 原因）                                                                   |
| `pcp build`                                       | 先校验，再确定性重建 HTML 输出目录                                                                                                  |
| `pcp build --check`                               | 在临时目录重新生成并比对，检测输出是否过期（CI 用）                                                                                           |
| `pcp status`                                      | 终端概览：项目、当前焦点、决策计数、进度计数                                                                                                |
| `pcp context [node] [--full]`                     | 输出会话恢复 capsule（默认当前焦点）                                                                                                |
| `pcp focus [node]`                                | 查看或切换当前焦点（对 `project.yaml` 做行级编辑，保留注释）                                                                                |
| `pcp ideas [--status S] [--for NODE [--subtree]]` | 按状态分组列出想法层。`--for` 选出与某节点或其祖先相关的想法，`--subtree` 切换为该节点的子树方向。`--for` 不带 `--status` 时只列出 OPEN 与 PARKED。最后一行给出下一个可用的想法 id |
| `pcp graduate IDEA --to NODE [--note TEXT]`       | 毕业一个想法：向想法文件写入 `status: PROMOTED` 与 `outcome`，并把带 `ref` 的论据条目复制进节点的 `evidence_sources`（保留注释；节点须已存在；失败时两文件回滚）          |

全局参数 `-p/--project-root PATH` 指定目标仓库根目录（其余命令从该目录
向上查找 `.planning/`）。

退出码：`0` 成功 · `1` 业务失败（校验错误、未知节点、产物过期）·
`2` 用法/加载错误。

## AI Harness 集成

两份资产让 AI coding harness 知道何时该用 `pcp`：

1. **AGENTS.md 段落**：每个仓库执行一次 `pcp agents >> AGENTS.md`，写入
   两类内容：仓库自己的规则（文档命名、登记约定）与会话工作流。AGENTS.md
   是多数 harness 原生读取的开放标准（Codex、Cursor、Gemini CLI、
   ZCode……）；Claude Code 只读 `CLAUDE.md`，因此需要一个内容仅为
   `@AGENTS.md` 的 CLAUDE.md 作为桥接。
2. **Skill**：[`integrations/skills/pcp/SKILL.md`](integrations/skills/pcp/SKILL.md)
   是工具本身的手册。一份内容，多个安装位置：
   ```bash
   # 用户级，跨 harness 共享（ZCode 会扫描 ~/.agents/skills/）
   mkdir -p ~/.agents/skills/pcp
   curl -fsSL https://raw.githubusercontent.com/LuneHaven/planning-control-plane/main/integrations/skills/pcp/SKILL.md \
     -o ~/.agents/skills/pcp/SKILL.md
   ```
   Claude Code 不扫描 `~/.agents/`；在 `~/.claude/skills/pcp/` 给它装自己的
   副本。若要团队共享，则把 SKILL.md 提交到仓库的 `.agents/skills/pcp/`。

   Skill 随仓库分发，不随 Python 包分发：它是 harness 资产，不属于 PCP
   运行时；运行时适配器与插件仍不在范围内（见路线图）。

这样分工不会产生重复内容，两处也就不会互相矛盾：仓库规则只写在
`AGENTS.md`，命令手册只写在 `SKILL.md`。

## 想法层

规划节点是**决策之后**的控制系统：节点存在，是因为某件事已经被承诺。想法层
承载更早的阶段：已经捕获、但还没有资格进入计划的思考。

```
.planning/ideas/IDEA-0007.yaml     # 每个想法一个文件（直接放在 ideas/ 下，.yaml 后缀）
```

```yaml
id: IDEA-0007
title: Add a trend comparison view to the dashboard
status: OPEN                       # OPEN | PARKED | PROMOTED | DISCARDED
detail: One paragraph. Capture asks for no structure.
relates_to: [P2]                   # 这个想法关联的规划节点
benchmark_sources:                 # 成熟产品实际怎么做
  - ref: docs/benchmarks/grafana-panels.md
    note: Grafana 的对比面板说明需求是稳定的
  - note: Stripe 的月环比面板              # 仓库外：只写 note
methodology_sources:               # 为什么成立，与具体产品解耦
  - ref: docs/method/heuristics.md
outcome: ~                         # 想法毕业为节点时填写
created: 2026-08-27
last_updated: 2026-08-27
```

四条性质是刻意的：

- **捕获零门槛。** `benchmark_sources` / `methodology_sources` 全空是
  合法状态，不产生任何 WARNING。
- **唯一入口。** 想法进入规划图必须经过毕业：先建节点，再把想法的
  `outcome.node` 指向该节点，手工编辑或用
  `pcp graduate IDEA-0007 --to P2-A5`，后者还会把想法中带 `ref` 的论据
  条目复制进节点的 `evidence_sources`。
  节点永不反向引用想法，因此读计划不会牵扯到未完成的思考。
- **想法不会破坏计划。** 想法文件格式错误只会降级为一条校验 issue 并跳过该文件，
  `pcp status` / `pcp context` / `pcp build` 照常工作；想法层 ERROR 也不阻断构建。
- **capsule 永不含想法。** `pcp context` 只携带规划数据；
  `pcp ideas --for <node>` 是另一次显式的、有意的查询。

只有项目中存在想法时，生成站点才会多出 `ideas.html` 页与侧栏入口。

想法层有一条贯穿的规则：`id` 决定身份，文件名只是索引。由此得出两条规则：
文件名与 `id` 不一致时，`pcp validate` 报 `idea-filename-mismatch`
WARNING，不阻断，改名即可；`pcp ideas` 的最后一行给出下一个可用的
`IDEA-<NNNN>`，编号同时参考已加载的 id 与磁盘上的文件名，因此永远不会
指向一个已存在的文件。

## 规划模型

- **节点类型**（受控枚举）：`PROGRAM`、`PHASE`、`STRATEGY`、
  `DISCUSSION`、`DECISION`、`INVESTIGATION`、`IMPLEMENTATION`、`CLOSURE`。
- **节点状态**（规划生命周期，不是看板）：`NOT_STARTED`、`DISCUSSING`、
  `INVESTIGATING`、`DECIDED`、`WRITEBACK_PENDING`、`WRITEBACK_DONE`、
  `READY`、`IMPLEMENTING`、`BLOCKED`、`DONE`、`DEFERRED`。
- **三条独立轨道**：`discussion_status` / `writeback_status` /
  `implementation_status` ∈ `NOT_STARTED`、`IN_PROGRESS`、`DONE`、`N/A`。
  一个纯讨论节点可以是 Discussion `DONE` + Writeback `DONE` +
  Implementation `N/A`。
- **决策**：每个节点有四个清单
  - *Frozen（已冻结）*：已定；子节点继承，不应无意识推翻
  - *Open（未决）*：已识别、未定
  - *Blocking（阻塞）*：未解决且阻止收尾（`DONE` + blocking → 校验 ERROR）
  - *Deferred（已延期）*：明确推迟
- **范围边界**：每节点 `scope` / `out_of_scope` 清单；祖先声明的条目会
  继承下来一并显示，标明边界所在。

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

## Dashboard 与分层展开

![节点详情](docs/screenshots/node-zh.png)

- **侧栏**承载完整规划树，含状态、焦点标记与展开/折叠。
- **Dashboard** 只回答四个问题：现在在哪（当前焦点）、是否被阻塞（需处理
  项）、焦点周围是什么（焦点分支）、接下来可以开始什么（就绪队列）。
- **节点页**按控制面优先级排列：sticky header（节点 ID、状态、三条轨道、
  复制上下文）→ 下一步行动 → 目标 → 范围边界 → 决策（阻塞 → 未决 →
  已冻结，继承分组按祖先折叠）→ 关联 → 来源 → 恢复这项工作。
- 会掩盖要点的细节默认折叠（继承的已冻结决策、已延期决策、完整
  capsule），条数始终可见。

## 上下文恢复

**Context Capsule** 把规划图的当前状态交接给下一个工作会话：

```bash
pcp context            # 当前焦点的紧凑 capsule
pcp context P2-A4      # 任意节点
pcp context --full     # 追加祖先摘要、关联节点、已延期决策
```

把 capsule 粘贴到新的 AI 会话作为开场上下文。它只携带新会话需要的内容：
该节点的目标、继承的已冻结决策、范围边界、未决与阻塞决策、来源与三条
轨道的状态，除此之外不含任何其他内容。节点页的「恢复这项工作」面板
展示同一份 capsule，并带复制按钮。

![恢复这项工作](docs/screenshots/node-zh-resume.png)

## 推荐的 AI Agent 工作流

```
1. pcp build → 打开 dashboard，阅读当前焦点
2. pcp context → 把 capsule 粘贴到新的 agent 会话
3. 只讨论该分支；讨论结论作为决策写进节点 YAML
4. 属于规格的结论回写到规范文档，节点里只保留链接
5. 更新 status / 三条轨道 / next_action / last_updated
6. pcp validate → 修复全部 ERROR
7. pcp build（CI：pcp build --check）
8. pcp focus <下一个节点> → 循环
```

循环的每一步产物都落盘，因此可在任意位置中断，之后随时恢复。

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
- **语言不碰数据**：标识符与原始值（节点 ID、决策 ID、存储的枚举值）、
  你撰写的文本（标题、摘要、`pcp context` capsule）在任何语言下都保持
  原值。详细状态视图同时显示「本地化文案 + 原始枚举」（如
  `未开始 NOT_STARTED`），机器可读的值始终可搜索。

> 语言切换改的只是 PCP 的界面文案；
> 项目自身的规划内容保持作者原文，不会被自动翻译。

正因为存在这条边界，本仓库提供两份示例项目而不是一份：
[`examples/demo-project`](examples/demo-project) 存放英文规划数据，
[`examples/demo-project-zh`](examples/demo-project-zh) 存放中文规划数据。
本文档的中文截图来自中文示例项目，而不是把英文示例切到中文界面得到的。

## 架构

| 层          | 位置                                                      | 归属           |
| ---------- | ------------------------------------------------------- | ------------ |
| PCP engine | `src/planning_control_plane/`（本仓库）                      | 独立的 pip 安装工具 |
| 规划数据       | `<你的仓库>/.planning/{project.yaml, roadmap.yaml, nodes/}` | 你的仓库         |
| 生成的 HTML   | `<你的仓库>/.planning/dist/`                                | 你的仓库（可随时重建）  |

模块：`model.py`（枚举与数据模型）· `loader.py`（容错 YAML 加载）·
`graph.py`（树/图操作）· `validator.py`（校验规则）· `context.py`
（capsule）· `i18n.py`（界面翻译表，单一来源、逐页内嵌）·
`generator.py` + `templates/`（确定性 HTML 生成）· `cli.py`。

## 权威边界（Authority Boundary）

PCP 的权威仅限**规划结构与规划进度**。产品、治理、架构与实现的
规范语义仍归你项目自己的文档所有；PCP 只链接它们
（`canonical_sources` / `evidence_sources`），不复制、不判定其内容。每张
生成页面都在页脚声明这一点。

## 当前状态

**当前版本：V0.1.3**（已发布到
[PyPI](https://pypi.org/project/planning-control-plane/)），已达到可用 MVP
阶段，并在真实项目中完成自用验证：引擎、CLI、校验器、capsule 与双语界面
均已可用，自动化测试共 409 项。

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
