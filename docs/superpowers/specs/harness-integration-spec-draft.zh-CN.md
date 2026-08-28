# PCP Harness 集成层草案（AGENTS.md 建议书 + Skill 封装 + 想法文件名卫生）

| 状态 | **草案（Draft，待评审）**——未合并主 spec，实现未开始 |
| --- | --- |
| 版本 | V0.1 草案（R2，评审后修订） |
| 依赖 | 对齐主 spec：§4（CLI 协议与退出码）、§16/§17（校验协议与引用校验）、§37（数据为源，HTML 为投影）；对齐想法层草案：IDEA-D6（文件名 `<id>.yaml`）、IDEA-D14（id 字符集）、IDEA-D50（想法层命令面） |
| 关联 V0.2 候选 | 文档登记制（PLAN 世界，本草案明确不做，见 §1）；`pcp close` 集成、`CANCELLED` 终态（同候 PLAN 世界，见想法层草案 §62.3）；`pcp agents --skill`（skill 正文分发，见 INT-D16） |
| 修订 | R1：初稿。R2：审查修订——事实订正 3 处、next-free-id 计算口径改写（数据安全）、新增 INT-D14–D18。背景与方向裁定见本文 §1；需求 ID 按新增顺序编号（`INT-D#`），合并主 spec 时统一重排 |

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
| 外部文件（specs/plans 等）命名校验 | PCP 不 lint 它不拥有的文件：跨工具命名没有统一答案，任何规则都武断。结构性答案是**身份放注册表**（id 在 YAML 里，如想法层已做），文件名只是人类 UX；登记之后文件名漂移无害。**不校验 ≠ 不建议**：INT-D3 仍给出命名建议，因为一致命名对人类读者有价值、且代价为零（建议可被用户改写） |
| MCP server | MCP 解决"能不能调"，本草案的痛点是"想不想得起调"。PCP 已是文件即源的 CLI，MCP 只是再包一层 exec；候出现非 CLI 环境（web agent）需求再做薄封装 |
| 文档登记制 / 「想法 ＞ specs ＞ plans」funnel 进度把控 | PLAN 世界 V0.2 正题（登记制，非命名规范）；当前弱版本 = 外部 spec/plan 路径写进想法的论据 `ref`（本草案把它作为 AGENTS.md 段落里的一条约定发出） |
| CLAUDE.md 双写 | AGENTS.md 正在成为跨 harness 事实标准；CLAUDE.md 由用户自行引用/symlink，PCP 不维护两份 |
| 节点文件名守门 | 想法层才是高频 AI 生成面；节点由作者模板化创建。范围纪律，不加 `node-filename-mismatch` |

---

## 2 任务 A：AGENTS.md 建议书（`pcp agents`）

**INT-D1** `pcp agents` 是**只读**子命令：向 stdout 打印一段带标记区间的英文建议段落，不写任何文件。**写 `.planning/` 数据面的命令仍是 `init` / `focus` / `graduate` 三条**（`build` 也写文件，但只写投影目录 `.planning/dist/`，不属于数据面）——AGENTS.md 是用户拥有的仓库级文件，既不在数据面也不在投影面内；PCP 是建议书角色，不是执法者（打印 + 用户自贴 = 一次粘贴，全 session 生效）。

**INT-D2** 段落首尾带标记 `<!-- pcp:agents begin v1 -->` / `<!-- pcp:agents end -->`：用户粘贴后可整段替换式自管理更新（未来 PCP 升级段落内容，用户重跑命令覆盖区间即可）。begin 标记带版本号 `v1`，为将来"检测用户贴的段落已过时"留钩子——本版本不实现任何检测，只固定格式（现在加零成本，事后加要改所有已粘贴的仓库）。

**INT-D3** 段落内容（英文固定，建议书口吻，均可被用户修改）：

