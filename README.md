# Planning Control Plane (PCP)

PCP 是一个随目标仓库存放的规划上下文与进度控制工具（CLI 名 `pcp`）：把跨周、跨会话的大型规划从线性聊天记录重构为持久化的 Planning Graph，并能为图中任意节点生成可直接粘贴到新会话的 Context Capsule（会话恢复用上下文摘要）。PCP 以 pip 安装为独立工具，可被多个项目复用，不依赖任何具体业务项目、目录约定或外部服务。

## What PCP Solves

结论：大型规划长期放在线性 Chat/Session 里会持续丢失上下文。会话越长，早期确立的父级约束、已冻结决策与原始目标越容易被后续讨论遗漏，最终表现为 decision drift（决策漂移：后续讨论无意识推翻既有决策）与 scope drift（范围漂移：讨论范围无意识扩大）。

PCP 针对的具体问题与对应机制：

| 问题 | 含义 | PCP 的机制 |
| --- | --- | --- |
| long-running planning | 规划周期以周/月计，远超单个会话寿命 | 规划数据持久化在 `.planning/`，随目标仓库提交 |
| branch discussions | 讨论应限定在规划树的某个 branch（规划树分支，非 git branch）内 | Current Focus 唯一指向当前节点；Context Capsule 只包含该 branch 的上下文 |
| context loss | 新会话不知道父级约束与已定决策 | `pcp context` 自动收集并展示祖先继承的 frozen decisions、scope 与 canonical sources |
| cross-session recovery | 换会话、换人、换工具后难以继续 | 一条命令输出 Session Resume Capsule，粘贴即可恢复工作上下文 |
| decision drift | 已定决策被无意识推翻 | frozen decisions 沿层级继承展示；DONE 节点仍带 blocking decision 时校验直接报 ERROR |
| scope drift | 讨论范围悄悄扩大 | 每个节点显式声明 In Scope / Out of Scope，详情页与 capsule 必须展示 |

PCP 不是普通 task tracker，不是 Jira/Notion 的替代品。它不管理任务分派、多人协作、通知或日历；它管理的是规划过程本身的结构（topology）、进度（progress）与上下文（context）。进度统计只反映 Planning Node 的推进情况，不代表产品或工程完成度。

## Mental Model

PCP 的使用是一个循环，每轮推进一个节点：

```
Planning Graph（持久化在 .planning/）
  → Select Node    pcp focus <node-id>，把 Current Focus 移到目标节点
  → Discuss        pcp context 输出 Context Capsule，粘贴到新会话；只讨论该节点所在 branch
  → Close          讨论结束形成结论，分类记入 frozen / open / blocking / deferred decisions
  → Writeback      属于规格的结论回写到仓库内的 canonical 文档，节点里只保留链接
  → Update Node    更新节点 YAML：决策、scope、三个 track 状态、next_action、last_updated
  → Continue       pcp validate + pcp build 后，focus 移到下一节点，回到 Select Node
```

每一步的产物都落盘在 `.planning/`，因此循环可在任意位置中断，之后随时恢复。

## 架构：三层严格分离

| 层 | 位置 | 归属 | 说明 |
| --- | --- | --- | --- |
| PCP engine | 本仓库 `src/planning_control_plane/` | 独立工具（pip 安装） | 不含任何业务项目假设；多个项目复用同一套 engine |
| Project planning data | 目标仓库 `.planning/{project.yaml, roadmap.yaml, nodes/}` | 目标仓库 | 规划的唯一数据源，随目标仓库提交与评审 |
| Generated HTML | 目标仓库 `.planning/dist/` | 目标仓库（生成物） | `pcp build` 的确定性输出，可随时删除重建；`pcp init` 生成的 `.planning/.gitignore` 默认忽略它 |

节点定义可写在 `roadmap.yaml`，也可写成 `nodes/*.yaml`（一节点一文件），加载时合并。

核心设计原则：

