# PCP Harness 集成层实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让装了 PCP 的 harness 在正确时机想起调用它（`pcp agents` 建议书 + SKILL.md 资产 + `pcp init` bootstrap 提示），并补上想法层文件名的守门规则与 next-free-id 提示。

**Architecture:** 三条互不耦合的改动线。任务 A/B 是**指令层资产**：`pcp agents` 打印一段带标记的英文 AGENTS.md 段落（只读，用户自贴），`integrations/skills/pcp/SKILL.md` 是随仓库分发的 harness 资产，两者内容分工靠"仓库规矩只在 AGENTS.md、命令手册只在 SKILL.md"划开。任务 C 是**引擎内改动**：validator 新增一条 WARNING 规则，`pcp ideas` 输出末尾加一行 next-free-id 建议，编号口径必须并入磁盘文件名以免建议覆盖已存在的文件。

**Tech Stack:** Python 3.10+（`from __future__ import annotations`）、argparse、PyYAML、pytest。无新依赖。

**Spec:** [docs/superpowers/specs/harness-integration-spec-draft.zh-CN.md](../specs/harness-integration-spec-draft.zh-CN.md)（R2 定稿）

## Global Constraints

- **语言**：CLI 输出、AGENTS.md 段落、SKILL.md 一律英文硬编码，不进 i18n 体系（INT-D9；i18n 只服务 build 投影层）。计划文档与提交信息用中文。
- **退出码**：`0` 成功 · `1` 业务失败 · `2` 用法/加载错误。`pcp agents` 无业务失败路径，恒返回 `EXIT_OK`（INT-D5）。
- **写入面**：本计划**不新增任何写文件的命令**。写 `.planning/` 数据面的命令仍是 `init` / `focus` / `graduate` 三条（INT-D1）。`pcp agents` 连 AGENTS.md 本身都不写。
- **标记格式**：AGENTS.md 段落首尾固定为 `<!-- pcp:agents begin v1 -->` / `<!-- pcp:agents end -->`，版本号写死 `v1`（INT-D2）。
- **规则严重度**：`idea-filename-mismatch` 是 **WARNING**，不得影响 `pcp validate` 退出码，也不得进入 `pcp build` 门禁（INT-D11）。
- **测试纪律**：只允许修改本计划 Task 5 明确列出的既有断言（实测清单，11 处）与 Task 4 的规则名闭集 pin。**改动超出该清单即为信号**：说明尾行位置或编号口径偏离了 spec，应先回看 INT-D12 / INT-D18，而不是继续改测试。
- **提交粒度**：每个 Task 结束提交一次，提交信息用中文 conventional commits（`feat:` / `test:` / `docs:`）。
- **命令面事实**：现有八条命令 `init` / `validate` / `status` / `context` / `focus` / `ideas` / `graduate` / `build`，本计划新增 `agents`，共九条（INT-D7）。

## spec 偏差（实施前须知，两条）

计划编写期间逐条对代码核验，发现 spec R2 有两处与代码不符。本计划按**实测事实**执行，并在此显式记录，供合并主 spec 时回填：

| # | spec 条款 | spec 说法 | 实测事实 | 本计划处理 |
| --- | --- | --- | --- | --- |
| 1 | INT-D12 爆炸半径 | `tests/test_ideas.py` **7 处**（5 endswith + 1 len + 1 id 列表） | **11 处**（11 个测试函数、12 个断言行）。做法：临时在 `cmd_ideas` 末尾插入尾行 → 跑全量测试 → 收集失败 → 还原。漏计的 4 处是：3 处 `out.strip() == "<空态提示>"` 全等断言（`:414` / `:484` / `:608`）与 1 处 `len(lines) == 6`（`:434`） | Task 5 给出实测清单与逐条改法。三处空态全等断言受影响是**预期内**：验收 #5 明确要求目录不存在 / 无匹配时尾行照常显示 |
| 2 | INT-D13 影响面 | 「其余引擎零改动（`model.py` / ...）」 | `model.py:IDEA_RULE_NAMES` 是想法层规则名的**闭集定义**（§58.1、IDEA-D59 门禁判据），新规则名必须注册；且 `tests/test_ideas.py:38` 有硬 pin 断言该集合 | Task 4 一并改 `model.py`（加一个规则名）与该 pin 测试（注释 18 → 19）。不改则闭集定义与实际规则集脱节 |

两条偏差都不改变 spec 的任何设计裁定，只订正事实描述。

---

## File Structure

**新建**

| 文件 | 责任 |
| --- | --- |
| `integrations/skills/pcp/SKILL.md` | harness 资产：九条命令的手册 + session 工作流 + "尊重本仓库 AGENTS.md"。不进 `src/`、不进包（INT-D6/D16） |
| `tests/test_agents.py` | `pcp agents` 命令与 `pcp init` bootstrap 提示的测试（Task 1、2） |
| `tests/test_skill_asset.py` | SKILL.md 存在性、description 场景覆盖、命令清单一致性门禁（Task 3） |
| `tests/test_idea_filename.py` | `idea-filename-mismatch` 规则测试（Task 4） |
| `tests/test_ideas_next_id.py` | next-free-id 尾行与编号口径测试（Task 5） |

**修改**

| 文件 | 改动 |
| --- | --- |
| `src/planning_control_plane/cli.py` | 新增 `_AGENTS_SNIPPET` 常量、`cmd_agents`、`agents` subparser；`cmd_init` 末尾提示行；`_next_free_idea_id` 辅助函数与 `cmd_ideas` 尾行 |
| `src/planning_control_plane/model.py` | `IDEA_RULE_NAMES` 加 `"idea-filename-mismatch"`（见 spec 偏差 #2） |
| `src/planning_control_plane/validator.py` | `_check_ideas` 内新增文件名比对规则 |
| `tests/test_ideas.py` | 规则名闭集 pin（`:38`）+ 11 处输出断言（Task 5 清单） |
| `README.md` / `README.zh-CN.md` | CLI 表格加 `agents` 行；新增 Skill 安装小节；想法层小节补 WARNING 与 next-id |

**为什么 AGENTS.md 段落放 `cli.py` 而不是新模块**：`cli.py` 已有 `_PROJECT_TEMPLATE` / `_ROADMAP_TEMPLATE` / `_GITIGNORE_TEMPLATE` 三个同类文本常量的先例，段落只是第四个。新开模块会让"模板住哪"这件事出现两个答案，且与 INT-D13 的影响面清单不符。

---

## Task 1: `pcp agents` 命令（INT-D1–D5、D17）

**Files:**
- Modify: `src/planning_control_plane/cli.py`（常量区加 `_AGENTS_SNIPPET`；`cmd_build` 之后加 `cmd_agents`；`_build_parser` 内 `init_parser` 之后接线）
- Test: `tests/test_agents.py`（新建）