1. 本仓库由 PCP 管理（存在 `.planning/`），数据是源、`dist/` 是投影（勿手改）；
2. session 工作流：开始/恢复工作先 `pcp context`；总览用 `pcp status` / `pcp ideas`；
3. 想法捕获：新建 `.planning/ideas/IDEA-<NNNN>.yaml`（给出最小骨架：id/title/status: OPEN/detail/**relates_to**/benchmark_sources/methodology_sources/created/last_updated），下一个可用 id 看 `pcp ideas` 尾行。骨架必须含 `relates_to`（可为空列表）：没有它，AI 捕获的想法不挂任何节点，`pcp ideas --for NODE` 视图看不到，登记约定（第 7 条）的价值也打折；
4. 毕业：`pcp graduate <idea-id> --to NODE [--note TEXT]`（节点须已存在于 `.planning/nodes/`，命令做两文件原子写 + 论据转录）；
5. 收尾：`pcp validate` 清掉 ERROR（WARNING 不阻断）；
6. 外部文档命名**建议**（仅覆盖**一次性产出**：plans / 研究笔记 / session 记录）：`YYYY-MM-DD-<slug>.md`，与 superpowers 计划文件同风格。**specs 不适用此建议**，用稳定 slug（可带语言后缀，如 `<topic>-spec.zh-CN.md`）：plan 是一次性执行产物，日期就是它的身份；spec 是长期修订文档，出生日期在 R5 修订时会误导读者。本仓库现状即此实践（`docs/superpowers/plans/` 带日期前缀，`docs/superpowers/specs/` 用稳定 slug）——建议若覆盖 specs，PCP 自己的仓库就是第一条反例；
7. 登记约定（弱版本）：落地的 spec / plan 路径写进对应想法的 `benchmark_sources` / `methodology_sources` 的 `ref`——这样 `pcp ideas` 视图能看到"想法有没有 spec、有没有 plan"，无需 PCP 校验任何外部文件。

**INT-D4** v1 段落为**静态模板**：不插值项目 id / 路径（`.planning/` 本身是常量约定）。若未来需要项目感知（如自定义目录）再修订。

**INT-D5** 退出码：成功 0；无业务失败路径（用法错误由 argparse 报 2）。输出英文纯文本、无颜色（CLI 既有惯例）。

**INT-D14** `pcp init` 成功输出末尾追加一行提示（内容形如 `next: run 'pcp agents >> AGENTS.md' to teach your AI harness about this project`）。**依据**：任务 A / B 的价值链第一环都要求用户已经知道 `pcp agents` 和 SKILL.md 存在——这是本草案要解决的知晓问题的同构版本，不闭环则两个资产等于没有入口。`pcp init` 是新项目唯一一定会被执行的命令，是唯一天然的 bootstrap 点。**写入面不变**：只多打印一行，不多写一个文件。**不需要测试豁免**：既有 init 断言是包含式（`"created:" in out`），新增输出行不影响。

**INT-D17** `pcp agents` 的 `--help` 一行须明写"print an AGENTS.md snippet"。命令名保持 `agents` 不改（AGENTS.md 是文件名事实标准，用户能猜到），但在 harness 语境里 `agents` 容易被读成"列出/管理 agents"，help 措辞是消歧的最低成本手段。

---

## 3 任务 B：Skill 封装

**INT-D6** 家在 `integrations/skills/pcp/SKILL.md`（随仓库分发）：它是给 harness 的资产，不是 PCP 运行时的一部分——不进 `src/`、不进包。安装 = 复制或链接到目标 harness 的 skills 目录（README 双语说明；`pip install` 用户的获取路径见 INT-D16）。

**INT-D7** 与 AGENTS.md 段落的内容分工（单一事实源原则）：

- **SKILL.md = 怎么用 PCP**：**九条命令**的手册（现有八条 `init` / `validate` / `status` / `context` / `focus` / `ideas` / `graduate` / `build`，加本草案新增的 `agents`）——用法、退出码、写命令的原子性语义、session 工作流、以及"尊重本仓库 AGENTS.md 里的规矩"；
- **AGENTS.md 段落 = 这个仓库的规矩**（命名规范、登记约定）。

仓库级规矩只存在于 AGENTS.md 段落一处，SKILL.md 引用而不复制——避免两处漂移。

