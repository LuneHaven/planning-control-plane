# PCP Harness 集成层草案（AGENTS.md 建议书 + Skill 封装 + 想法文件名卫生）

| 状态 | **草案（Draft，待评审）**——未合并主 spec，实现未开始 |
| --- | --- |
| 版本 | V0.1 草案（R1 初稿） |
| 依赖 | 对齐主 spec：§4（CLI 协议与退出码）、§16/§17（校验协议与引用校验）、§37（数据为源，HTML 为投影）；对齐想法层草案：IDEA-D6（文件名 `<id>.yaml`）、IDEA-D14（id 字符集）、IDEA-D50（想法层命令面） |
| 关联 V0.2 候选 | 文档登记制（PLAN 世界，本草案明确不做，见 §1）；`pcp close` 集成、`CANCELLED` 终态（同候 PLAN 世界，见想法层草案 §62.3） |
| 修订 | R1：初稿。背景与方向裁定见本文 §1；需求 ID 按新增顺序编号（`INT-D#`），合并主 spec 时统一重排 |

## 1 目标与非目标

**问题**：PCP 已实现（核心 V0.1.x + 想法层阶段 1–3），但作为跨 session AI Coding 工具存在两个采用缺口：

1. **知晓缺口**——harness（Claude Code、Codex 等）装了 PCP 却"想不起调用"：这是知晓/触发问题，不是调用问题（PCP 是 CLI，任何 harness 都能 shell 调用，缺的是让模型在正确时机想起它）。
2. **命名漂移缺口**——跨 session 生成的文件命名不一致：外部文档（specs / plans）各有各的命名，即使遵从性好的 harness 也只保证同 session 一致；想法文件同样有内部缺口（IDEA-D6 规定了文件名 `<id>.yaml`，validator 却没有任何规则守门）。

**交付三个小任务**：

- **任务 A**：`pcp agents` —— AGENTS.md 建议书（只读命令，打印可粘贴的集成段落）；
- **任务 B**：Skill 封装 —— `integrations/skills/pcp/SKILL.md`（harness 触发层资产）；
- **任务 C**：想法文件名卫生 —— `idea-filename-mismatch` WARNING + `pcp ideas` 尾行 next-free-id 提示。

**非目标（方向裁定，R1 记录）**：

| 不做 | 依据 |
| --- | --- |
| 外部文件（specs/plans 等）命名校验 | PCP 不 lint 它不拥有的文件：跨工具命名没有统一答案，任何规则都武断。结构性答案是**身份放注册表**（id 在 YAML 里，如想法层已做），文件名只是人类 UX；登记之后文件名漂移无害 |
| MCP server | MCP 解决"能不能调"，本草案的痛点是"想不想得起调"。PCP 已是文件即源的 CLI，MCP 只是再包一层 exec；候出现非 CLI 环境（web agent）需求再做薄封装 |
| 文档登记制 / 「想法 ＞ specs ＞ plans」funnel 进度把控 | PLAN 世界 V0.2 正题（登记制，非命名规范）；当前弱版本 = 外部 spec/plan 路径写进想法的论据 `ref`（本草案把它作为 AGENTS.md 段落里的一条约定发出） |
| CLAUDE.md 双写 | AGENTS.md 正在成为跨 harness 事实标准；CLAUDE.md 由用户自行引用/symlink，PCP 不维护两份 |
| 节点文件名守门 | 想法层才是高频 AI 生成面；节点由作者模板化创建。范围纪律，不加 `node-filename-mismatch` |

---

## 2 任务 A：AGENTS.md 建议书（`pcp agents`）

**INT-D1** `pcp agents` 是**只读**子命令：向 stdout 打印一段带标记区间的英文建议段落，不写任何文件。写入面维持 `init` / `focus` / `graduate` 三条不变——AGENTS.md 是用户拥有的仓库级文件，不在 `.planning/` 数据面内；PCP 是建议书角色，不是执法者（打印 + 用户自贴 = 一次粘贴，全 session 生效）。

**INT-D2** 段落首尾带标记 `<!-- pcp:agents begin -->` / `<!-- pcp:agents end -->`：用户粘贴后可整段替换式自管理更新（未来 PCP 升级段落内容，用户重跑命令覆盖区间即可）。

**INT-D3** 段落内容（英文固定，建议书口吻，均可被用户修改）：

1. 本仓库由 PCP 管理（存在 `.planning/`），数据是源、`dist/` 是投影（勿手改）；
2. session 工作流：开始/恢复工作先 `pcp context`；总览用 `pcp status` / `pcp ideas`；
3. 想法捕获：新建 `.planning/ideas/IDEA-<NNNN>.yaml`（给出最小骨架：id/title/status: OPEN/detail/benchmark_sources/methodology_sources/created/last_updated），下一个可用 id 看 `pcp ideas` 尾行；
4. 毕业：`pcp graduate <idea-id> --to NODE [--note TEXT]`（节点须已存在于 `.planning/nodes/`，命令做两文件原子写 + 论据转录）；
5. 收尾：`pcp validate` 清掉 ERROR（WARNING 不阻断）；
6. 外部文档（specs / plans / 研究笔记）命名**建议**：`YYYY-MM-DD-<slug>.md`（日期前缀，与 superpowers 计划文件同风格；用户可改）；
7. 登记约定（弱版本）：落地的 spec / plan 路径写进对应想法的 `benchmark_sources` / `methodology_sources` 的 `ref`——这样 `pcp ideas` 视图能看到"想法有没有 spec、有没有 plan"，无需 PCP 校验任何外部文件。