**Interfaces:**
- Consumes: `EXIT_OK`（`cli.py:49`）、`cli` fixture（`tests/conftest.py`，签名 `cli(*argv) -> (code, out, err)`，**全局 `-p` 必须排在子命令之前**）
- Produces: `cli._AGENTS_SNIPPET: str`（以 `\n` 结尾的完整段落）、`cli.cmd_agents(args: argparse.Namespace) -> int`、子命令名 `"agents"`（Task 2、3 依赖此名字存在）

- [ ] **Step 1: 写失败测试**

新建 `tests/test_agents.py`：

```python
"""Harness integration: the AGENTS.md advisory command (spec INT-D1..D5, D14, D17)."""

from planning_control_plane import cli as cli_module

BEGIN = "<!-- pcp:agents begin v1 -->"
END = "<!-- pcp:agents end -->"


def test_agents_prints_a_marker_delimited_block(cli):
    code, out, err = cli("agents")
    assert (code, err) == (0, "")
    assert out.startswith(BEGIN)
    assert out.rstrip().endswith(END)
    assert out.endswith("\n")  # append-friendly: 'pcp agents >> AGENTS.md'


def test_agents_covers_every_int_d3_point(cli):
    _code, out, _err = cli("agents")
    # INT-D3 1..7, in order: data plane, session workflow, idea capture,
    # graduation, validate, document naming, registration convention.
    for needle in (
        ".planning/",
        "dist/",
        "pcp context",
        "pcp status",
        "pcp ideas",
        ".planning/ideas/IDEA-",
        "relates_to",
        "benchmark_sources",
        "methodology_sources",
        "pcp graduate",
        "pcp validate",
        "YYYY-MM-DD-",
        "ref",
    ):
        assert needle in out, needle


def test_agents_naming_advice_excludes_specs(cli):
    """INT-D3-6: the date prefix covers one-shot artifacts only."""
    _code, out, _err = cli("agents")
    assert "stable slug" in out


def test_agents_writes_nothing(cli, tmp_path):
    """INT-D1: read-only — no project load, no file written, not even AGENTS.md."""
    root = tmp_path / "repo"
    root.mkdir()
    code, _out, _err = cli("-p", str(root), "agents")
    assert code == 0
    assert list(root.iterdir()) == []


def test_agents_works_without_a_planning_directory(cli, tmp_path):
    """No .planning is needed: the snippet is a static template (INT-D4)."""
    root = tmp_path / "bare"
    root.mkdir()
    code, out, err = cli("-p", str(root), "agents")
    assert (code, err) == (0, "")
    assert BEGIN in out


def test_agents_help_says_it_prints_an_agents_md_snippet():
    """INT-D17: 'agents' reads as 'manage agents' in a harness context."""
    help_text = cli_module._build_parser().format_help()
    assert "agents" in help_text
    assert "AGENTS.md" in help_text
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_agents.py -q`
Expected: FAIL —— argparse 报 `invalid choice: 'agents'`（`SystemExit: 2`）。

- [ ] **Step 3: 加段落常量**

在 `src/planning_control_plane/cli.py` 的 `_GITIGNORE_TEMPLATE` 之后（常量区末尾）加：

````python
#: Ready-to-paste AGENTS.md section printed by ``pcp agents`` (spec INT-D2,
#: INT-D3). Static by design (INT-D4): no project id, no path interpolation
#: — ``.planning/`` is a constant convention. The ``v1`` in the begin marker
#: is a hook for a future staleness check; the format is fixed now because
#: adding it later would mean editing every repository that already pasted
#: the block.
_AGENTS_SNIPPET = """\
<!-- pcp:agents begin v1 -->
## Planning Control Plane (PCP)

This repository is managed by PCP. `.planning/` holds the planning data and is
the single source of truth; `.planning/dist/` is a generated projection — never
edit it by hand, run `pcp build` to regenerate it.

**Session workflow**

- Starting or resuming work: run `pcp context` first (pass a node id for a
  specific node, `--full` for ancestors and dependency detail).
- Overview: `pcp status` for the planning graph, `pcp ideas` for the idea layer.
- Before wrapping up: run `pcp validate` and clear every ERROR. WARNINGs are
  advisory and do not block.

**Capturing an idea**

Ideas are files, not a CLI write path: create `.planning/ideas/IDEA-<NNNN>.yaml`
yourself. The next free id is printed on the last line of `pcp ideas`. Minimal
skeleton:

```yaml
id: IDEA-0001
title: One line — what the thought is
status: OPEN               # OPEN | PARKED | PROMOTED | DISCARDED
detail: |
  Free text. Why this might matter, what is still open.
relates_to: []             # planning node ids this thought touches
benchmark_sources: []      # - ref: docs/some-note.md   (repo-relative)
methodology_sources: []    # - note: free text, for anything outside the repo
created: 2026-01-01
last_updated: 2026-01-01
```

Keep `relates_to` even when empty: without it the idea hangs off no node and
`pcp ideas --for <node>` will never surface it.

**Graduating an idea**

`pcp graduate <idea-id> --to <node-id> [--note TEXT]` sets `status: PROMOTED`
plus `outcome` on the idea and copies its ref-carrying justification entries
into the node's `evidence_sources`. The target node must already exist under
`.planning/nodes/` — PCP never authors planning semantics for you.

**Naming planning documents**

One-shot artifacts (plans, research notes, session records): `YYYY-MM-DD-<slug>.md`.
Long-lived specs keep a stable slug instead (`<topic>-spec.md`) — a spec is
revised for months, so a birth date in its name misleads the reader.

**Registration convention**

When a spec or plan lands, put its repository-relative path into the matching
idea's `benchmark_sources` / `methodology_sources` as a `ref`. `pcp ideas` then
shows which thoughts already have a spec or a plan behind them.
<!-- pcp:agents end -->
"""
````

- [ ] **Step 4: 加命令函数**

在 `cmd_build` 之后、`_build_parser` 之前加：

```python
def cmd_agents(args: argparse.Namespace) -> int:
    """``pcp agents`` — print the AGENTS.md advisory snippet (spec INT-D1).

    Read-only by construction: no project is loaded and no file is written,
    AGENTS.md included. That file is a repository-level file owned by the
    user and sits outside the ``.planning`` data plane, so PCP prints and
    the user pastes (``pcp agents >> AGENTS.md`` is the one-liner).
    """
    print(_AGENTS_SNIPPET, end="")
    return EXIT_OK
```

- [ ] **Step 5: 接线 subparser**

在 `_build_parser()` 内 `init_parser.set_defaults(func=cmd_init)` 之后加（放在 `init` 之后是有意的：`pcp --help` 里与 `init` 相邻，和 INT-D14 的提示叙事一致）：

```python
    agents_parser = subparsers.add_parser(
        "agents",
        help="print an AGENTS.md snippet that teaches AI harnesses this repository's PCP workflow",
        description=(
            "Print a ready-to-paste AGENTS.md section, delimited by "
            "<!-- pcp:agents begin v1 --> / <!-- pcp:agents end --> markers so "
            "a later PCP version can replace the block in place. Read-only: "
            "nothing is written, AGENTS.md included — append it yourself with "
            "'pcp agents >> AGENTS.md'."
        ),
    )
    agents_parser.set_defaults(func=cmd_agents)
```