**INT-D8** SKILL.md 的 `description` 覆盖触发场景（渐进披露：只有描述常驻上下文，正文按需加载）：仓库含 `.planning/`（PCP 管理的仓库）、开始/恢复工作（`pcp context`）、捕获或毕业想法、结束前校验（`pcp validate`）、规划文档命名。措辞在实现时打磨，验收以覆盖上述场景为准。

**INT-D9** 语言：英文（harness 资产的事实标准），不进 i18n 体系——i18n 服务于 build 投影层，CLI 与 harness 资产沿用英文惯例。

**INT-D15** SKILL.md 的命令清单一致性由**测试门禁**保证，不靠人眼验收：新增测试从 `_build_parser()` 取 subparser 名字集合，断言（a）每条命令名都出现在 SKILL.md 正文中，（b）SKILL.md 不提及任何未注册的命令。**依据**：INT-D7 用"单一事实源"论证仓库规矩只放一处，但命令清单在 SKILL.md 里天然是第二份拷贝——没有机制保证 CLI 改动时它跟着改，就是自己犯自己反对的错。成本为一个测试函数。

**INT-D16** 分发口径裁定（v1）：**保持仓库分发**，README 给出 raw URL 与一行下载命令，不打进 Python 包。**依据**：INT-D6 的"skill 不是运行时的一部分"是结构判断；为一个尚未验证的采用假设就把资产塞进包不划算，而 raw URL 成本为零且立即可用。**已知代价**：`pip install` 用户（"装了 PCP"的主体）不能只靠已安装的包拿到 skill，必须访问仓库。若实际采用数据显示这是断点，V0.2 加 `pcp agents --skill`（打印 skill 正文，与任务 A 的建议书模式同构，写入面仍为零）翻转此裁定。

---

## 4 任务 C：想法文件名卫生（补 IDEA-D6 的门）

**INT-D10** 背景：IDEA-D6 规定一文件一想法、文件名 `<id>.yaml`，但 validator 现无任何 filename 规则——`trend-view.yaml` 内写 `id: IDEA-0007` 可干净加载、干净通过校验。这是跨 session 命名漂移在 PCP 内部数据面上的缺口。

**INT-D11** 新校验规则 `idea-filename-mismatch`（Severity **WARNING**）：想法文件名 stem ≠ `id` 时报，消息建议重命名为 `<id>.yaml`。定位镜像 `idea-id-collides-with-node`（提示不阻断）：id 是身份权威（D14），文件名只是索引便利（D6）；不 ERROR、不影响 validate 退出码与 build 门禁（§16 协议：仅 ERROR 影响）。仅对成功加载的想法生效；消息硬编码英文（validator 既有惯例，不走 i18n）。

比较口径（写死，避免实现自由发挥）：取 `Idea.source_file` 的 basename、去掉末尾的 `.yaml` 后缀，与 `id` 逐字节比较，**大小写敏感**（`idea-0001.yaml` 配 `id: IDEA-0001` 报 WARNING）。loader 只加载顶层 `*.yaml`（`.yml` 与子目录文件走既有 `ignored-idea-file` WARNING），因此不存在 `.yml` 分支。

**重命名建议（近乎）总是可执行**：想法 id 受 `NODE_ID_RE`（`^[A-Za-z0-9][A-Za-z0-9._-]*$`）约束，不含路径分隔符与平台保留字符，`<id>.yaml` 在主流平台因此总是合法文件名；唯一理论残余是 Windows 保留设备名（`CON` / `PRN` / `AUX` / `NUL` / `COM1-9` / `LPT1-9`——字符集并不排除它们），但与本规则的典型对象 `IDEA-NNNN` 无交集——这是 WARNING 消息敢于直接给出重命名指令的前提。

**INT-D12** `pcp ideas` 成功读取想法目录的输出路径，末尾追加一行 `next free id: IDEA-<NNNN>`（计算口径见 INT-D18）。纯建议行，给跨 session 的下一个创建动作现成抓手。