1. **Planning data is source. HTML is projection.** 规划数据是源，HTML 只是投影；修改永远改 YAML，不改生成文件。
2. **Project data belongs to target repository. PCP engine belongs to standalone tool.** 数据归目标仓库，工具独立安装。
3. **Parent decisions remain visible in child work.** 父级决策在子节点工作中始终可见。
4. **Discussion state ≠ writeback state ≠ implementation state.** 三个 track 独立存储，互不推导。
5. **Current Focus must always be recoverable.** 当前焦点任何时候都能快速恢复。
6. **Generated output must be disposable and reproducible.** 生成物可丢弃、可复现：删除 `dist/` 后一条命令完全重建。
7. **PCP must never become product/governance SSOT.** PCP 永不成为产品或治理的单一事实来源（SSOT，single source of truth）。

## Install

要求 Python 3.11+；运行时依赖仅 PyYAML 与 Jinja2，安装时自动解析。

```bash
pip install -e .
pcp --help              # 查看命令列表
pcp <command> --help    # 每个子命令的详细帮助
```

运行测试需要可选 dev 依赖（pytest）：`pip install -e ".[dev]"`。

## Quick Start

在任意仓库的根目录：

```bash
cd my-project
pcp init          # 生成 .planning/{project.yaml, roadmap.yaml, nodes/, .gitignore}，不覆盖已有文件
pcp validate      # 结构与一致性校验，逐条输出 Node ID / Rule / Reason
pcp build         # 校验通过后生成 .planning/dist/ 离线静态 HTML
pcp status        # 终端概览：Current Focus、阻塞决策计数、进度计数
pcp context       # 当前 focus 的 Context Capsule，可直接粘贴到新会话
```

初始化后在 `nodes/` 下添加节点 YAML（字段见下文「核心概念」），用 `pcp focus <node-id>` 设定当前焦点，再进入上述循环。

也可以直接使用本仓库自带的演示目标仓库：

```bash
cd examples/demo-project
pcp status           # Current Focus 为 P2-A4，含 blocking decision BD-401
pcp context --full   # 完整 capsule：含祖先摘要、依赖明细
pcp validate
pcp build            # 打开 .planning/dist/index.html，可直接双击离线浏览
```

`examples/demo-project` 是合成仓库，规划树为 `P1 → P2 → P2-A → P2-A1..A4`，覆盖多级 frozen decision 继承、blocking decision、dependency、canonical/evidence 链接与 Current Focus；不含任何真实业务数据。

## Recommended Workflow

1. 打开 dashboard：`pcp build` 后用浏览器打开 `.planning/dist/index.html`。
2. 定位 Current Focus：dashboard 顶部最醒目区域，或 `pcp status`。
3. 阅读继承决策：节点详情页的 Inherited Frozen Decisions，或 `pcp context` 的对应小节。
4. 复制恢复上下文：详情页 Copy Context 按钮，或 `pcp context` 的终端输出。
5. 开始新的 chat/agent session：把 capsule 作为开场上下文粘贴进去。
6. 只讨论该 branch：不展开其他节点的问题；不属于本节点的内容记为 open decision 或另立节点。
7. 记录持久结论：讨论中形成的结论写入节点 YAML（决策、scope、next_action）。
8. 完成适用的 Writeback（回写）：属于规格的结论回写 canonical 文档，节点中只保留链接。
9. 更新 planning node：status、三个 track 状态、`last_updated`。
10. 校验：`pcp validate`，修复全部 ERROR。
11. 重新生成：`pcp build`；CI 中可用 `pcp build --check` 验证生成物无 drift（生成物与当前数据不一致）。
12. 移动 focus：`pcp focus <next-node-id>`，进入下一轮循环。

## 核心概念

### Planning Node / Planning Graph

规划的基本单位是 Planning Node：一个 YAML 文件，包含 objective、scope、决策、状态与文档链接。节点之间通过 `parent`、`depends_on`、`blocks`、`related_to`、`supersedes` 构成 Planning Graph。UI 主视图按树展示 parent 层级，底层校验按 graph 处理（cycle 检测覆盖 parent 边与 dependency 边）。

### Node Type 与 Status：受控枚举