同时更新 `cli.py` 模块 docstring 的命令清单（第 7–10 行），把 `agents` 加进去：

```python
Implemented commands (spec §4): ``init`` (§5), ``agents`` (INT-D1), ``validate``
(§16/§17), ``status`` (§18), ``context`` (§20/§21), ``focus`` (§19), ``ideas``
(§60), ``graduate`` (spec IDEA §55/§62.3) and ``build`` / ``build --check``
(§22/§23).
```

- [ ] **Step 6: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_agents.py -q`
Expected: PASS（6 个测试；`test_agents_covers_every_int_d3_point` 若报某个 needle 缺失，是段落漏了 INT-D3 的某一条，补段落而不是删断言）

- [ ] **Step 7: 跑全量测试**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 全绿。新增命令不改任何既有输出。

- [ ] **Step 8: 提交**

```bash
git add src/planning_control_plane/cli.py tests/test_agents.py
git commit -m "feat(agents): add pcp agents advisory command (INT-D1..D5, D17)"
```

---

## Task 2: `pcp init` bootstrap 提示行（INT-D14）

**Files:**
- Modify: `src/planning_control_plane/cli.py`（`cmd_init` 结尾的 `return EXIT_OK` 之前）
- Test: `tests/test_agents.py`（追加，与命令同文件：断言的是指向 `pcp agents` 的提示）

**Interfaces:**
- Consumes: Task 1 产出的子命令名 `"agents"`
- Produces: 无新符号。`pcp init` stdout 末尾多一行固定文本

- [ ] **Step 1: 写失败测试**

在 `tests/test_agents.py` 末尾追加：

```python
def test_init_points_at_the_agents_command(cli, tmp_path):
    """INT-D14: init is the only command a new project is guaranteed to run,
    so it is the only natural bootstrap point for the advisory snippet."""
    root = tmp_path / "fresh"
    root.mkdir()
    code, out, err = cli("-p", str(root), "init")
    assert (code, err) == (0, "")
    assert out.splitlines()[-1] == (
        "next: run 'pcp agents >> AGENTS.md' to teach your AI harness about this project"
    )