位置约束：该行**必须是输出的最后一行**，排在既有 `note: N idea record(s) not shown ...` 行之后。这既是语义上的收尾，也把对既有测试的影响压到最小（首行断言不受影响）。

边界钉死：「`idea files exist but could not be loaded`」（目录里有文件但一条都没加载成功）同样是**退出 0** 的列举路径，尾行照常显示、同样排在 `note:` 之后——INT-D18 的磁盘口径恰好在该场景给出安全编号（这正是该条款的存在理由）。

**本任务显式豁免"既有测试零修改"**：允许为该新增行为最小更新既有输出断言（新增输出行，不改既有语义）。爆炸半径已核实并封顶——受影响断言集中在 `tests/test_ideas.py` 一个文件**共 7 处**：5 处 `out.rstrip().endswith("via: ...")` 尾断言、1 处 `len(lines) == N` 行数断言、1 处从 `splitlines()` 提取 id 列表的断言（其 `not line.startswith("==")` 过滤器会捞到尾行）。另有 3 处 splitlines 断言（首行/前几行定位式、表头过滤式）经核实**不受**尾行影响，不得顺手修改。其余测试文件不受影响。实现时若修改超出此范围，说明尾行位置或口径偏离了本条，应先回看而不是继续改测试。

**INT-D18** next-free-id 计算口径（**数据安全条款**）：

1. **候选集合 = 已加载的想法 id ∪ `.planning/ideas/` 顶层 `*.yaml` / `*.yml` 文件名 stem**。只算顶层：子目录里的文件不会与顶层新建文件撞名。
2. 从候选集合中取完整匹配 `^IDEA-(\d+)$` 的项，编号取最大值 +1；零匹配 → `IDEA-0001`。**必须完整匹配**：子串匹配会把合法 id `MY-IDEA-0042-x` 误算进来。
3. 格式 `IDEA-%04d`（四位零填充）；编号超过 9999 时自然进位（`IDEA-10000`），不截断、不报错。
4. 口径**与任何过滤无关**：`--status` / `--for` / `--subtree` 下的尾行与不过滤时完全相同。按过滤后集合计算会给出错误的 next id（如 `--status DISCARDED` 只看到 3 条就建议 `IDEA-0004`）。

**为什么必须并入磁盘文件名（第 1 点）**：只有成功解析的想法才进 `project.ideas`——一个 YAML 语法错的 `IDEA-0008.yaml` 会变成 `invalid-idea-file` ERROR 并被跳过。若只看 `project.ideas`，尾行会打印 `next free id: IDEA-0008`，而该文件在磁盘上存在；这条尾行的读者恰恰是"照着做"的 AI，结果是覆盖用户尚未修复的文件。磁盘扫描在 `cli.py` 内用 `project.planning_dir()` 完成，不改 loader。

**INT-D13** 影响面：`cli.py`（`pcp agents` 命令 + `pcp ideas` 尾行与磁盘扫描 + `pcp init` 提示行 + parser 接线）、`validator.py`（新规则——本任务的正当引擎触点）、`integrations/skills/pcp/SKILL.md`（新资产）、`README.md` / `README.zh-CN.md`、新增测试文件。其余引擎零改动（`model.py` / `loader.py` / `generator.py` / `i18n.py` / `templates/` / `context.py` / `graph.py`）。

---

## 5 验收