**INT-D4** v1 段落为**静态模板**：不插值项目 id / 路径（`.planning/` 本身是常量约定）。若未来需要项目感知（如自定义目录）再修订。

**INT-D5** 退出码：成功 0；无业务失败路径（用法错误由 argparse 报 2）。输出英文纯文本、无颜色（CLI 既有惯例）。

---

## 3 任务 B：Skill 封装

**INT-D6** 家在 `integrations/skills/pcp/SKILL.md`（随仓库分发）：它是给 harness 的资产，不是 PCP 运行时的一部分——不进 `src/`、不进包。安装 = 复制或链接到目标 harness 的 skills 目录（README 双语说明）。

**INT-D7** 与 AGENTS.md 段落的内容分工（单一事实源原则）：

- **SKILL.md = 怎么用 PCP**：七个命令的手册（用法、退出码、写命令的原子性语义）、session 工作流、以及"尊重本仓库 AGENTS.md 里的规矩"；
- **AGENTS.md 段落 = 这个仓库的规矩**（命名规范、登记约定）。

仓库级规矩只存在于 AGENTS.md 段落一处，SKILL.md 引用而不复制——避免两处漂移。

**INT-D8** SKILL.md 的 `description` 覆盖触发场景（渐进披露：只有描述常驻上下文，正文按需加载）：仓库含 `.planning/`（PCP 管理的仓库）、开始/恢复工作（`pcp context`）、捕获或毕业想法、结束前校验（`pcp validate`）、规划文档命名。措辞在实现时打磨，验收以覆盖上述场景为准。

**INT-D9** 语言：英文（harness 资产的事实标准），不进 i18n 体系——i18n 服务于 build 投影层，CLI 与 harness 资产沿用英文惯例。

---

## 4 任务 C：想法文件名卫生（补 IDEA-D6 的门）

**INT-D10** 背景：IDEA-D6 规定一文件一想法、文件名 `<id>.yaml`，但 validator 现无任何 filename 规则——`trend-view.yaml` 内写 `id: IDEA-0007` 可干净加载、干净通过校验。这是跨 session 命名漂移在 PCP 内部数据面上的缺口。

**INT-D11** 新校验规则 `idea-filename-mismatch`（Severity **WARNING**）：想法文件名 stem ≠ `id` 时报，消息建议重命名为 `<id>.yaml`。定位镜像 `idea-id-collides-with-node`（提示不阻断）：id 是身份权威（D14），文件名只是索引便利（D6）；不 ERROR、不影响 validate 退出码与 build 门禁（§16 协议：仅 ERROR 影响）。仅对成功加载的想法生效；消息硬编码英文（validator 既有惯例，不走 i18n）。

**INT-D12** `pcp ideas` 成功读取想法目录的输出路径，末尾追加一行 `next free id: IDEA-<NNNN>`：取现有 id 中 `IDEA-(\d+)` 模式的最大编号 +1（零匹配 → `IDEA-0001`）。纯建议行，给跨 session 的下一个创建动作现成抓手。**本任务显式豁免"既有测试零修改"**：允许为该新增行为最小更新既有输出断言（新增输出行，不改既有语义）。

**INT-D13** 影响面：`cli.py`（`pcp agents` 命令 + `pcp ideas` 尾行 + parser 接线）、`validator.py`（新规则——本任务的正当引擎触点）、`integrations/skills/pcp/SKILL.md`（新资产）、`README.md` / `README.zh-CN.md`（三件事各一段）、新增测试文件。其余引擎零改动（`model.py` / `loader.py` / `generator.py` / `i18n.py` / `templates/` / `context.py` / `graph.py`）。

---

## 5 验收

1. `pcp agents`：输出含标记区间与 INT-D3 全部要点；运行前后 `git status` 无变化（只读证明）；不写任何文件（含 AGENTS.md 本身）；
2. Skill：`integrations/skills/pcp/SKILL.md` 存在，description 覆盖 INT-D8 场景，正文命令清单与 `pcp --help` 一致；
3. validate：文件名与 id 错配 → `idea-filename-mismatch` WARNING 且退出码 0；配对 → 无该 WARNING；
4. `pcp ideas`：空想法目录 → 尾行 `next free id: IDEA-0001`；有 `IDEA-0007` → `IDEA-0008`；加载失败路径不显示该行；
5. 全量测试绿（新增测试 + 按 INT-D12 豁免最小更新的既有断言）；
6. 两份 README 各覆盖三件事（`pcp agents` 表格行、Skill 安装说明、文件名 WARNING 与 next-id 提示）。

---

## 附录 D 修订记录

### D.1 修订记录 R1（初稿）

| # | 改动 | 依据 |
| --- | --- | --- |
| 1 | 初稿：任务 A（`pcp agents` 只读建议书）、任务 B（`integrations/skills/pcp/SKILL.md`）、任务 C（`idea-filename-mismatch` WARNING + next-free-id 尾行） | 跨 session 采用缺口的两轮方向裁定（2026-08-28）：知晓问题用指令层（AGENTS.md/Skill）解决而非 MCP；外部文件命名不校验（身份在注册表），登记制候 PLAN 世界；内部缺口（IDEA-D6 无守门）用 WARNING 补门 |
| 2 | 写入面不变裁定：`pcp agents` 只打印不写文件 | AGENTS.md 是用户拥有的仓库级文件、不在 `.planning/` 数据面内；打印 + 自贴已满足"一次粘贴、全 session 生效"，代价为零写入面 |
| 3 | 允许为 `pcp ideas` 新增尾行最小更新既有测试断言 | 该行是新增输出而非语义变更；沿用"既有测试零修改"会逼出规避式实现（如藏 stderr），得不偿失 |
