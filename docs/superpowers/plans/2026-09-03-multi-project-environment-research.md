# 多项目共用环境调研：PCP 与 codegraph 的对照

日期：2026-09-03
性质：一次性研究笔记，IDEA-0006 的支撑材料

## 问题

这份笔记记录一次调研。PCP 目前只支持单个项目，观察到 codegraph
（colbymchenry/codegraph）支持多个项目共用一个环境，要不要跟进升级？
调研分两路：一路读 PCP 源码，确认单项目假设落在哪里；一路读 codegraph
仓库，拆解它的多项目模型。

## PCP 的单项目模型落在哪里

单项目假设不是实现疏忽，它落在四个结构性位置：

1. 项目根解析：`-p/--project-root` 默认取当前目录（cli.py:1066-1073），
   `find_planning_dir` 从起点向上找第一个 `.planning`
   （loader.py:151-164，注释明说模仿 git 找 `.git`）。一次调用恰好
   解析出一个项目。
2. 引用校验：节点与想法的来源引用必须是仓库相对路径，绝对路径或
   `..` 越界直接判 ERROR（validator.py:379-409 的
   `reference-escapes-repo`，validator.py:277-295 的
   `idea-source-escapes-repo`）。model.py:213-223 写明设计意图：
   `note:` 自由文本是仓库外世界的唯一通道。`output.directory` 是唯一
   允许指向根之外的路径，且只出不进。
3. 构建投影：`build_site` 清空一个 dist 目录后生成一个站点，节点引用
   只在单项目内解析（generator.py:743-806，_node_ref 见
   generator.py:224）。
4. 无进程层、无全局配置：源码里没有 server / daemon / watch 概念，
   不读环境变量，没有用户级配置目录；i18n.py:15-17 甚至拒绝从系统
   环境推断 locale，来保证构建字节确定。

已有的多项目能力只有一项：`-p` 让一份安装操作任意多个项目，项目之间
完全隔离。examples/ 下两个 demo 各自持有独立的 `.planning`，互不可见。
README 已把「multi-project workspace」列为预留扩展点（README.md:447、
456，V0.2 候选，未承诺），并把 server / 云同步 / 多用户明确排除在
范围外（README.md:439-441）。

## codegraph 的多项目模型

codegraph 是一个 CLI 加 MCP server 的组合，TypeScript 应用配 Rust
内核，按项目在 `.codegraph/` 目录里存放 SQLite 索引、daemon 进程文件
与缓存。它的多项目支持由四条机制组成：

1. 状态按项目隔离在磁盘上：每个项目一份 `.codegraph/`，没有用户级
   项目注册表；`~/.codegraph/` 只放运维元数据（daemon 发现记录、更新
   与遥测缓存），源码注释明说它永远不是 source of truth。
2. 发现自底向上：查询时从起点向上找最近的 `.codegraph/`
   （src/directory.ts 的 findNearestCodeGraphRoot）；monorepo 场景
   向下扫子目录找子项目索引（findIndexedSubprojectRoots，限深 4、
   上限 64）；恰好命中一个子项目才收养为默认项目，零个或多个就没有
   默认。
3. 共用发生在进程层：每个项目根跑一个常驻 daemon，持有一个引擎
   （一份索引、一个文件 watcher、一个 SQLite WAL），N 个客户端通过
   socket 共享它；会话内每次调用还可以传 `projectPath`，无状态打开
   第二项目，按解析后的根路径缓存实例。server 根目录没有索引是受
   支持的状态，此时工具仍然可用，`projectPath` 变为必填。
4. 数据从不跨项目合并：跨项目查询就是进程层路由到另一份索引；
   反过来一个索引可以横跨多个 git 仓库（把装着多个仓库的文件夹
   索引成一个项目）。

这套模型的代价也有公开记录：用 `projectPath` 打开的第二项目没有
live watcher，数据过期只标记不修复；两个环境共享同一棵工作树时要用
`CODEGRAPH_DIR` 改目录名隔离（WSL 与 Windows 的 SQLite 锁不可靠，
issue #636）；文件锁事实上排除了多进程并发写。

## 对照结论

两个工具在数据层的设计一致：状态按项目留在磁盘上，发现自底向上，
没有全局注册表。差异在 codegraph 多一个常驻 daemon 层，多项目支持
就由那一层承担。codegraph 的「共用环境」共用的是 daemon 进程
（watcher、数据库连接、查询池），数据模型仍然是严格单项目的。

PCP 是一次性 CLI：读 YAML、渲染 HTML、退出。每次调用天然是独立
环境，`-p` 已让一份安装服务任意多个项目。没有常驻进程，就没有需要
共用的对象。「PCP 不支持多项目共用环境」这个观察成立，但在 CLI
形态下不构成损失。

## 候选痛点逐项检验

1. 多仓库总览：想在一张页面看到所有项目的进度。这是投影层缺口，
   不是数据层缺口。解法是聚合构建：读 N 个项目的 `.planning`，生成
   一份组合 Dashboard（仪表盘），只读不写回，不动任何校验规则。
2. monorepo 子项目：子目录各持 `.planning`。从子项目自己的目录运行
   pcp 即可操作对应项目，互不干扰；缺的只是跨子项目的聚合视图，
   同上一条。
3. 跨仓库结构化依赖：仓库 A 的节点被仓库 B 的节点阻塞。现有合法
   通道是 `note:` 自由文本；没有真实案例之前，不为它设计结构化引用。
4. 单会话多项目：一个 AI 会话同时管多个项目的规划。这是 codegraph
   场景的直接对应物，前提是存在会话层（MCP server）。PCP 尚无
   会话层，harness 集成规范草案已把 MCP server 推迟到非 CLI 环境
   需要时（docs/superpowers/specs/harness-integration-spec-draft.zh-CN.md）。
   CLI 形态下 AI 会话逐项目运行 pcp，没有阻碍。

## 决策建议

现在不升级，理由三点：

1. 共用的对象不存在：多项目共用环境解决的是常驻资源共享问题，
   PCP 没有常驻进程。
2. 数据模型级合并的代价与卖点冲突：一张规划图跨仓库，会正面冲撞
   ERROR 级的 repo-relative 校验和「规划数据随仓库走、进 PR 审查」
   的核心主张；要动 loader、model、validator、generator 四个核心
   模块，收益却建立在未验证的需求上。
3. README 的排序是对的：「multi-project workspace」列为 V0.2 未承诺
   候选，排在 harness 集成之后；先有会话层，再谈多项目会话。

重启条件：仓库出现会话层（harness / MCP 集成）。届时照 codegraph
模式映射到 PCP：每次调用可传项目路径、自底向上发现沿用
`find_planning_dir`、不引入全局注册表、状态继续按项目留在
`.planning/`。

如果多仓库总览的需求先出现，可以独立做聚合投影，规模远小于会话层
改造。

## 参考

- codegraph 仓库：https://github.com/colbymchenry/codegraph
  （机制结论来自 src/directory.ts、src/mcp/tools.ts、src/mcp/engine.ts、
  src/mcp/server-instructions.ts 与 README、issue #636、#411、#964）
- PCP 源码引用见上文行号