1. `pcp agents`：输出含带版本的标记区间（`<!-- pcp:agents begin v1 -->` / `<!-- pcp:agents end -->`）与 INT-D3 全部要点（含骨架里的 `relates_to`、收窄后的命名建议）；运行前后 `git status` 无变化（只读证明）；不写任何文件（含 AGENTS.md 本身）；`pcp agents >> AGENTS.md` 追加后区间完整可识别；`--help` 含 INT-D17 措辞；
2. `pcp init`：成功输出末尾含 INT-D14 提示行；既有 init 测试断言零修改；
3. Skill：`integrations/skills/pcp/SKILL.md` 存在，description 覆盖 INT-D8 场景；INT-D15 的一致性测试通过（九条命令全覆盖、无多余命令）；
4. validate：文件名与 id 错配 → `idea-filename-mismatch` WARNING 且退出码 0；配对 → 无该 WARNING；仅大小写不同（`idea-0001.yaml` / `id: IDEA-0001`）→ 报（大小写敏感）；
5. `pcp ideas` 尾行（逐条对应 INT-D18）：
   - `.planning/ideas/` **目录不存在**（`pcp init` 后的默认状态，init 不创建该目录）→ `next free id: IDEA-0001`；
   - 目录存在但为空 → 同上；
   - 有 `IDEA-0007` → `IDEA-0008`；
   - 磁盘存在 `IDEA-0008.yaml` 但 YAML 解析失败（不在 `project.ideas` 内）→ `IDEA-0009`，不指向已存在文件；
   - 存在 `MY-IDEA-0042-x` 之类 id → 不参与编号计算；
   - `--status` / `--for` 过滤下的尾行与不过滤时相同；
   - 尾行是输出最后一行，排在 `note: ... not shown` 行之后；
   - 项目加载失败路径（`_load_project` 返回 `None`）不显示该行；
6. 全量测试绿；既有断言的修改仅限 `tests/test_ideas.py` 的 7 处（INT-D12 豁免范围）；
7. 两份 README 各覆盖：`pcp agents` 表格行与 `>> AGENTS.md` 一行用法、`pcp init` 提示、Skill 安装说明（含 INT-D16 的 raw URL 获取路径）、文件名 WARNING 与 next-id 提示。

---

## 附录 D 修订记录

### D.1 修订记录 R1（初稿）

| # | 改动 | 依据 |
| --- | --- | --- |
| 1 | 初稿：任务 A（`pcp agents` 只读建议书）、任务 B（`integrations/skills/pcp/SKILL.md`）、任务 C（`idea-filename-mismatch` WARNING + next-free-id 尾行） | 跨 session 采用缺口的两轮方向裁定（2026-08-28）：知晓问题用指令层（AGENTS.md/Skill）解决而非 MCP；外部文件命名不校验（身份在注册表），登记制候 PLAN 世界；内部缺口（IDEA-D6 无守门）用 WARNING 补门 |
| 2 | 写入面不变裁定：`pcp agents` 只打印不写文件 | AGENTS.md 是用户拥有的仓库级文件、不在 `.planning/` 数据面内；打印 + 自贴已满足"一次粘贴、全 session 生效"，代价为零写入面 |
| 3 | 允许为 `pcp ideas` 新增尾行最小更新既有测试断言 | 该行是新增输出而非语义变更；沿用"既有测试零修改"会逼出规避式实现（如藏 stderr），得不偿失 |

### D.2 修订记录 R2（审查修订，2026-08-28）