`type` 取值：`PROGRAM` / `PHASE` / `STRATEGY` / `DISCUSSION` / `DECISION` / `INVESTIGATION` / `IMPLEMENTATION` / `CLOSURE`。
`status` 取值：`NOT_STARTED` / `DISCUSSING` / `INVESTIGATING` / `DECIDED` / `WRITEBACK_PENDING` / `WRITEBACK_DONE` / `READY` / `IMPLEMENTING` / `BLOCKED` / `DONE` / `DEFERRED`。
枚举之外的值被 validator 拒绝（`invalid-type` / `invalid-status`，ERROR）。不使用 todo/doing/done 三态，因为 PCP 表达的是规划生命周期，不是执行看板。

### 三个独立 track 状态

`discussion_status` / `writeback_status` / `implementation_status` 分别存储，取值 `NOT_STARTED` / `IN_PROGRESS` / `DONE` / `N/A`。讨论完成不推导出回写完成或实现完成；三个状态只由人工更新。例如一个纯讨论节点可以是 Discussion DONE + Writeback DONE + Implementation N/A。

### Decision 四类：Frozen / Open / Blocking / Deferred

- Frozen Decision：已冻结的决策，子节点默认继承，不应无意识推翻；每条含 `id`、`summary`、可选 `source`。
- Open Decision：已识别但未定的决策。
- Blocking Decision：阻止节点收尾的决策；节点 `status = DONE` 且 `blocking_decisions` 非空 → ERROR。
- Deferred Decision：明确推迟的决策（默认 capsule 不展开，`--full` 才显示）。

PCP 只负责保存、继承、展示决策，不判断决策是否正确。

### Scope Guard

每个节点显式声明 `scope`（In Scope）与 `out_of_scope`（Out of Scope），详情页与 `pcp context` 必须展示；祖先的 scope 与 out_of_scope 条目也作为 guardrails 继承展示（当前节点已声明的条目不再重复）。用途是在长讨论中持续提示边界，防止范围无意识扩大。

### Current Focus

`project.yaml` 中的 `planning.current_focus`，指向当前正在推进的唯一节点。`pcp focus` 查看或切换（切换前校验节点存在，并显示 Previous/New focus）。focus 指向不存在的节点 → ERROR；指向 DONE 节点 → WARNING。

### Context Capsule 与 progressive disclosure

`pcp context [node_id]` 输出 Session Resume Capsule：项目、节点、Parent Path、objective、继承与自身的 frozen decisions、In/Out of Scope、open/blocking decisions、canonical/evidence sources、三个 track 状态、next_action。默认输出 compact 模式，规模适合直接粘贴给新会话；`--full` 才追加 ancestor summaries、related nodes、dependency details、deferred decisions（progressive disclosure，按需分层展开）。

### Canonical Source 与 Evidence Source

`canonical_sources` 指向仓库内对该主题具有规范效力（normative）的文档；`evidence_sources` 指向佐证与背景材料。两类分开存储、分开校验，不混为一类。路径必须是 repository-relative（仓库相对路径）；PCP 只检查文件存在性，不读取或判定其内容。

### Generated UI：布局与 locale

`pcp build` 生成的 HTML 是规划数据的投影，分工固定：左侧 sidebar 承载完整 Planning Tree（全局拓扑），Dashboard 主区只回答「现在在哪 / 有没有阻塞 / 下一步做什么 / 怎么恢复」，因此主区不再重复渲染整棵树。节点详情页按控制面优先级排列：sticky header（Node ID、标题、状态、focus 标记、更新日期、三轨状态、Copy Context）→ Next Action → Objective → Scope Guard → 决策（Blocking → Open → Frozen）→ 关联与来源 → Resume This Work。继承的 frozen decisions 按祖先分组折叠（最近的祖先默认展开，更上层默认折叠），分组标题始终显示祖先、条数与来源。

界面语言由 `project.yaml` 的 `ui.locale` 显式指定：

```yaml
ui:
  locale: zh-CN
```

- 默认值：`en`。不写 `ui` 段时行为与 V0.1 完全一致。
- 支持的取值：`en`、`zh-CN`。
- 取值不在支持列表时：回退到 `en` 并输出 WARNING（`unknown-ui-locale`），不阻断 build。
- locale 是显式配置，不从 project name、数据中的中文字符、操作系统 locale 或环境变量推断；相同规划数据 + 相同配置永远生成相同字节。