def test_init_hint_does_not_write_anything_extra(cli, tmp_path):
    """The hint is output only: the write surface stays init/focus/graduate."""
    root = tmp_path / "fresh2"
    root.mkdir()
    code, _out, _err = cli("-p", str(root), "init")
    assert code == 0
    assert not (root / "AGENTS.md").exists()
    assert sorted(p.name for p in root.iterdir()) == [".planning"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_agents.py -q -k init`
Expected: FAIL —— 末行是 `created: .../.planning/.gitignore`，不是提示行。

- [ ] **Step 3: 实现**

`src/planning_control_plane/cli.py` 的 `cmd_init` 内，把结尾改成：

```python
        else:
            path.write_text(content, encoding="utf-8")
            print(f"created: {path}")
    # INT-D14: the advisory snippet and the SKILL.md asset are worthless if
    # nobody knows they exist. init is the one command every new project
    # runs, so it carries the pointer. Output only — nothing extra is written.
    print(
        "next: run 'pcp agents >> AGENTS.md' to teach your AI harness about this project"
    )
    return EXIT_OK
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_agents.py tests/test_init.py -q`
Expected: PASS。`tests/test_init.py` **零修改**——既有断言是包含式（`"created:" in out`），新增行不影响（INT-D14 已核实）。

- [ ] **Step 5: 跑全量测试**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 全绿。

- [ ] **Step 6: 提交**

```bash
git add src/planning_control_plane/cli.py tests/test_agents.py
git commit -m "feat(init): point new projects at pcp agents (INT-D14)"
```

---

## Task 3: SKILL.md 资产与一致性门禁（INT-D6–D9、D15、D16）

**Files:**
- Create: `integrations/skills/pcp/SKILL.md`
- Test: `tests/test_skill_asset.py`（新建）

**Interfaces:**
- Consumes: `cli._build_parser()`（Task 1 之后其 subparser choices 为九条命令）
- Produces: 仓库路径 `integrations/skills/pcp/SKILL.md`（Task 6 的 README 安装说明引用此路径）

- [ ] **Step 1: 写失败测试**

新建 `tests/test_skill_asset.py`：

```python
"""The harness skill asset and its drift gate (spec INT-D6..D9, D15)."""

import argparse
import re
from pathlib import Path

from planning_control_plane import cli as cli_module

SKILL_PATH = Path(__file__).resolve().parent.parent / "integrations" / "skills" / "pcp" / "SKILL.md"

#: Commands as they appear in prose: `pcp <name>` inside backticks.
_COMMAND_MENTION_RE = re.compile(r"`pcp ([a-z][a-z0-9-]*)")


def _registered_commands() -> set[str]:
    """The authoritative command set: argparse's own subparser choices."""
    parser = cli_module._build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    raise AssertionError("no subparsers registered on the pcp parser")


def test_skill_asset_exists():
    assert SKILL_PATH.is_file(), f"missing harness asset: {SKILL_PATH}"


def test_skill_frontmatter_covers_the_trigger_scenarios():
    """INT-D8: only the description stays in context, so it carries the
    triggers — progressive disclosure means the body is loaded on demand."""
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    frontmatter = text.split("---", 2)[1]
    assert "name: pcp" in frontmatter
    lowered = frontmatter.lower()
    for scenario in (".planning", "resum", "idea", "graduat", "validate", "naming"):
        assert scenario in lowered, scenario


def test_skill_documents_every_registered_command():
    """INT-D15 (a): no command may be missing from the manual."""
    text = SKILL_PATH.read_text(encoding="utf-8")
    mentioned = set(_COMMAND_MENTION_RE.findall(text))
    missing = _registered_commands() - mentioned
    assert not missing, f"SKILL.md does not document: {sorted(missing)}"


def test_skill_mentions_no_unregistered_command():
    """INT-D15 (b): and none may outlive its removal from the CLI."""
    text = SKILL_PATH.read_text(encoding="utf-8")
    mentioned = set(_COMMAND_MENTION_RE.findall(text))
    unknown = mentioned - _registered_commands()
    assert not unknown, f"SKILL.md documents commands that do not exist: {sorted(unknown)}"


def test_skill_defers_repository_rules_to_agents_md():
    """INT-D7: repository rules live in AGENTS.md alone; the skill points at
    it instead of copying it, so the two cannot drift apart."""
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "AGENTS.md" in text
    # The naming convention is a repository rule: it must NOT be restated here.
    assert "YYYY-MM-DD-" not in text
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_skill_asset.py -q`
Expected: FAIL —— `missing harness asset: .../integrations/skills/pcp/SKILL.md`。

- [ ] **Step 3: 写 SKILL.md**

新建 `integrations/skills/pcp/SKILL.md`：

````markdown
---
name: pcp
description: Use when working in a repository that contains a .planning/ directory (managed by the Planning Control Plane CLI) - starting or resuming work, reading planning context, capturing or graduating an idea, validating planning data before wrapping up, or naming planning documents.
---

# Planning Control Plane (`pcp`)

`pcp` is a repository-native planning tool. The planning data lives in
`.planning/` as YAML files and **the files are the source**: `pcp` reads them,
and only three commands write into that directory. The HTML under
`.planning/dist/` is a generated projection — never edit it by hand.

**This file is the manual for the tool. The rules for a given repository live
in that repository's own AGENTS.md** (naming conventions, registration
conventions, anything project-specific). Read AGENTS.md and follow it; if it
disagrees with this file about repository conventions, AGENTS.md wins.

## Session workflow

1. Starting or resuming work → `pcp context` (the resume capsule for the
   current focus). Add a node id for a specific node, `--full` for ancestors,
   related nodes and dependency detail.
2. Orienting → `pcp status` (planning graph) and `pcp ideas` (idea layer).
3. Capturing a thought that is not a decision yet → write an idea file
   (see below), do not grow the planning graph for it.
4. Wrapping up → `pcp validate`, clear every ERROR. WARNINGs are advisory.

## Commands

| Command | What it does |
| --- | --- |
| `pcp init` | Create the `.planning/` skeleton. Never overwrites; `--force` only fills in missing files. |
| `pcp agents` | Print the AGENTS.md snippet for this tool. Read-only — append it yourself: `pcp agents >> AGENTS.md`. |
| `pcp validate` | Structural + consistency checks, one issue per line (`ERROR` / `WARNING` + id + rule + reason). |
| `pcp status` | Project, current focus, decision counts, progress counts. |
| `pcp context [node] [--full]` | The paste-ready session resume capsule. |
| `pcp focus [node]` | Show or switch the current focus. **Writes** `project.yaml` (line-oriented; comments survive). |
| `pcp ideas [--status S] [--for NODE [--subtree]]` | List the idea layer grouped by status. The last line prints the next free idea id. |
| `pcp graduate IDEA --to NODE [--note TEXT]` | **Writes** two files: promotes the idea and copies its ref-carrying justification into the node's `evidence_sources`. |
| `pcp build [--check]` | Regenerate the HTML projection; `--check` compares instead of writing (CI drift detection). |

Global option `-p/--project-root PATH` must come **before** the subcommand.

Exit codes: `0` success · `1` business failure (validation errors, unknown
node, drift) · `2` usage or load error.

## Write semantics

Only `pcp init`, `pcp focus` and `pcp graduate` write into `.planning/`
(`pcp build` writes the projection directory only). Both `focus` and
`graduate` are line-oriented edits that preserve comments and layout, and
`graduate` verifies after writing and restores both files if the check fails.
Everything else is read-only.

## Ideas

Ideas are uncommitted thinking; planning nodes are post-decision. Capture an
idea as a file — there is no create command:

```yaml
# .planning/ideas/IDEA-0001.yaml
id: IDEA-0001
title: One line — what the thought is
status: OPEN               # OPEN | PARKED | PROMOTED | DISCARDED
detail: |
  Free text.
relates_to: []             # planning node ids this thought touches
benchmark_sources: []      # - ref: docs/note.md   (repository-relative)
methodology_sources: []    # - note: free text
created: 2026-01-01
last_updated: 2026-01-01
```

The next free id is the last line of `pcp ideas`. A broken idea file never
blocks planning: it becomes a validation issue and is skipped.

When an idea becomes a decision, graduate it into an existing node —
`pcp graduate` never creates the node for you.
````

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_skill_asset.py -q`
Expected: PASS（5 个测试）。若 `test_skill_mentions_no_unregistered_command` 失败，说明正文写了不存在的命令；若 `test_skill_documents_every_registered_command` 失败，说明漏了某条命令。

- [ ] **Step 5: 跑全量测试**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 全绿。

- [ ] **Step 6: 提交**

```bash
git add integrations/skills/pcp/SKILL.md tests/test_skill_asset.py
git commit -m "feat(skill): add harness skill asset with a command-drift gate (INT-D6..D9, D15)"
```

---

## Task 4: `idea-filename-mismatch` WARNING（INT-D10、D11）

**Files:**
- Modify: `src/planning_control_plane/model.py:159-180`（`IDEA_RULE_NAMES` 加一项）
- Modify: `src/planning_control_plane/validator.py`（`_check_ideas` 内，`idea-id-collides-with-node` 之后）
- Modify: `tests/test_ideas.py:36-50`（规则名闭集 pin）
- Test: `tests/test_idea_filename.py`（新建）

**Interfaces:**
- Consumes: `Idea.source_file`（仓库相对 posix 路径，如 `.planning/ideas/IDEA-0001.yaml`）、`idea_issue(severity, rule, detail, ident, node_id)`（`model.py:183`，自动加 `idea '<id>': ` 前缀）、`by_rule` fixture
- Produces: 规则名 `"idea-filename-mismatch"`（Task 6 的 README 引用）

- [ ] **Step 1: 写失败测试**

新建 `tests/test_idea_filename.py`：

```python
"""Idea filename hygiene (spec INT-D10, INT-D11)."""

from planning_control_plane.model import IDEA_RULE_NAMES, Severity
from planning_control_plane.validator import validate_project

RULE = "idea-filename-mismatch"


def test_rule_is_part_of_the_idea_layer_closed_set():
    """§58.1: the closed set is what identifies an idea-layer rule."""
    assert RULE in IDEA_RULE_NAMES


def test_mismatched_filename_warns(make_project, tmp_path, by_rule):
    """IDEA-D6 says <id>.yaml; before this rule nothing guarded it."""
    project, _root = make_project(
        tmp_path,
        raw_files={"ideas/trend-view.yaml": "id: IDEA-0007\ntitle: T\nstatus: OPEN\n"},
    )
    issues = by_rule(validate_project(project), RULE)
    assert len(issues) == 1
    assert issues[0].severity == Severity.WARNING
    assert issues[0].node_id == "IDEA-0007"
    assert issues[0].message == (
        "idea 'IDEA-0007': file name does not match the id; rename to 'IDEA-0007.yaml'"
    )


def test_matching_filename_is_silent(make_project, tmp_path, by_rule):
    project, _root = make_project(
        tmp_path,
        raw_files={"ideas/IDEA-0007.yaml": "id: IDEA-0007\ntitle: T\nstatus: OPEN\n"},
    )
    assert by_rule(validate_project(project), RULE) == []


def test_comparison_is_case_sensitive(make_project, tmp_path, by_rule):
    """The id is the authority; a case-different file name is still a miss."""
    project, _root = make_project(
        tmp_path,
        raw_files={"ideas/idea-0007.yaml": "id: IDEA-0007\ntitle: T\nstatus: OPEN\n"},
    )
    assert len(by_rule(validate_project(project), RULE)) == 1


def test_warning_does_not_fail_validate(make_project, tmp_path, cli):
    """INT-D11: WARNING only — the exit code and the build gate stay clean."""
    _project, root = make_project(
        tmp_path,
        raw_files={"ideas/trend-view.yaml": "id: IDEA-0007\ntitle: T\nstatus: OPEN\n"},
    )
    code, out, _err = cli("-p", str(root), "validate")
    assert code == 0
    assert RULE in out
    assert "0 error(s)" in out


def test_build_gate_ignores_the_warning(make_project, tmp_path, cli):
    """IDEA-D59: idea-layer rules never gate the build."""
    _project, root = make_project(
        tmp_path,
        node_dicts=[{"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE"}],
        raw_files={"ideas/trend-view.yaml": "id: IDEA-0007\ntitle: T\nstatus: OPEN\n"},
    )
    code, _out, _err = cli("-p", str(root), "build")
    assert code == 0


def test_unloadable_file_produces_no_filename_warning(make_project, tmp_path, by_rule):
    """Only successfully loaded ideas are checked (INT-D11): a file that never
    parsed has no id to compare against, and already has its own ERROR."""
    project, _root = make_project(tmp_path, raw_files={"ideas/BAD.yaml": "id: [unclosed\n"})
    assert by_rule(validate_project(project), RULE) == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_idea_filename.py -q`
Expected: FAIL —— `assert RULE in IDEA_RULE_NAMES` 与 `len(issues) == 1` 均失败（规则尚不存在）。

- [ ] **Step 3: 注册规则名**

`src/planning_control_plane/model.py`，在 `IDEA_RULE_NAMES` 的 `"idea-unknown-field",` 之后加：

```python
        "idea-unknown-field",
        "idea-filename-mismatch",
```

- [ ] **Step 4: 实现规则**

`src/planning_control_plane/validator.py` 的 `_check_ideas` 内，紧跟 `idea-id-collides-with-node` 那段之后加：

```python
        # INT-D11: IDEA-D6 fixes the file name as <id>.yaml, but nothing
        # guarded it — a cross-session rename drifts silently. WARNING, not
        # ERROR, and deliberately mirrors idea-id-collides-with-node: the id
        # is the identity (IDEA-D14), the file name is only an index (D6).
        # The loader reads top-level *.yaml only, so there is no .yml branch.
        if idea.source_file:
            stem = idea.source_file.rsplit("/", 1)[-1]
            if stem.endswith(".yaml"):
                stem = stem[: -len(".yaml")]
            if stem != idea_id:
                issues.append(
                    idea_issue(
                        Severity.WARNING,
                        "idea-filename-mismatch",
                        f"file name does not match the id; rename to '{idea_id}.yaml'",
                        idea_id,
                        idea_id,
                    )
                )
```

- [ ] **Step 5: 更新闭集 pin 测试**

`tests/test_ideas.py` 的 `test_idea_rule_names_form_the_documented_closed_set`（约 `:36-50`）：注释里的 `exactly these 18 rule names` 改为 `19`，集合里加一项：

```python
def test_idea_rule_names_form_the_documented_closed_set():
    # Spec §58.1 + INT-D11: exactly these 19 rule names identify the idea
    # layer (IDEA-D59 build gate, IDEA-D64 message prefix). Guards drift.
    assert IDEA_RULE_NAMES == frozenset(
        {
            "invalid-idea-file", "invalid-idea", "missing-idea-title",
            "invalid-idea-field", "invalid-idea-source", "invalid-idea-outcome",
            "invalid-idea-id", "duplicate-idea-id", "ignored-idea-file",
            "invalid-idea-status", "missing-idea-relates-target",
            "promoted-without-outcome", "missing-outcome-target",
            "outcome-without-promotion", "idea-source-escapes-repo",
            "idea-source-missing", "idea-id-collides-with-node",
            "idea-unknown-field", "idea-filename-mismatch",
        }
    )
```

- [ ] **Step 6: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_idea_filename.py tests/test_ideas.py -q`
Expected: PASS。

- [ ] **Step 7: 跑全量测试**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 全绿。demo 仓库没有 `ideas/` 目录（已核实），新 WARNING 不会打到 demo 与 HTML 快照测试。

- [ ] **Step 8: 提交**

```bash
git add src/planning_control_plane/model.py src/planning_control_plane/validator.py tests/test_idea_filename.py tests/test_ideas.py
git commit -m "feat(validator): warn when an idea file name does not match its id (INT-D11)"
```

---

## Task 5: `pcp ideas` next-free-id 尾行（INT-D12、D18）

**Files:**
- Modify: `src/planning_control_plane/cli.py`（`_HIDDEN_IDEA_RULES` 附近加正则常量与 `_next_free_idea_id`；`cmd_ideas` 末尾加尾行）
- Modify: `tests/test_ideas.py`（11 处既有断言，清单见 Step 5）
- Test: `tests/test_ideas_next_id.py`（新建）

**Interfaces:**
- Consumes: `Project.planning_dir() -> Path`（`model.py:427`）、`loader.IDEAS_DIR == "ideas"`（`loader.py:45`）、`re`（`cli.py` 已导入）
- Produces: `cli._next_free_idea_id(project: Project) -> str`（返回形如 `IDEA-0008`）；`pcp ideas` stdout 末行 `next free id: <id>`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_ideas_next_id.py`：

```python
"""The next-free-id hint on pcp ideas (spec INT-D12, INT-D18)."""

TAIL = "next free id: "


def _tail(out: str) -> str:
    return out.splitlines()[-1]


def test_missing_ideas_directory_starts_at_one(make_project, tmp_path, cli):
    """pcp init does not create ideas/, so this is a new project's default."""
    _project, root = make_project(tmp_path)
    code, out, err = cli("-p", str(root), "ideas")
    assert (code, err) == (0, "")
    assert _tail(out) == TAIL + "IDEA-0001"


def test_empty_ideas_directory_starts_at_one(make_project, tmp_path, cli):
    _project, root = make_project(tmp_path)
    (root / ".planning" / "ideas").mkdir()
    code, out, _err = cli("-p", str(root), "ideas")
    assert code == 0
    assert _tail(out) == TAIL + "IDEA-0001"


def test_highest_number_plus_one(make_project, tmp_path, cli):
    _project, root = make_project(
        tmp_path,
        raw_files={"ideas/IDEA-0007.yaml": "id: IDEA-0007\ntitle: T\nstatus: OPEN\n"},
    )
    code, out, _err = cli("-p", str(root), "ideas")
    assert code == 0
    assert _tail(out) == TAIL + "IDEA-0008"


def test_unparsable_file_still_reserves_its_number(make_project, tmp_path, cli):
    """INT-D18: the data-safety clause. A file that failed to load never
    reaches project.ideas; suggesting its id would tell the reader — usually
    an agent — to overwrite a file the user has not fixed yet."""
    _project, root = make_project(tmp_path, raw_files={"ideas/IDEA-0008.yaml": "id: [unclosed\n"})
    code, out, _err = cli("-p", str(root), "ideas")
    assert code == 0
    assert _tail(out) == TAIL + "IDEA-0009"
    assert (root / ".planning" / "ideas" / "IDEA-0008.yaml").exists()


def test_yml_file_also_reserves_its_number(make_project, tmp_path, cli):
    """A top-level .yml is not loaded (ignored-idea-file) but does occupy the name."""
    _project, root = make_project(
        tmp_path,
        raw_files={"ideas/IDEA-0003.yml": "id: IDEA-0003\ntitle: T\nstatus: OPEN\n"},
    )
    code, out, _err = cli("-p", str(root), "ideas")
    assert code == 0
    assert _tail(out) == TAIL + "IDEA-0004"


def test_subdirectory_files_do_not_reserve_numbers(make_project, tmp_path, cli):
    """Only top-level names can collide with a new top-level file."""
    _project, root = make_project(
        tmp_path,
        raw_files={"ideas/archive/IDEA-0100.yaml": "id: IDEA-0100\ntitle: T\nstatus: OPEN\n"},
    )
    code, out, _err = cli("-p", str(root), "ideas")
    assert code == 0
    assert _tail(out) == TAIL + "IDEA-0001"


def test_non_idea_ids_do_not_participate(make_project, tmp_path, cli):
    """INT-D18: anchored match — a substring match would count MY-IDEA-0042-x."""
    _project, root = make_project(
        tmp_path,
        raw_files={"ideas/MY-IDEA-0042-x.yaml": "id: MY-IDEA-0042-x\ntitle: T\nstatus: OPEN\n"},
    )
    code, out, _err = cli("-p", str(root), "ideas")
    assert code == 0
    assert _tail(out) == TAIL + "IDEA-0001"


def test_unpadded_ids_are_normalized(make_project, tmp_path, cli):
    """IDEA-7 counts as 7; the suggestion is always four-digit padded."""
    _project, root = make_project(
        tmp_path,
        raw_files={"ideas/IDEA-7.yaml": "id: IDEA-7\ntitle: T\nstatus: OPEN\n"},
    )
    code, out, _err = cli("-p", str(root), "ideas")
    assert code == 0
    assert _tail(out) == TAIL + "IDEA-0008"


def test_numbers_above_the_padding_width_grow(make_project, tmp_path, cli):
    _project, root = make_project(
        tmp_path,
        raw_files={"ideas/IDEA-9999.yaml": "id: IDEA-9999\ntitle: T\nstatus: OPEN\n"},
    )
    code, out, _err = cli("-p", str(root), "ideas")
    assert code == 0
    assert _tail(out) == TAIL + "IDEA-10000"


def test_hint_is_independent_of_filters(make_project, tmp_path, cli):
    """INT-D18 point 4: filtering is a display choice, not a data question."""
    raw = {
        "ideas/IDEA-0001.yaml": "id: IDEA-0001\ntitle: T\nstatus: OPEN\nrelates_to: [P1]\n",
        "ideas/IDEA-0002.yaml": "id: IDEA-0002\ntitle: T\nstatus: DISCARDED\n",
    }
    _project, root = make_project(
        tmp_path,
        node_dicts=[{"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE"}],
        raw_files=raw,
    )
    for argv in (
        ("ideas",),
        ("ideas", "--status", "OPEN"),
        ("ideas", "--status", "DISCARDED"),
        ("ideas", "--for", "P1"),
    ):
        code, out, _err = cli("-p", str(root), *argv)
        assert code == 0
        assert _tail(out) == TAIL + "IDEA-0003", argv


def test_hint_comes_after_the_hidden_records_note(make_project, tmp_path, cli):
    """INT-D12: the hint closes the output; the note keeps its place."""
    raw = {
        "ideas/IDEA-0001.yaml": "id: IDEA-0001\ntitle: First\nstatus: OPEN\n",
        "ideas/dup.yaml": "id: IDEA-0001\ntitle: Second\nstatus: OPEN\n",
    }
    _project, root = make_project(tmp_path, raw_files=raw)
    code, out, _err = cli("-p", str(root), "ideas")
    assert code == 0
    lines = out.splitlines()
    assert lines[-2].startswith("note: 1 idea record(s) not shown")
    assert lines[-1] == TAIL + "IDEA-0002"


def test_hint_shows_on_the_all_files_broken_path(make_project, tmp_path, cli):
    """INT-D12 boundary: 'could not be loaded' is an exit-0 listing path, not
    a failure path — and it is exactly where the disk-name rule pays off."""
    _project, root = make_project(tmp_path, raw_files={"ideas/IDEA-0004.yaml": "id: [unclosed\n"})
    code, out, err = cli("-p", str(root), "ideas")
    assert (code, err) == (0, "")
    assert out.splitlines()[0] == "idea files exist but could not be loaded; run 'pcp validate'"
    assert _tail(out) == TAIL + "IDEA-0005"


def test_no_hint_when_the_project_fails_to_load(cli, tmp_path):
    """Load failure returns EXIT_USAGE before any listing output."""
    bare = tmp_path / "no-planning"
    bare.mkdir()
    code, out, _err = cli("-p", str(bare), "ideas")
    assert code == 2
    assert TAIL not in out


def test_no_hint_on_usage_error(make_project, tmp_path, cli):
    _project, root = make_project(tmp_path)
    code, out, _err = cli("-p", str(root), "ideas", "--subtree")
    assert code == 2
    assert TAIL not in out
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_ideas_next_id.py -q`
Expected: FAIL —— 尾行不存在，`_tail(out)` 返回列表行或空态提示。

- [ ] **Step 3: 实现编号口径**

`src/planning_control_plane/cli.py`，在 `_HIDDEN_IDEA_RULES`（约 `:553`）之后加：

```python
#: Ids that participate in the next-free-id hint (spec INT-D18). Anchored on
#: purpose: a substring match would count a legitimate id like MY-IDEA-0042-x.
_IDEA_NUMBER_RE = re.compile(r"^IDEA-(\d+)$")


def _next_free_idea_id(project: Project) -> str:
    """Suggest the next unused ``IDEA-<NNNN>`` id (spec INT-D18).

    The candidate set is the loaded idea ids UNION the top-level file names
    under ``.planning/ideas/`` — including the ``.yml`` ones the loader
    refuses to read. A file that failed to parse never reaches
    ``project.ideas``, and this line's reader is usually an agent acting on
    it: suggesting an id whose file already exists would tell it to
    overwrite work the user has not repaired yet. Only top-level names are
    considered; a file in a subdirectory cannot collide with a new one.
    """
    candidates = set(project.ideas)
    ideas_dir = project.planning_dir() / loader.IDEAS_DIR
    if ideas_dir.is_dir():
        for pattern in ("*.yaml", "*.yml"):
            for entry in ideas_dir.glob(pattern):
                if entry.is_file():
                    candidates.add(entry.stem)

    highest = 0
    for candidate in candidates:
        match = _IDEA_NUMBER_RE.match(candidate)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"IDEA-{highest + 1:04d}"
```

- [ ] **Step 4: 加尾行**

`cmd_ideas` 结尾，把 `if hidden:` 块之后的 `return EXIT_OK` 改成：

```python
    if hidden:
        print(
            f"note: {hidden} idea record(s) not shown (broken or duplicate "
            "entry, or invalid status); run 'pcp validate'"
        )
    # INT-D12: the closing line of every listing path that reached this far
    # (including the all-files-broken one, which also exits 0). Advisory
    # only — it hands the next cross-session capture a ready-made id.
    print(f"next free id: {_next_free_idea_id(project)}")
    return EXIT_OK
```

- [ ] **Step 5: 更新既有断言（实测清单，11 处）**

以下是**唯一允许修改**的既有断言。每处只加尾行相关的调整，语义不动。

行号基准：当前 `main` 状态。Task 4 对本文件的净增行数为 0（闭集 pin 的注释与集合体行数不变），所以行号在本任务执行时仍然成立；若实际对不上，**用断言文本定位，不要照行号盲改**。


| 行 | 现状 | 改法 |
| --- | --- | --- |
| `:414` | `assert out.strip() == "no ideas yet; add .planning/ideas/<id>.yaml"` | 改为 `lines = out.splitlines()` + `assert lines[0] == "no ideas yet; add .planning/ideas/<id>.yaml"` + `assert lines[-1] == "next free id: IDEA-0001"` |
| `:434` | `assert len(lines) == 6` | `assert len(lines) == 7` + 追加 `assert lines[6].startswith("next free id: ")` |
| `:463` | `assert out.rstrip().endswith("via: P1")` | `assert out.splitlines()[-2].endswith("via: P1")` |
| `:484` | `assert out.strip() == "no ideas match the requested status filter"` | 同 `:414` 模式（首行全等 + 尾行断言；此 fixture 的尾行是 `IDEA-0001`，因为 id `IDEA-A` 不匹配 `^IDEA-(\d+)$`） |
| `:565` | `assert len(lines) == 2` | `assert len(lines) == 3` |
| `:583` | `assert out.rstrip().endswith("via: P2")` | `assert out.splitlines()[-2].endswith("via: P2")` |
| `:591` | `assert out.rstrip().endswith("via: P2-A")` | `assert out.splitlines()[-2].endswith("via: P2-A")` |
| `:600` | `assert out.rstrip().endswith("via: P2, P2-A")` | `assert out.splitlines()[-2].endswith("via: P2, P2-A")` |
| `:608` | `assert out.strip() == "no matching ideas for node 'P1'"` | 同 `:414` 模式（尾行是 `IDEA-0002`：fixture 里有 `IDEA-1`） |
| `:622` | `assert out.rstrip().endswith("via: P2-A")` | `assert out.splitlines()[-2].endswith("via: P2-A")` |
| `:643` + `:647` | `ids = [line.split()[0] for line in out.splitlines() if not line.startswith("==")]` | 过滤器加一条：`if not line.startswith("==") and not line.startswith("next free id:")`（两行都要改；`:647` 在 `:643` 之后同函数内） |

**不得修改**的三处（实测确认不受尾行影响）：`:505`（`splitlines()[0]` 首行式）、`:526`（`splitlines()[1]` 前几行式）、`:553`（`startswith("==")` 表头过滤式）。

- [ ] **Step 6: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_ideas_next_id.py tests/test_ideas.py -q`
Expected: PASS。

- [ ] **Step 7: 跑全量测试**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: 全绿。若 `tests/test_ideas.py` 之外的文件出现失败，说明尾行位置错了（不是最后一行），回看 INT-D12。

- [ ] **Step 8: 提交**

```bash
git add src/planning_control_plane/cli.py tests/test_ideas_next_id.py tests/test_ideas.py
git commit -m "feat(ideas): print the next free idea id, reserving on-disk names (INT-D12, INT-D18)"
```

---

## Task 6: 两份 README（验收 #7）

**Files:**
- Modify: `README.md`（CLI 表 `:161-171`；想法层小节）
- Modify: `README.zh-CN.md`（CLI 表 `:147-157`；想法层小节）

**Interfaces:**
- Consumes: Task 1–5 的全部产出（命令名、规则名、尾行文案、SKILL.md 路径）
- Produces: 无代码符号

- [ ] **Step 1: 英文 README 加命令行**

`README.md` 的 CLI 表格，在 `pcp init` 行之后插入：

```markdown
| `pcp agents` | Print a paste-ready AGENTS.md section teaching AI harnesses this repository's PCP workflow. Read-only — append it with `pcp agents >> AGENTS.md` |
```

并把 `pcp ideas` 行末尾补一句：`The last line prints the next free idea id.`

- [ ] **Step 2: 英文 README 加 Skill 小节**

在 `## Idea Layer` 之前插入：

```markdown
## AI Harness Integration

Two assets teach an AI coding harness when to reach for `pcp`:

1. **AGENTS.md section** — `pcp agents >> AGENTS.md`, once per repository. It
   states the repository's own rules (document naming, the registration
   convention) and the session workflow.
2. **Skill** — [`integrations/skills/pcp/SKILL.md`](integrations/skills/pcp/SKILL.md)
   is the manual for the tool itself. Copy or symlink it into your harness's
   skills directory:

   ```bash
   mkdir -p ~/.claude/skills/pcp
   curl -fsSL https://raw.githubusercontent.com/LuneHaven/planning-control-plane/main/integrations/skills/pcp/SKILL.md \
     -o ~/.claude/skills/pcp/SKILL.md
   ```

   The skill ships with the repository, not with the Python package: it is a
   harness asset, not part of the PCP runtime.

The division is deliberate — repository rules live in AGENTS.md alone, the
command manual lives in SKILL.md alone, so the two cannot drift apart.
```

- [ ] **Step 3: 英文 README 想法层补两句**

在 `## Idea Layer` 小节末尾加：

```markdown
`pcp validate` warns (`idea-filename-mismatch`) when an idea file's name does
not match its `id` — the id is the identity, the file name is only an index,
so it is a WARNING and never blocks. The last line of `pcp ideas` prints the
next free `IDEA-<NNNN>`, computed from both loaded ids and the file names on
disk, so it never points at a file that already exists.
```

- [ ] **Step 4: 中文 README 同步三处**

`README.zh-CN.md` 的 CLI 表格 `pcp init` 行后插入：

```markdown
| `pcp agents` | 打印可直接粘贴的 AGENTS.md 段落，让 AI harness 知道本仓库的 PCP 工作流。只读——用 `pcp agents >> AGENTS.md` 自行追加 |
```

`pcp ideas` 行末补：`最后一行给出下一个可用的想法 id。`

在 `## 想法层` 之前插入：

```markdown
## AI Harness 集成

两个资产让 AI coding harness 在正确时机想起调用 `pcp`：

1. **AGENTS.md 段落**——每个仓库执行一次 `pcp agents >> AGENTS.md`。它写的是
   这个仓库自己的规矩（文档命名、登记约定）与 session 工作流。
2. **Skill**——[`integrations/skills/pcp/SKILL.md`](integrations/skills/pcp/SKILL.md)
   是工具本身的手册。复制或链接到 harness 的 skills 目录：

   ```bash
   mkdir -p ~/.claude/skills/pcp
   curl -fsSL https://raw.githubusercontent.com/LuneHaven/planning-control-plane/main/integrations/skills/pcp/SKILL.md \
     -o ~/.claude/skills/pcp/SKILL.md
   ```

   Skill 随仓库分发，不随 Python 包分发：它是 harness 资产，不是 PCP 运行时的
   一部分。

分工是有意的——仓库规矩只在 AGENTS.md，命令手册只在 SKILL.md，两处不会漂移。
```

`## 想法层` 小节末尾加：

```markdown
想法文件名与 `id` 不一致时，`pcp validate` 报 `idea-filename-mismatch`
WARNING——id 是身份权威，文件名只是索引便利，因此不阻断。`pcp ideas` 的最后
一行给出下一个可用的 `IDEA-<NNNN>`，编号同时参考已加载的 id 与磁盘上的文件名，
不会指向一个已经存在的文件。
```

- [ ] **Step 5: 校对**

Run: `grep -n "pcp agents" README.md README.zh-CN.md && grep -n "idea-filename-mismatch" README.md README.zh-CN.md && grep -n "SKILL.md" README.md README.zh-CN.md`
Expected: 两份文件各命中三项。

- [ ] **Step 6: 提交**

```bash
git add README.md README.zh-CN.md
git commit -m "docs: document pcp agents, the skill asset and idea filename hygiene"
```

---

## Task 7: 验收对照与收尾

**Files:** 无改动（只跑验证；若发现缺口，回到对应 Task 修复后再走本任务）

- [ ] **Step 1: 逐条跑 spec §5 验收**

```bash
# 验收 1：pcp agents 只读
git status --porcelain > /tmp/pcp-before.txt
.venv/bin/python -m planning_control_plane.cli agents | head -3
git status --porcelain > /tmp/pcp-after.txt
diff /tmp/pcp-before.txt /tmp/pcp-after.txt && echo "验收1 只读: OK"
.venv/bin/python -m planning_control_plane.cli agents | tail -1   # 期望: <!-- pcp:agents end -->
```

注：`python -m planning_control_plane.cli` 可跑；若已 `pip install -e .`，等价用 `.venv/bin/pcp`。

- [ ] **Step 2: 验收 2–4（init 提示、skill 门禁、filename WARNING）**

```bash
.venv/bin/python -m pytest tests/test_agents.py tests/test_skill_asset.py tests/test_idea_filename.py -q
```
Expected: PASS。

- [ ] **Step 3: 验收 5（尾行八种状态）**

```bash
.venv/bin/python -m pytest tests/test_ideas_next_id.py -v
```
Expected: 14 个测试全 PASS，覆盖验收 #5 的每一条（目录不存在 / 空目录 / 最大值 +1 / 解析失败占位 / 非 IDEA 前缀 / 过滤无关 / 位置在 note 之后 / 加载失败不显示）。

- [ ] **Step 4: 验收 6（全量绿 + 豁免范围）**

```bash
.venv/bin/python -m pytest tests/ -q
git diff --stat $(git merge-base HEAD main) -- tests/test_ideas.py
```
Expected: 全量绿；`tests/test_ideas.py` 的改动只涉及 Task 4 的闭集 pin 与 Task 5 清单的 11 处。

- [ ] **Step 5: 投影层无 drift**

```bash
.venv/bin/python -m planning_control_plane.cli -p examples/demo-project build --check
.venv/bin/python -m planning_control_plane.cli -p examples/demo-project-zh build --check
```
Expected: 退出码 0。本计划不碰 generator / templates，demo 也没有 `ideas/` 目录，投影应当零变化。

- [ ] **Step 6: 命令面自检**

```bash
.venv/bin/python -m planning_control_plane.cli --help | grep -A 12 "COMMAND"
```
Expected: 九条命令齐全，`agents` 一行含 "AGENTS.md"。

- [ ] **Step 7: 提交（若前面步骤产生修复）**

```bash
git add -A && git commit -m "test(harness): verify the INT acceptance checklist end to end"
```

若无改动则跳过本步。

---

## Self-Review

**1. spec 覆盖**

| spec 条款 | 落点 |
| --- | --- |
| INT-D1（只读、写入面） | Task 1 Step 4 + `test_agents_writes_nothing` |
| INT-D2（带版本标记） | Task 1 Step 3 常量 + `test_agents_prints_a_marker_delimited_block` |
| INT-D3（七条内容，含 `relates_to`、收窄的命名建议） | Task 1 Step 3 + `test_agents_covers_every_int_d3_point` / `test_agents_naming_advice_excludes_specs` |
| INT-D4（静态模板） | Task 1 Step 3 常量无插值 + `test_agents_works_without_a_planning_directory` |
| INT-D5（退出码 0、纯文本） | Task 1 Step 4 + 各测试的 `(code, err) == (0, "")` |
| INT-D6（资产位置、不进包） | Task 3 Step 3 + `test_skill_asset_exists` |
| INT-D7（内容分工、九条命令） | Task 3 Step 3 + `test_skill_defers_repository_rules_to_agents_md` |
| INT-D8（description 场景） | `test_skill_frontmatter_covers_the_trigger_scenarios` |
| INT-D9（英文、不进 i18n） | Global Constraints + 资产全英文 |
| INT-D10 / D11（新 WARNING） | Task 4 全部 |
| INT-D12（尾行、位置、豁免） | Task 5 Step 4 + Step 5 清单 + `test_hint_comes_after_the_hidden_records_note` / `test_hint_shows_on_the_all_files_broken_path` |
| INT-D13（影响面） | File Structure 表（含偏差 #2 的 `model.py`） |
| INT-D14（init 提示） | Task 2 全部 |
| INT-D15（一致性门禁） | Task 3 的两条 `test_skill_*_command` |
| INT-D16（分发口径） | Task 6 Step 2/4 的 raw URL 小节 |
| INT-D17（help 措辞） | Task 1 Step 5 + `test_agents_help_says_it_prints_an_agents_md_snippet` |
| INT-D18（编号口径四点） | Task 5 Step 3 + `tests/test_ideas_next_id.py` 九个编号测试 |
| 验收 1–7 | Task 7 Step 1–6 |

无遗漏条款。

**2. 占位符扫描**：无 TBD / TODO / "类似 Task N" / "适当处理错误"。每个代码步骤都给出可直接粘贴的完整代码，每处既有断言改法都给出行号与目标写法。

**3. 类型一致性**：`_next_free_idea_id(project: Project) -> str` 在 Task 5 定义并只在 `cmd_ideas` 调用；`_IDEA_NUMBER_RE` 同任务内定义使用；`_AGENTS_SNIPPET` / `cmd_agents` 在 Task 1 定义，Task 2 只依赖子命令名 `"agents"`，Task 3 的门禁通过 `_build_parser()` 间接依赖同一名字；规则名字符串 `"idea-filename-mismatch"` 在 `model.py`、`validator.py`、两个测试文件与 README 中拼写一致。