| # | 改动 | 依据 |
| --- | --- | --- |
| 1 | **INT-D18 新增**：next-free-id 候选集合并入磁盘文件名 stem（顶层 `*.yaml` / `*.yml`） | 数据安全。R1 口径只看 `project.ideas`，而解析失败的想法文件不入该字典（`invalid-idea-file` ERROR 后跳过）；尾行会建议一个磁盘上已存在的 id，读者是照做的 AI，后果是覆盖未修复的用户文件 |
| 2 | INT-D18 同时写死：完整匹配 `^IDEA-(\d+)$`、`IDEA-%04d` 零填充、超 9999 自然进位、口径与过滤无关 | R1 只写"`IDEA-(\d+)` 模式"，未锚定会把 `MY-IDEA-0042-x` 误算；宽度与过滤关系未定会导致实现自由发挥、验收对不上 |
| 3 | **事实订正** INT-D7：「七个命令」→ 现有八条 + `agents` 共九条 | 实际命令面为 `init` / `validate` / `status` / `context` / `focus` / `ideas` / `graduate` / `build` |
| 4 | **事实订正** INT-D1：写入面表述限定为「写 `.planning/` 数据面的命令三条」 | `pcp build` 也写文件（投影目录 `.planning/dist/`）。INT-D1 整段论证依赖这条不变量，措辞必须准确 |
| 5 | **事实订正** INT-D3-6：命名建议收窄到一次性产出（plans / 研究笔记 / session 记录），specs 排除在外 | 原建议与本仓库自身实践冲突（`docs/superpowers/specs/` 无日期前缀）；且区分有理由——plan 是一次性产物、日期即身份，spec 长期修订、出生日期误导。不收窄则 PCP 建议书的第一条反例是 PCP 自己 |
| 6 | **INT-D14 新增**：`pcp init` 尾行提示 `pcp agents >> AGENTS.md` | bootstrap 闭环。任务 A/B 的第一环都要求用户已知道这两个资产存在，等于用知晓问题解决知晓问题；`init` 是唯一一定会被执行的命令。写入面不变，且既有 init 断言为包含式，零测试改动 |
| 7 | **INT-D15 新增**：SKILL.md 命令清单一致性改为测试门禁 | R1 验收 #2「与 `pcp --help` 一致」靠人眼，没有机制阻止 CLI 改动后漂移——正是 INT-D7 自己反对的两处漂移 |
| 8 | **INT-D16 新增**：分发口径裁定（保持仓库分发 + raw URL，`pcp agents --skill` 列 V0.2 候选） | R1 未交代 `pip install` 用户如何拿到 SKILL.md，而这正是"装了 PCP"的主体，是采用链上的实际断点。v1 选低成本方案并记下已知代价与翻转条件 |
| 9 | **INT-D17 新增**：`--help` 明写 "print an AGENTS.md snippet" | `agents` 在 harness 语境易被读成"列出/管理 agents"；不改命令名（AGENTS.md 是文件名事实标准），用 help 措辞消歧 |
| 10 | INT-D3-3 骨架补 `relates_to` | 缺该字段则 AI 捕获的想法不挂节点，`pcp ideas --for NODE` 看不到，登记约定价值打折 |
| 11 | INT-D2 标记加版本 `v1` | 为将来检测过时段落留钩子；现在加零成本，事后加要改所有已粘贴的仓库 |
| 12 | INT-D11 补比较口径（basename 去 `.yaml`、大小写敏感、无 `.yml` 分支）与 id 字符集依据 | 避免实现自由发挥；`NODE_ID_RE` 保证 `<id>.yaml` 跨平台合法，是"建议重命名"总是可执行的前提 |
| 13 | INT-D12 补位置约束（末行、`note:` 之后）与爆炸半径量化（`tests/test_ideas.py`，后经复核订正为 7 处，见第 16 条） | 尾行放末尾可把既有断言影响压到最小；量化后豁免范围可验收，超出即信号 |
| 14 | 验收 #5 补「`ideas/` 目录不存在」「解析失败文件占位」「非 IDEA 前缀 id」「过滤下不变」四种状态 | R1 只写了"空目录"，而 `pcp init` 不创建 `ideas/`，目录不存在才是新项目默认状态 |
| 15 | §1 非目标表补一句「不校验 ≠ 不建议」 | 原依据栏说"任何规则都武断"，紧接着 INT-D3 又发命名建议，读者会看成自相矛盾；两者不冲突，但依据要说全 |
| 16 | R2 定稿复核（逐条对代码核验后）三处订正：(a) 爆炸半径订正为 7 处——原 8 处的构成有误：漏计 `len(lines) == N` 行数断言，误计 2 处实际不受影响的定位式断言（首行 `splitlines()[0]`、前几行 `lines[n]`）；(b) INT-D11 平台合法性补 Windows 保留设备名残余（`CON`/`NUL` 等——字符集不排除，与 `IDEA-NNNN` 无交集）；(c) INT-D12 钉死「could not be loaded」为退出 0 路径、尾行照常显示 | (a)(c) 复核 `tests/test_ideas.py` 与 `cmd_ideas` 源码确认：该路径 `return EXIT_OK`，且恰是 INT-D18 最需要发挥作用的场景；(b) `NODE_ID_RE` 只管字符集，Windows 保留名是另一维度，原句"任何平台总是合法"为过强不变量 |