Localization 只作用于**人类可见的界面文案**（presentation-only）。以下内容在任何 locale 下都保持原值：Planning Node ID、Decision ID、YAML 中存储的枚举值、`pcp context` capsule、`pcp status` / `pcp validate` 等 CLI 的 machine-facing 输出。页面上状态的展示规则是：sidebar、表格、队列等紧凑位置只显示本地化文案；节点详情页头部与三轨状态显示「本地化文案 + 原始枚举」（例如 `未开始 NOT_STARTED`），因此原始枚举在页面上始终可见、可搜索。`en` 下本地化文案就是枚举本身，页面不会把同一个值印两遍。

生成页面不依赖任何 CDN、远程字体或网络请求；中文字体走离线 system font stack（PingFang SC / Microsoft YaHei / Noto Sans CJK SC 等），在 Windows / macOS / Linux 上均有可用回退。

## CLI 参考

| 命令 | 说明 |
| --- | --- |
| `pcp init` | 在目标仓库生成 `.planning/` 骨架；已有 `.planning/` 时拒绝执行（`--force` 只补建缺失文件，绝不覆盖任何已有文件） |
| `pcp validate` | 结构 + 规划一致性 + reference 校验，逐条输出问题 |
| `pcp build` | 先校验（ERROR 时拒绝生成），再确定性重建 HTML 输出目录 |
| `pcp status` | 终端概览：项目、Current Focus、决策计数、进度计数 |
| `pcp context [node_id]` | 输出某节点的 Context Capsule（默认当前 focus） |
| `pcp focus [node_id]` | 查看或切换 Current Focus（写回 `project.yaml`，只改 `planning:` 段内的 `current_focus` 行，保留注释、排版与换行符；写后回读校验，失败即回滚） |

参数：

| 参数 | 适用命令 | 说明 |
| --- | --- | --- |
| `-p` / `--project-root PATH` | 全局 | 目标仓库根目录；`init` 在该目录创建 `.planning/`，其余命令从该目录向上查找 `.planning/`（默认当前目录） |
| `--force` | `init` | `.planning/project.yaml` 已存在时仍补建缺失文件；绝不覆盖已存在文件 |
| `--check` | `build` | 不写盘，在临时目录重新生成并与输出目录比较；一致 exit 0，drift exit 1（用于 CI） |
| `--full` | `context` | 在 compact 输出上追加祖先摘要、related nodes、dependency details、deferred decisions |

exit code 约定：`0` 成功；`1` 业务失败（存在校验 ERROR、未知节点、生成物 drift）；`2` 用法或加载错误（参数错误、`.planning` 缺失或不可读）。`pcp validate` 只有 WARNING 时 exit 0。

## Validation 规则摘要

输出格式：每条问题一行，依次为 severity（`ERROR` / `WARNING`）、Node ID（项目级问题显示 `-`）、Rule、Reason，按 severity → node id → rule 排序。示例：

```
ERROR  P2-A4        done-with-blocking-decision: status is DONE but blocking_decisions is not empty (BD-401)
```

结构规则（ERROR，另注明者除外）：

- `duplicate-node-id`：节点 id 重复（保留第一处定义）。
- `missing-parent` / `self-parent` / `parent-cycle`：parent 指向缺失节点、指向自身、或形成环。
- `missing-dependency-target` / `missing-blocks-target` / `missing-related-target` / `missing-supersedes-target`：各边指向未知节点。
- `dependency-cycle`：`depends_on` 关系成环。
- `invalid-type` / `invalid-status` / `invalid-track-status`：枚举之外的值（含空串；`type: null` 视为缺省）。
- `invalid-current-focus`：`current_focus` 指向不存在的节点。
- `duplicate-decision-id`：同一节点内四个决策列表出现重复决策 id。
- `unsafe-output-directory`：`output.directory` 解析结果等于或包含 `.planning/`（含仓库根）——`pcp build` 重建输出目录会删除规划数据，直接拒绝。
- `ignored-node-file`（WARNING）：`nodes/` 下存在但不会被读取的 YAML 文件（如 `.yml` 后缀、子目录内），提示避免规划数据静默丢失。
- `unknown-field`（WARNING）：节点或 `project.yaml` 中存在 schema 之外的键。
- `unknown-ui-locale`（WARNING）：`ui.locale` 不在支持列表（`en` / `zh-CN`）内或不是非空字符串；回退到 `en`，不阻断 build。

另有两类加载期硬失败（`LoadError`，exit 2）：YAML 语法错误，以及同一映射内出现重复键（如两个 `nodes:` 段或两个 `current_focus:` 键）——后者是歧义文件，拒绝加载而不是静默取后值。

规划一致性规则：

- `status = DONE` 且 `blocking_decisions` 非空 → ERROR（`done-with-blocking-decision`）。
- `status = BLOCKED` 但既无 blocking decision 也无未解决 dependency → WARNING。
- `writeback_status = DONE` 但 `canonical_sources` 为空 → WARNING。
- `current_focus` 指向 DONE 节点 → WARNING；有节点但未设置 focus → WARNING。
- `depends_on` 指向 DEFERRED 节点 → WARNING。

Reference 规则：

- canonical source 文件不存在 → ERROR；evidence source 文件不存在 → WARNING。
- 路径为绝对路径或越出仓库根（非 repository-relative）→ ERROR。

`pcp build` 在存在任何 ERROR 时拒绝生成；WARNING 只打印不阻断。

## Authority Boundary

结论：PCP 只拥有规划本身，不拥有被规划的对象。

- PCP owns：planning topology（节点、边、层级）、planning progress（状态与进度计数）、planning context（决策继承、Context Capsule）。
- PCP does not own：product specification、architecture specification、engineering specification、implementation truth（实现的真实状态）、decision provenance（决策的原始出处）。PCP 只以 repository-relative 链接引用这些 artifacts，不复制、不判定其内容。

生成页面每页 footer 固定声明：

```
Planning Control Plane
This view is authoritative only for planning structure and planning progress.
Normative product, governance, architecture, and implementation semantics remain owned by the linked project artifacts.
```

## V0.1 Non-goals 与 Future Extension Points

V0.1 明确不做（不是未完成，而是范围外）：

- multi-user collaboration、server、cloud sync、database
- GitHub integration、PR integration
- Claude plugin、Codex plugin、ChatGPT plugin
- automatic AI summarization、automatic decision making
- semantic search、vector database
- Jira replacement、Notion replacement

预留的扩展方向（V0.1 只保留命名空间，不实现任何接口，也不为它们提前抽象）：

`pcp prompt`、`pcp close`、`pcp reopen`、Git Adapter、GitHub Adapter、Claude Code Adapter、Codex Adapter、ChatGPT Adapter、Multi-project Workspace。

## Upgrade Note：V0.1 → V0.1.1

V0.1.1 只改 UI 层：生成模板、样式与前端脚本重写，新增 `ui.locale` 配置项。Planning Node schema、决策继承规则、Context Capsule 语义、状态生命周期、authority boundary 均未改动，规划数据无需迁移。

升级后请先执行一次 `pcp build` 再使用 `pcp build --check`：模板变了，旧的 `dist/` 与新引擎生成的结果必然不一致，`--check` 会报 drift。这不是 planning data migration，只是重新生成投影。

```bash
pip install -e .
pcp build          # 重新生成 dist/
pcp build --check  # 现在应当 exit 0
```

需要中文界面时，在 `.planning/project.yaml` 追加：

```yaml
ui:
  locale: zh-CN
```

## Development

```bash
pip install -e ".[dev]"   # 安装 pytest
python -m pytest
```

模块职责分离：`model.py`（数据模型与枚举）、`loader.py`（YAML 加载）、`graph.py`（图操作）、`validator.py`（校验规则）、`context.py`（Context Capsule）、`i18n.py`（生成 UI 的文案表，presentation-only）、`generator.py` 与 `templates/`（HTML 生成）、`cli.py`（CLI 入口）。

## License

MIT，见 [LICENSE](LICENSE)。
