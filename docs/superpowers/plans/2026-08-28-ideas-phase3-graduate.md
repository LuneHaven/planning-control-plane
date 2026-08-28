# PCP IDEA 子系统 · 阶段 3（毕业桥：`pcp graduate`）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 spec §55/§62.3 交付阶段 3 的已命名扩展点 `pcp graduate`：把毕业桥从两文件手工编辑升级为一条命令（状态翻转 PROMOTED + `outcome` 接线 + 论据转录进 `evidence_sources`），并以 spec R4 修订与验收记录完成想法层的阶段 3 收尾。

**Architecture:** 全部源码改动落在 `cli.py`——三个行级 YAML 手术函数（沿用 `pcp focus` 的行级编辑先例，保作者注释/CRLF）+ `cmd_graduate`（拒绝判定全部先于首个字节写入；两文件写完后重新加载真实文件验证，失败恢复两个原始文本）。引擎（model / loader / validator / generator / i18n / templates / context / graph）零改动，因此不变量 §59.1/2/3/5 与阶段 2 口径的不变量 4 无成本成立。

**Tech Stack:** Python 3.11+ 标准库 + PyYAML（均为既有依赖）；pytest。无新依赖。

**Spec:** `docs/superpowers/specs/ideas-spec-draft.zh-CN.md`（含 R1/R2/R3 修订；本计划落地其 §62.3 的 `pcp graduate`，`pcp close` 集成仍候 PLAN 世界，不在本计划范围）

**前置状态:** 阶段 2 已合并进 `main`（`1429b15`，fast-forward），334 测试全绿。本计划从 `main` 开新分支。

## Global Constraints

以下是 spec 的项目级要求，每个任务都隐含包含：

- **引擎零改动**：`model.py` / `loader.py` / `validator.py` / `generator.py` / `i18n.py` / `templates/` / `context.py` / `graph.py` 一行不动。阶段 3 的全部源码改动 = `cli.py` + 新测试文件。Task 6 会物理验证这一点。
- **IDEA-D34 转录语义**：把想法两个论据槽中带 `ref` 的条目复制进目标节点的 `evidence_sources`——内容复制，不是结构链接，节点侧零字段。已在节点上的 ref 跳过（去重），顺序保持想法内的出现顺序。
- **IDEA-D35 原子性（三段式）**：全部拒绝判定（未知 id、拒绝状态、内联节点、flow 写法、多行 note）先于首个字节写入；两文件写完后重新加载真实文件验证（PROMOTED + `outcome.node` + 证据已入列），验证失败恢复两个原始文本；文件系统中途崩溃窗口仍存在（不劣于手工流程，由 git 承载）。
- **行级手术契约**：只替换目标键块，其余字节原样；作者注释与 CRLF 保留（`pcp focus` 先例，`cli.py:393-426` 的 newline="" 读写与验证回滚模式）。被替换键块内紧随的空行会被消费——YAML 合法性与其余内容不受影响（docstring 写明）。
- **接受的源状态**：OPEN 与 PARKED。拒绝 PROMOTED（§54.2：毕业后迭代必须新建想法文件经节点枢纽，不得重开终态）、DISCARDED（§53.2：复活先回 OPEN）、非受控枚举值（指向 `pcp validate`）。裁定理由记入 spec 附录 D.7 第 2 条。
- **CLI 输出**：英文纯文本、无颜色（既有惯例）；退出码协议 0（成功）/ 1（业务失败）/ 2（用法错误，argparse 自带）。
- **既有测试零修改**：只允许**新增** `tests/test_graduate.py`；不改任何既有测试文件。
- **写入面**：`pcp graduate` 成为与 `init` / `focus` 同级的第三条写命令；不做节点创建、不做 `--force`、不做 dry-run（YAGNI）。

---

## File Structure

| 文件 | 责任 | 任务 |
| --- | --- | --- |
| `src/planning_control_plane/cli.py` | 三个行级手术函数 + `cmd_graduate` + parser 接线 + 模块 docstring 命令清单 | Task 1–3 |
| `tests/test_graduate.py` | **新建**：阶段 3 全部测试 | Task 1–4 |
| `README.md` / `README.zh-CN.md` | CLI 表格行 + 「只有一座桥」段落提及 `pcp graduate` | Task 5 |
| `docs/superpowers/specs/ideas-spec-draft.zh-CN.md` | 状态行修正 + D34/D50/§62.1/§62.3 行内修订 + 附录 D.7（R4） | Task 6 |
| `docs/superpowers/plans/2026-08-28-ideas-phase3-graduate.md` | 本文件，追加执行记录 | Task 6 |

---

## 环境准备（一次性）

```bash
cd /home/asus/dev/planning-control-plane
source .venv/bin/activate
git status                       # 应为 clean
git checkout -b feat/ideas-phase3-graduate
python -m pytest                 # 基线：334 passed
```

**测试文件约定：** 阶段 3 的测试全部进 `tests/test_graduate.py`（新建）。fixture 来自 `tests/conftest.py`：`make_project(tmp_path, config_dict=, node_dicts=, roadmap_nodes=, raw_files=, repo_files=)` 返回 `(project, repo_root)`；`node_dicts` 的元组形式 `("P2-A5.yaml", "<raw yaml text>")` 用于精确控制文件排版（本阶段要断言注释与排版保留，必须用原文 fixture 而非 `yaml.safe_dump`）；`cli(*argv)` 原地运行 CLI 返回 `(exit_code, stdout, stderr)`。

---

### Task 1: 行级 YAML 手术函数

纯文本函数，不带 I/O。放进 `cli.py` 的 small helpers 区（`_set_current_focus` 之后、command handlers banner 之前，即当前 `cli.py:207` 与 `cli.py:210` 之间）。`cmd_focus` 是它们的唯一先例：`_set_current_focus`（`cli.py:151-207`）证明了这个仓库对"编辑作者 YAML"的既定答案就是行级手术。

**Files:**
- Modify: `src/planning_control_plane/cli.py`（`_set_current_focus` 之后插入三个函数）
- Test: `tests/test_graduate.py`（新建）

**Interfaces:**
- Consumes: 既有 `_yaml_scalar()`（`cli.py:110`）
- Produces:
  - `cli._top_level_key_span(lines: list[str], key: str) -> tuple[int, int] | None`
  - `cli._set_top_level_key(text: str, key: str, rendered_lines: list[str]) -> str`
  - `cli._append_to_top_level_list(text: str, key: str, items: list[str]) -> str`（flow 写法抛 `ValueError`）

- [x] **Step 1: 写失败测试**

新建 `tests/test_graduate.py`：

```python
"""Graduation bridge tests (spec §55/§62.3, appendix D.7).

`pcp graduate` is the idea layer's only write command: it flips the idea
to PROMOTED, wires outcome.node at an existing node, and transcribes the
idea's ref-carrying justification entries into the node's evidence_sources.
"""

from __future__ import annotations

import os

import pytest

from planning_control_plane import cli as cli_module


# ------------------------------------------------------- yaml surgery units


def test_set_top_level_key_replaces_the_value_line():
    text = "id: P1\ntitle: T\nstatus: OPEN\n"
    out = cli_module._set_top_level_key(text, "status", ["status: PROMOTED"])
    assert out == "id: P1\ntitle: T\nstatus: PROMOTED\n"


def test_set_top_level_key_replaces_a_multiline_block():
    text = "id: P1\noutcome:\n  node: OLD\n  note: old text\nlast_updated: 2026-01-01\n"
    out = cli_module._set_top_level_key(text, "outcome", ["outcome:", "  node: NEW"])
    assert out == "id: P1\noutcome:\n  node: NEW\nlast_updated: 2026-01-01\n"


def test_set_top_level_key_appends_a_missing_key():
    text = "id: P1\ntitle: T"
    out = cli_module._set_top_level_key(text, "status", ["status: PROMOTED"])
    assert out == "id: P1\ntitle: T\nstatus: PROMOTED\n"


def test_set_top_level_key_adopts_crlf():
    text = "id: P1\r\nstatus: OPEN\r\n"
    out = cli_module._set_top_level_key(text, "status", ["status: PROMOTED"])
    assert out == "id: P1\r\nstatus: PROMOTED\r\n"


def test_set_top_level_key_leaves_indented_same_name_keys_alone():
    """Only a column-0 `key:` is the target; an indented `status:` under
    another key is value data, never the top-level one."""
    text = "outer:\n  status: INNER\nstatus: OPEN\n"
    out = cli_module._set_top_level_key(text, "status", ["status: PROMOTED"])
    assert out == "outer:\n  status: INNER\nstatus: PROMOTED\n"


def test_append_to_top_level_list_appends_after_the_last_item():
    text = "id: P1\nevidence_sources:\n  - docs/a.md\n\nlast_updated: 2026-01-01\n"
    out = cli_module._append_to_top_level_list(text, "evidence_sources", ["docs/b.md"])
    assert out == (
        "id: P1\nevidence_sources:\n  - docs/a.md\n  - docs/b.md\n\nlast_updated: 2026-01-01\n"
    )


def test_append_to_top_level_list_creates_a_missing_key():
    text = "id: P1\ntitle: T\n"
    out = cli_module._append_to_top_level_list(text, "evidence_sources", ["docs/a.md"])
    assert out == "id: P1\ntitle: T\nevidence_sources:\n  - docs/a.md\n"


def test_append_to_top_level_list_refuses_flow_style():
    with pytest.raises(ValueError, match="block list style"):
        cli_module._append_to_top_level_list(
            "id: P1\nevidence_sources: [docs/a.md]\n", "evidence_sources", ["docs/b.md"]
        )
```

- [x] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_graduate.py -v`
Expected: FAIL —— `AttributeError: module 'planning_control_plane.cli' has no attribute '_set_top_level_key'`

- [x] **Step 3: 实现三个函数**

在 `cli.py` 的 `_set_current_focus` 之后（command handlers banner 之前）插入：

```python
def _default_eol(text: str) -> str:
    """The file's dominant line ending, adopted by every line we generate."""
    return "\r\n" if "\r\n" in text else "\n"


def _top_level_key_span(lines: list[str], key: str) -> tuple[int, int] | None:
    """Span ``[start, end)`` of a top-level ``key:`` block in *lines* (each
    kept with its ending): the key line plus every following line that is
    blank or indented (the key's value). ``None`` when the key is absent.

    Only a column-0 ``key:`` line matches: an indented ``status:`` under
    another key is value data, and a top-level comment line ends the block
    (comments belong to the file, not to the key). Duplicate keys cannot
    occur — the loader's ``_UniqueKeyLoader`` refuses them.
    """
    pattern = re.compile(rf"^{re.escape(key)}:(\s|#|$)")
    start = None
    for index, raw in enumerate(lines):
        body = raw.rstrip("\r\n")
        if body and not body[0].isspace() and pattern.match(body):
            start = index
            break
    if start is None:
        return None
    end = start + 1
    for index in range(start + 1, len(lines)):
        body = lines[index].rstrip("\r\n")
        if body and not body[0].isspace():
            break
        end = index + 1
    return start, end


def _set_top_level_key(text: str, key: str, rendered_lines: list[str]) -> str:
    """Replace a top-level ``key:`` block — or append it when absent — with
    *rendered_lines* (no endings yet; this function adds the file's dominant
    EOL). Every other byte of the file survives untouched, so author
    comments and layout live on (the ``pcp focus`` discipline).

    Replacing a span may consume blank lines that sit inside it (directly
    after the key): YAML validity and all other content are unaffected.
    """
    eol = _default_eol(text)
    block = [line + eol for line in rendered_lines]
    lines = text.splitlines(keepends=True)
    span = _top_level_key_span(lines, key)
    if span is None:
        if text and not text.endswith(("\n", "\r\n")):
            text += eol
        return text + "".join(block)
    start, end = span
    lines[start:end] = block
    return "".join(lines)


def _append_to_top_level_list(text: str, key: str, items: list[str]) -> str:
    """Append *items* to a top-level block list under *key*, creating the
    key when absent. The existing value must be a block (or null) list —
    a flow list (``key: [a, b]``) raises :class:`ValueError` so the caller
    can refuse before touching the file: appending to a flow list cannot
    be done as a line edit without guessing the author's formatting.

    New items adopt the indent of the first existing ``- `` entry (two
    spaces when the list is empty or null) and land after the last
    non-blank line of the block.
    """
    eol = _default_eol(text)
    lines = text.splitlines(keepends=True)
    span = _top_level_key_span(lines, key)
    if span is None:
        if text and not text.endswith(("\n", "\r\n")):
            text += eol
        new = [key + ":" + eol] + [f"  - {_yaml_scalar(item)}{eol}" for item in items]
        return text + "".join(new)
    start, end = span
    key_body = lines[start].rstrip("\r\n")
    value = key_body[len(key) + 1 :].strip()
    if value and not value.startswith("#"):
        raise ValueError(
            f"'{key}:' must use block list style (one '- item' per line) for "
            f"automatic transcription; this file has '{key_body.strip()}' — "
            "convert it to block style first"
        )
    insert_at = start
    for index in range(start, end):
        if lines[index].strip():
            insert_at = index + 1
    indent = "  "
    for index in range(start + 1, end):
        match = re.match(r"^(\s+)- ", lines[index].rstrip("\r\n"))
        if match:
            indent = match.group(1)
            break
    new = [f"{indent}- {_yaml_scalar(item)}{eol}" for item in items]
    lines[insert_at:insert_at] = new
    return "".join(lines)
```

- [x] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_graduate.py -v`
Expected: PASS（8 个用例）

- [x] **Step 5: 全量回归**

Run: `python -m pytest`
Expected: 342 passed（334 基线 + 8 新增）

- [x] **Step 6: Commit**

```bash
git add src/planning_control_plane/cli.py tests/test_graduate.py
git commit -m "feat(graduate): line-oriented YAML surgery helpers for author files"
```

---

### Task 2: `pcp graduate` 的解析与拒绝（首个字节写入之前）

命令契约的守门半边：参数接线 + 全部拒绝判定。这些路径绝不写文件——测试对每条拒绝断言源文件字节不变。

**Files:**
- Modify: `src/planning_control_plane/cli.py:7-9`（模块 docstring 命令清单）、`cli.py:564` 之后（`cmd_graduate`，插在 `cmd_ideas` 与 `cmd_build` 之间）、`cli.py:750` 之后（parser 接线，插在 `ideas_parser` 与 `build_parser` 之间）
- Test: `tests/test_graduate.py`（追加）

**Interfaces:**
- Consumes: `_load_project` / `_IDEA_STATUS_ORDER` / `loader.IDEAS_DIR` / `loader.NODES_DIR` / `PLANNING_DIR` / `IdeaStatus` / Task 1 的手术函数（Task 3 才调用）
- Produces: `cmd_graduate(args: argparse.Namespace) -> int`；`pcp graduate <idea-id> --to NODE [--note TEXT]`

- [x] **Step 1: 写失败测试**

追加到 `tests/test_graduate.py`：

```python
# ------------------------------------------------------------- fixtures


GRAD_NODE = """\
# pilot target
id: P2-A5
title: Pilot
type: INVESTIGATION
status: NOT_STARTED

objective: >
  Pilot the hypothesis in one domain.

evidence_sources:
  - docs/existing.md

last_updated: 2026-08-27
"""

GRAD_IDEA = """\
# captured thinking
id: IDEA-0007
title: Trend comparison view
status: OPEN

detail: >
  One paragraph, no structure required.

relates_to: [P2]
benchmark_sources:
  - ref: docs/bench.md
    note: Grafana time-compare
  - note: Stripe month-over-month
methodology_sources:
  - ref: docs/method.md

outcome: ~

created: 2026-08-27
last_updated: 2026-08-27
"""


def _graduate_project(make_project, tmp_path, idea_text=GRAD_IDEA, node_text=GRAD_NODE, name="repo"):
    """A one-idea project whose node file carries author comments, a folded
    scalar and an existing evidence entry — the shapes the surgery must
    preserve. repo_files make every ref resolvable for post-graduate
    validate runs."""
    room = tmp_path / name
    room.mkdir()
    return make_project(
        room,
        node_dicts=[
            ("P2-A5.yaml", node_text),
            ("P2.yaml", "id: P2\ntitle: P2\ntype: PHASE\nstatus: READY\n"),
        ],
        raw_files={"ideas/IDEA-0007.yaml": idea_text},
        repo_files={"docs/existing.md": "x", "docs/bench.md": "b", "docs/method.md": "m"},
    )


# --------------------------------------------- resolution and refusals


def test_graduate_requires_to(make_project, tmp_path, cli, capsys):
    """argparse enforces the required flag itself and exits before any
    handler runs (usage error → exit 2). The `cli` fixture does not catch
    SystemExit, so this one asserts the exit directly."""
    _project, root = _graduate_project(make_project, tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        cli("-p", str(root), "graduate", "IDEA-0007")
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "--to" in captured.err


def test_graduate_unknown_idea_says_so(make_project, tmp_path, cli):
    _project, root = _graduate_project(make_project, tmp_path)
    idea_file = root / ".planning" / "ideas" / "IDEA-0007.yaml"
    before = idea_file.read_text(encoding="utf-8")
    code, _out, err = cli("-p", str(root), "graduate", "IDEA-9999", "--to", "P2-A5")
    assert code == 1
    assert "unknown idea 'IDEA-9999'" in err
    assert "pcp ideas" in err
    assert idea_file.read_text(encoding="utf-8") == before


def test_graduate_node_id_gets_an_idea_layer_hint(make_project, tmp_path, cli):
    """IDEA-D15 lets idea and node ids collide; passing a node id where an
    idea id is expected is the natural mistake (mirrors _idea_hint)."""
    _project, root = _graduate_project(make_project, tmp_path)
    code, _out, err = cli("-p", str(root), "graduate", "P2", "--to", "P2-A5")
    assert code == 1
    assert "'P2' is a node id" in err


def test_graduate_refuses_an_already_promoted_idea(make_project, tmp_path, cli):
    raw = GRAD_IDEA.replace("status: OPEN", "status: PROMOTED")
    _project, root = _graduate_project(make_project, tmp_path, idea_text=raw)
    code, _out, err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 1
    assert "already graduated" in err
    assert (root / ".planning" / "ideas" / "IDEA-0007.yaml").read_text(encoding="utf-8") == raw


def test_graduate_refuses_a_discarded_idea(make_project, tmp_path, cli):
    raw = GRAD_IDEA.replace("status: OPEN", "status: DISCARDED")
    _project, root = _graduate_project(make_project, tmp_path, idea_text=raw)
    code, _out, err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 1
    assert "revive it to OPEN" in err


def test_graduate_refuses_an_invalid_status(make_project, tmp_path, cli):
    raw = GRAD_IDEA.replace("status: OPEN", "status: WISHLIST")
    _project, root = _graduate_project(make_project, tmp_path, idea_text=raw)
    code, _out, err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 1
    assert "invalid status 'WISHLIST'" in err


def test_graduate_unknown_target_node_says_so(make_project, tmp_path, cli):
    _project, root = _graduate_project(make_project, tmp_path)
    code, _out, err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "NOSUCH")
    assert code == 1
    assert "unknown node 'NOSUCH'" in err


def test_graduate_target_idea_id_gets_a_node_hint(make_project, tmp_path, cli):
    _project, root = _graduate_project(make_project, tmp_path)
    code, _out, err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "IDEA-0007")
    assert code == 1
    assert "'IDEA-0007' is an idea id" in err


def test_graduate_refuses_an_inline_roadmap_node(make_project, tmp_path, cli):
    """Transcription edits the node's own file; an inline roadmap node has
    no file of its own to edit."""
    room = tmp_path / "roadmap-repo"
    room.mkdir()
    _project, root = make_project(
        room,
        roadmap_nodes=[
            {"id": "R1", "title": "Inline", "type": "DISCUSSION", "status": "NOT_STARTED"}
        ],
        raw_files={"ideas/IDEA-0007.yaml": GRAD_IDEA},
    )
    code, _out, err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "R1")
    assert code == 1
    assert "standalone file" in err
```

- [x] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_graduate.py -k graduate -v`
Expected: FAIL —— `requires_to` 走到 `assert "--to" in captured.err` 失败（当前 argparse 报的是 `invalid choice: 'graduate'`，不含 `--to`）；其余 8 个用例表现为 `SystemExit: 2`（argparse 对未知子命令直接退出）——两种表现都算红

- [x] **Step 3: 实现 `cmd_graduate`（本任务只做到拒绝判定；写路径的 TODO 占位留待 Task 3 替换为真实实现）**

3a. 模块 docstring（`cli.py:7-9`）的命令清单加一项：

```python
Implemented commands (spec §4): ``init`` (§5), ``validate`` (§16/§17),
``status`` (§18), ``context`` (§20/§21), ``focus`` (§19), ``ideas``
(§60), ``graduate`` (spec IDEA §55/§62.3) and ``build`` / ``build --check``
(§22/§23).
```

3b. 在 `cmd_ideas` 与 `cmd_build` 之间插入：

```python
def cmd_graduate(args: argparse.Namespace) -> int:
    """``pcp graduate <idea-id> --to NODE [--note TEXT]`` — walk the
    graduation bridge (spec §55, §62.3).

    The idea layer's only write command. Sets ``status: PROMOTED`` and
    ``outcome`` in the idea file, and transcribes the idea's ``ref``-carrying
    justification entries into the target node's ``evidence_sources``
    (IDEA-D34 — a content copy, never a structural link). The node must
    already exist as its own file: PCP never authors planning semantics,
    so node creation stays with the author. Both edits are line-oriented
    so author comments and layout survive (the ``pcp focus`` discipline);
    every refusal happens before the first byte is written, and a failed
    post-write verification restores both original files (IDEA-D35).
    """
    project = _load_project(args)
    if project is None:
        return EXIT_USAGE

    idea = project.ideas.get(args.idea_id)
    if idea is None:
        hint = (
            f"; '{args.idea_id}' is a node id — graduate takes an idea id"
            if args.idea_id in project.nodes
            else "; run 'pcp ideas' to list idea ids"
        )
        print(f"error: unknown idea '{args.idea_id}'{hint}", file=sys.stderr)
        return EXIT_FAILURE

    if idea.status == IdeaStatus.PROMOTED.value:
        outcome_now = idea.outcome.node if idea.outcome else "-"
        print(
            f"error: idea '{idea.id}' is already graduated (outcome: {outcome_now}); "
            "post-graduation iteration starts a new idea file (spec §54.2), "
            "never a re-graduation",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    if idea.status == IdeaStatus.DISCARDED.value:
        print(
            f"error: idea '{idea.id}' is DISCARDED; revive it to OPEN first "
            "(spec §53.2), then graduate",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    if idea.status not in _IDEA_STATUS_ORDER:
        print(
            f"error: idea '{idea.id}' has invalid status '{idea.status}'; "
            "run 'pcp validate'",
            file=sys.stderr,
        )
        return EXIT_FAILURE

    node = project.nodes.get(args.node)
    if node is None:
        hint = (
            f"; '{args.node}' is an idea id — --to takes a node id"
            if args.node in project.ideas
            else ""
        )
        print(f"error: unknown node '{args.node}'{hint}", file=sys.stderr)
        return EXIT_FAILURE

    ideas_dir = project.planning_dir() / loader.IDEAS_DIR
    nodes_dir = project.planning_dir() / loader.NODES_DIR
    if idea.source_file is None or (project.root / idea.source_file).parent != ideas_dir:
        print(
            f"error: idea '{idea.id}' was not loaded from a file under "
            f"{PLANNING_DIR}/{loader.IDEAS_DIR}/",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    if node.source_file is None or (project.root / node.source_file).parent != nodes_dir:
        print(
            f"error: node '{node.id}' is not a standalone file under "
            f"{PLANNING_DIR}/{loader.NODES_DIR}/ (inline roadmap node); "
            "move it to its own file first",
            file=sys.stderr,
        )
        return EXIT_FAILURE

    if args.note and ("\n" in args.note or "\r" in args.note):
        print("error: --note must be a single line", file=sys.stderr)
        return EXIT_FAILURE

    # --- write path (Task 3) -------------------------------------------
    raise NotImplementedError("write path lands in Task 3")
```

3c. parser 接线：在 `ideas_parser.set_defaults(func=cmd_ideas)` 与 `build_parser = ...` 之间插入：

```python
    graduate_parser = subparsers.add_parser(
        "graduate",
        help="graduate an idea into a planning node (the idea-layer write command)",
        description=(
            "Set status PROMOTED and outcome in the idea file, and copy the "
            "idea's ref-carrying justification entries into the target "
            "node's evidence_sources. The node must already exist as its "
            "own file under .planning/nodes/ (PCP never authors planning "
            "semantics). Line-oriented edits preserve comments and layout; "
            "both files are restored if post-write verification fails."
        ),
    )
    graduate_parser.add_argument(
        "idea_id",
        help="idea id to graduate (see 'pcp ideas')",
    )
    graduate_parser.add_argument(
        "--to",
        dest="node",
        metavar="NODE",
        required=True,
        help="target node id (must exist as its own file under .planning/nodes/)",
    )
    graduate_parser.add_argument(
        "--note",
        default=None,
        help="optional outcome note (single line)",
    )
    graduate_parser.set_defaults(func=cmd_graduate)
```

- [x] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_graduate.py -k graduate -v`
Expected: 9 个用例全 PASS（拒绝路径不触碰写路径的 `NotImplementedError`）

- [x] **Step 5: 全量回归**

Run: `python -m pytest`
Expected: 351 passed（342 + 9）

- [x] **Step 6: Commit**

```bash
git add src/planning_control_plane/cli.py tests/test_graduate.py
git commit -m "feat(graduate): resolve and refuse before the first byte is written"
```

---

### Task 3: 写路径 —— 手术、转录、验证与回滚

**Files:**
- Modify: `src/planning_control_plane/cli.py`（`cmd_graduate` 尾部的 `NotImplementedError` 占位替换为完整写路径）
- Test: `tests/test_graduate.py`（追加）

**Interfaces:**
- Consumes: Task 1 的三个手术函数、`_yaml_scalar`、`loader.load_project`
- Produces: 无新公开符号

- [x] **Step 1: 写失败测试**

追加到 `tests/test_graduate.py`：

```python
# ------------------------------------------------------ the write path


def test_graduate_writes_both_files_and_preserves_author_text(make_project, tmp_path, cli):
    _project, root = _graduate_project(make_project, tmp_path)
    code, out, _err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 0
    assert "graduated: IDEA-0007 -> P2-A5 (OPEN -> PROMOTED)" in out

    idea_text = (root / ".planning" / "ideas" / "IDEA-0007.yaml").read_text(encoding="utf-8")
    assert "# captured thinking" in idea_text           # author comment survives
    assert "status: PROMOTED" in idea_text
    assert "outcome:\n  node: P2-A5" in idea_text
    assert "outcome: ~" not in idea_text
    assert "relates_to: [P2]" in idea_text              # untouched keys untouched

    node_text = (root / ".planning" / "nodes" / "P2-A5.yaml").read_text(encoding="utf-8")
    assert "# pilot target" in node_text
    assert "objective: >" in node_text
    assert node_text.count("  - docs/existing.md") == 1  # existing entry kept once
    assert "  - docs/bench.md" in node_text
    assert "  - docs/method.md" in node_text


def test_graduate_output_names_transcribed_refs_and_files(make_project, tmp_path, cli):
    _project, root = _graduate_project(make_project, tmp_path)
    code, out, _err = cli(
        "-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5",
        "--note", "pilot is the evidence",
    )
    assert code == 0
    assert "evidence transcribed into P2-A5: docs/bench.md, docs/method.md" in out
    assert "idea file: .planning/ideas/IDEA-0007.yaml" in out
    assert "node file: .planning/nodes/P2-A5.yaml" in out
    idea_text = (root / ".planning" / "ideas" / "IDEA-0007.yaml").read_text(encoding="utf-8")
    assert "  note: pilot is the evidence" in idea_text


def test_graduate_without_note_writes_no_note_line(make_project, tmp_path, cli):
    """The idea's own justification entries keep their note lines; what must
    stay absent is a note inside the outcome block (asserted on the
    reloaded model, not on raw text)."""
    _project, root = _graduate_project(make_project, tmp_path)
    code, _out, _err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 0
    from planning_control_plane.loader import load_project

    project = load_project(root)
    assert project.ideas["IDEA-0007"].outcome.note == ""


def test_graduate_dedupes_refs_already_on_the_node(make_project, tmp_path, cli):
    node_text = GRAD_NODE.replace(
        "  - docs/existing.md", "  - docs/existing.md\n  - docs/bench.md"
    )
    _project, root = _graduate_project(make_project, tmp_path, node_text=node_text)
    code, out, _err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 0
    node_new = (root / ".planning" / "nodes" / "P2-A5.yaml").read_text(encoding="utf-8")
    assert node_new.count("docs/bench.md") == 1
    assert "evidence transcribed into P2-A5: docs/method.md" in out
    assert "skipped 1 ref(s) already present" in out


def test_graduate_note_only_sources_leave_the_node_file_untouched(make_project, tmp_path, cli):
    raw = GRAD_IDEA.replace(
        "  - ref: docs/bench.md\n    note: Grafana time-compare\n",
        "  - note: Grafana time-compare\n",
    ).replace("  - ref: docs/method.md\n", "")
    _project, root = _graduate_project(make_project, tmp_path, idea_text=raw)
    node_file = root / ".planning" / "nodes" / "P2-A5.yaml"
    before = node_file.read_text(encoding="utf-8")
    code, out, _err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 0
    assert node_file.read_text(encoding="utf-8") == before
    assert "no evidence refs to transcribe" in out


def test_graduate_accepts_a_parked_idea(make_project, tmp_path, cli):
    raw = GRAD_IDEA.replace("status: OPEN", "status: PARKED")
    _project, root = _graduate_project(make_project, tmp_path, idea_text=raw)
    code, out, _err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 0
    assert "(PARKED -> PROMOTED)" in out


def test_graduate_result_validates_clean(make_project, tmp_path, cli):
    """The written state is the state the spec promises: PROMOTED with a
    reachable outcome — no ERROR, no outcome-without-promotion."""
    _project, root = _graduate_project(make_project, tmp_path)
    assert cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")[0] == 0
    code, out, _err = cli("-p", str(root), "validate")
    assert code == 0
    assert "IDEA-0007" not in out


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores file permissions")
def test_graduate_restores_files_when_a_write_fails(make_project, tmp_path, cli):
    """The idea file is written first; if the node write then fails, the
    idea file must go back to its original content (IDEA-D35)."""
    _project, root = _graduate_project(make_project, tmp_path)
    idea_file = root / ".planning" / "ideas" / "IDEA-0007.yaml"
    node_file = root / ".planning" / "nodes" / "P2-A5.yaml"
    idea_before = idea_file.read_text(encoding="utf-8")
    node_before = node_file.read_text(encoding="utf-8")
    os.chmod(node_file, 0o444)
    try:
        code, _out, err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
        assert code == 1
        assert "restored" in err
    finally:
        os.chmod(node_file, 0o644)
    assert idea_file.read_text(encoding="utf-8") == idea_before
    assert node_file.read_text(encoding="utf-8") == node_before


def test_graduate_restores_files_when_reverification_fails(make_project, tmp_path, cli, monkeypatch):
    """A reload that cannot even run counts as verification failure: both
    files go back to their originals and the command exits 1."""
    from planning_control_plane import loader as loader_module

    _project, root = _graduate_project(make_project, tmp_path)
    idea_file = root / ".planning" / "ideas" / "IDEA-0007.yaml"
    node_file = root / ".planning" / "nodes" / "P2-A5.yaml"
    idea_before = idea_file.read_text(encoding="utf-8")
    node_before = node_file.read_text(encoding="utf-8")

    real_load = loader_module.load_project
    calls = {"count": 0}

    def flaky_load(root_arg):
        calls["count"] += 1
        if calls["count"] > 1:
            raise loader_module.LoadError("simulated unreadable project")
        return real_load(root_arg)

    monkeypatch.setattr(loader_module, "load_load_placeholder", None)  # guard: never used
    monkeypatch.setattr(loader_module, "load_project", flaky_load)
    code, _out, err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 1
    assert "verification failed" in err
    assert idea_file.read_text(encoding="utf-8") == idea_before
    assert node_file.read_text(encoding="utf-8") == node_before
```

**注意：** 上面 `monkeypatch.setattr(loader_module, "load_load_placeholder", None)` 一行是转写失误，**删除该行**，只保留 `monkeypatch.setattr(loader_module, "load_project", flaky_load)`。计划的测试代码以此修正后为准。

- [x] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_graduate.py -k "writes_both or output_names or without_note or dedupes or note_only or parked or validates_clean or restores" -v`
Expected: FAIL —— 前七个用例撞上 `NotImplementedError`；两个 restores 用例同样

- [x] **Step 3: 实现写路径**

把 `cmd_graduate` 尾部的占位（注释行 + `raise NotImplementedError(...)`）替换为：

```python
    idea_path = project.root / idea.source_file
    node_path = project.root / node.source_file
    try:
        # newline="" on both ends: the edit must be line-oriented at the byte
        # level too, so CRLF files keep their original endings throughout.
        with idea_path.open("r", encoding="utf-8", newline="") as handle:
            idea_text = handle.read()
        with node_path.open("r", encoding="utf-8", newline="") as handle:
            node_text = handle.read()
    except OSError as exc:
        print(f"error: cannot read the source files: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    # IDEA-D34: transcribe every ref-carrying justification entry, in order
    # of appearance, skipping refs the node already carries (a content
    # copy, never a structural link — the node gains no idea knowledge).
    refs: list[str] = []
    for source in (*idea.benchmark_sources, *idea.methodology_sources):
        if source.ref and source.ref not in refs:
            refs.append(source.ref)
    new_refs = [ref for ref in refs if ref not in node.evidence_sources]

    outcome_lines = ["outcome:", f"  node: {_yaml_scalar(node.id)}"]
    if args.note:
        outcome_lines.append(f"  note: {_yaml_scalar(args.note)}")
    try:
        new_idea_text = _set_top_level_key(idea_text, "status", ["status: PROMOTED"])
        new_idea_text = _set_top_level_key(new_idea_text, "outcome", outcome_lines)
        new_node_text = (
            _append_to_top_level_list(node_text, "evidence_sources", new_refs)
            if new_refs
            else node_text
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    def _restore() -> None:
        for path, text in ((idea_path, idea_text), (node_path, node_text)):
            try:
                path.write_text(text, encoding="utf-8", newline="")
            except OSError:
                pass  # best-effort rollback; the error below still reports

    try:
        idea_path.write_text(new_idea_text, encoding="utf-8", newline="")
        node_path.write_text(new_node_text, encoding="utf-8", newline="")
    except OSError as exc:
        _restore()
        print(
            f"error: cannot write the graduation edits ({exc}); "
            "both files were restored to their previous content",
            file=sys.stderr,
        )
        return EXIT_FAILURE

    # Verify the written state by reloading the real files (IDEA-D35):
    # anything short of the promised state rolls both files back.
    try:
        reloaded = loader.load_project(project.root)
        check_idea = reloaded.ideas.get(idea.id)
        check_node = reloaded.nodes.get(node.id)
        ok = (
            check_idea is not None
            and check_idea.status == IdeaStatus.PROMOTED.value
            and check_idea.outcome is not None
            and check_idea.outcome.node == node.id
            and check_node is not None
            and all(ref in check_node.evidence_sources for ref in new_refs)
        )
    except loader.LoadError:
        ok = False
    if not ok:
        _restore()
        print(
            f"error: graduation verification failed for idea '{idea.id}'; "
            "both files were restored to their previous content — "
            "edit them manually",
            file=sys.stderr,
        )
        return EXIT_FAILURE

    skipped = len(refs) - len(new_refs)
    print(f"graduated: {idea.id} -> {node.id} ({idea.status} -> PROMOTED)")
    if new_refs:
        print(f"  evidence transcribed into {node.id}: " + ", ".join(new_refs))
    elif refs:
        print(
            f"  evidence already present in {node.id} "
            f"({len(refs)} ref(s), nothing to transcribe)"
        )
    else:
        print("  no evidence refs to transcribe (note-only or empty justification slots)")
    if skipped and new_refs:
        print(f"  skipped {skipped} ref(s) already present")
    print(f"  idea file: {idea.source_file}")
    if new_refs:
        print(f"  node file: {node.source_file}")
    return EXIT_OK
```

- [x] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_graduate.py -v`
Expected: PASS（26 个用例全绿 = Task 1 的 8 + Task 2 的 9 + 本任务的 9）

- [x] **Step 5: 全量回归**

Run: `python -m pytest`
Expected: 360 passed（351 + 9）

- [x] **Step 6: Commit**

```bash
git add src/planning_control_plane/cli.py tests/test_graduate.py
git commit -m "feat(graduate): atomic two-file graduation with evidence transcription"
```

---

### Task 4: 作者文件形状的边界

**Files:**
- Test: `tests/test_graduate.py`（追加；无需改源码——全部由 Task 1–3 的实现覆盖）

**Interfaces:** 无新接口；本任务是把手术契约的边角钉死。

- [x] **Step 1: 写失败测试**（先跑一遍确认现状；这些用例应当全绿——若红，说明 Task 1–3 的实现与契约不符，修实现而不是改测试）

追加到 `tests/test_graduate.py`（reload 断言用到的 `load_project` 就地导入）：

```python
# ------------------------------------------------- author file shapes


def test_graduate_appends_outcome_when_the_key_is_absent(make_project, tmp_path, cli):
    raw = GRAD_IDEA.replace("outcome: ~\n\n", "")
    assert "outcome" not in raw
    _project, root = _graduate_project(make_project, tmp_path, idea_text=raw)
    code, _out, _err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 0
    idea_text = (root / ".planning" / "ideas" / "IDEA-0007.yaml").read_text(encoding="utf-8")
    assert idea_text.count("outcome:") == 1
    assert "outcome:\n  node: P2-A5" in idea_text


def test_graduate_replaces_a_transition_state_outcome_block(make_project, tmp_path, cli):
    """OPEN + outcome already set is the legal transition state (IDEA-D38
    WARNING); graduation overwrites it instead of growing a second key."""
    raw = GRAD_IDEA.replace(
        "outcome: ~",
        "outcome:\n  node: P2\n  note: node built, status flip pending",
    )
    _project, root = _graduate_project(make_project, tmp_path, idea_text=raw)
    code, _out, _err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 0
    idea_text = (root / ".planning" / "ideas" / "IDEA-0007.yaml").read_text(encoding="utf-8")
    assert idea_text.count("outcome:") == 1
    assert "node: P2-A5" in idea_text
    assert "status flip pending" not in idea_text


def test_graduate_appends_status_when_the_key_is_absent(make_project, tmp_path, cli):
    """An idea relying on the OPEN default has no status line; graduation
    appends an explicit one (only absent keys fall back — same discipline
    as the loader)."""
    raw = GRAD_IDEA.replace("status: OPEN\n\n", "", 1)
    assert "\nstatus:" not in raw
    _project, root = _graduate_project(make_project, tmp_path, idea_text=raw)
    code, _out, _err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 0
    from planning_control_plane.loader import load_project

    project = load_project(root)
    assert project.ideas["IDEA-0007"].status == "PROMOTED"
    assert project.ideas["IDEA-0007"].outcome.node == "P2-A5"


def test_graduate_preserves_crlf_author_files(make_project, tmp_path, cli):
    _project, root = _graduate_project(make_project, tmp_path)
    idea_file = root / ".planning" / "ideas" / "IDEA-0007.yaml"
    node_file = root / ".planning" / "nodes" / "P2-A5.yaml"
    idea_file.write_bytes(GRAD_IDEA.replace("\n", "\r\n").encode("utf-8"))
    node_file.write_bytes(GRAD_NODE.replace("\n", "\r\n").encode("utf-8"))
    code, _out, _err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 0
    assert b"status: PROMOTED\r\n" in idea_file.read_bytes()
    assert b"  node: P2-A5\r\n" in idea_file.read_bytes()
    assert b"  - docs/bench.md\r\n" in node_file.read_bytes()


def test_graduate_note_must_be_a_single_line(make_project, tmp_path, cli):
    _project, root = _graduate_project(make_project, tmp_path)
    code, _out, err = cli(
        "-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5", "--note", "two\nlines"
    )
    assert code == 1
    assert "single line" in err
```

- [x] **Step 2: 运行**

Run: `python -m pytest tests/test_graduate.py -k "key_is_absent or outcome_block or crlf or single_line" -v`
Expected: PASS。若 `appends_outcome` 或 `appends_status` 红——检查 `_set_top_level_key` 的 append 分支是否在文件无尾换行时补了 EOL；若 `crlf` 红——检查 `_default_eol` 是否被两侧使用。

- [x] **Step 3: 全量回归**

Run: `python -m pytest`
Expected: 365 passed（360 + 5）

- [x] **Step 4: Commit**

```bash
git add tests/test_graduate.py
git commit -m "test(graduate): pin file-shape edges (absent keys, transition outcome, CRLF)"
```

---

### Task 5: README 双语更新

**Files:**
- Modify: `README.md`（CLI 表格 `pcp ideas` 行之后插入一行，约 `README.md:169`；「One bridge」bullet，约 `README.md:208-211`）
- Modify: `README.zh-CN.md`（CLI 表格 `pcp ideas` 行之后插入一行，约 `README.zh-CN.md:155`；「只有一座桥」bullet，`README.zh-CN.md:192-194`）

- [x] **Step 1: README.md 的 CLI 表格追加行**（紧跟 `pcp ideas` 行之后）

```markdown
| `pcp graduate IDEA --to NODE [--note TEXT]` | Graduate an idea: write `status: PROMOTED` + `outcome` into the idea file and copy its ref-carrying justification entries into the node's `evidence_sources` (comments preserved; the node must already exist; both files roll back on failure) |
```

- [x] **Step 2: README.md 的「One bridge」bullet** —— 把

```markdown
- **One bridge.** An idea enters the planning graph only by graduating:
  create the node, then point `outcome.node` at it. Nodes never reference
  ideas back, so reading the plan never drags in unfinished thinking.
```

替换为

```markdown
- **One bridge.** An idea enters the planning graph only by graduating:
  create the node, then point `outcome.node` at it — by hand, or with
  `pcp graduate IDEA-0007 --to P2-A5`, which also copies the idea's
  ref-carrying justification entries into the node's `evidence_sources`.
  Nodes never reference ideas back, so reading the plan never drags in
  unfinished thinking.
```

- [x] **Step 3: README.zh-CN.md 的 CLI 表格追加行**（紧跟 `pcp ideas` 行之后）

```markdown
| `pcp graduate IDEA --to NODE [--note TEXT]` | 毕业一个想法：向想法文件写入 `status: PROMOTED` 与 `outcome`，并把带 `ref` 的论据条目复制进节点的 `evidence_sources`（保留注释；节点须已存在；失败时两文件回滚） |
```

- [x] **Step 4: README.zh-CN.md 的「只有一座桥」bullet** —— 把

```markdown
- **只有一座桥。** 想法进入规划图的唯一途径是毕业：先建节点，再把
  `outcome.node` 指向它。节点永不反向引用想法，因此读计划不会牵扯到未完成的
  思考。
```

替换为

```markdown
- **只有一座桥。** 想法进入规划图的唯一途径是毕业：先建节点，再把
  `outcome.node` 指向它——手工编辑，或用 `pcp graduate IDEA-0007 --to P2-A5`，
  后者还会把想法中带 `ref` 的论据条目复制进节点的 `evidence_sources`。
  节点永不反向引用想法，因此读计划不会牵扯到未完成的思考。
```

- [x] **Step 5: 检查双语结构一致**

Run:
```bash
grep -c '^| `pcp' README.md README.zh-CN.md
```
Expected: 两个文件计数相同（各 +1）

- [x] **Step 6: 全量回归**

Run: `python -m pytest`
Expected: 365 passed（文档改动，测试数不变）

- [x] **Step 7: Commit**

```bash
git add README.md README.zh-CN.md
git commit -m "docs(graduate): document pcp graduate in both READMEs"
```

---

### Task 6: 阶段 3 验收 + spec R4 修订 + 执行记录

**Files:**
- Modify: `docs/superpowers/specs/ideas-spec-draft.zh-CN.md`
- Modify: `docs/superpowers/plans/2026-08-28-ideas-phase3-graduate.md`（本文件，追加执行记录）
- Test: 无新测试；本任务是端到端验收

- [x] **Step 1: 跑全量测试**

Run: `python -m pytest && python -m pytest --collect-only -q | tail -1`
Expected: 全绿，记录最终用例总数（预计 365）

- [x] **Step 2: 物理验证「引擎零改动」**

Run:
```bash
git diff --stat main -- src/ tests/
```
Expected: `src/` 下只有 `cli.py` 一个文件变更；`tests/` 下只有新建的 `test_graduate.py`。`model.py` / `loader.py` / `validator.py` / `generator.py` / `i18n.py` / `templates/` / `context.py` / `graph.py` 零改动——不变量 §59.1/2/3/5 与阶段 2 口径的不变量 4 由此自动成立（无想法项目的构建产物与阶段 2 收尾时逐字节相同）。

- [x] **Step 3: 手工端到端验收**

```bash
rm -rf /tmp/pcp-graduate-demo && cp -r examples/demo-project /tmp/pcp-graduate-demo
rm -rf /tmp/pcp-graduate-demo/.planning/dist
mkdir -p /tmp/pcp-graduate-demo/.planning/ideas
cat > /tmp/pcp-graduate-demo/.planning/ideas/IDEA-0007.yaml <<'EOF'
id: IDEA-0007
title: Add a trend comparison view to the dashboard
status: OPEN
detail: One paragraph, no structure required at capture time.
relates_to: [P2]
benchmark_sources:
  - ref: docs/rollout/inventory.md
    note: Grafana's time-compare panel shows the demand is stable
  - note: Stripe's month-over-month dashboard
methodology_sources:
  - ref: docs/notes/2026-08-15-sequencing-review.md
created: 2026-08-27
last_updated: 2026-08-27
EOF
cd /tmp/pcp-graduate-demo
python -m planning_control_plane.cli graduate IDEA-0007 --to P2-A4 --note "pilot is the evidence"
python -m planning_control_plane.cli validate
python -m planning_control_plane.cli build
```

逐条确认：
1. graduate 退出 0，输出含 `graduated: IDEA-0007 -> P2-A4 (OPEN -> PROMOTED)` 与转录行；
2. `P2-A4.yaml` 的 `evidence_sources` 多出两个 ref、原有条目与注释排版原样；
3. `IDEA-0007.yaml` 为 `status: PROMOTED` + `outcome` 块，作者文本原样；
4. validate 退出 0（无 `promoted-without-outcome`、无 `outcome-without-promotion`）；
5. build 后 `dist/ideas.html` 的 PROMOTED 组出现该想法，`outcome` 渲染为指向 `nodes/P2-A4.html` 的链接；
6. 节点页 `dist/nodes/P2-A4.html` 的 evidence 列表含新 ref，且页面无任何想法标记（IDEA-D55）。

- [x] **Step 4: spec 修订（R4）**

4a. 状态行（第 5 行）——把

```markdown
| 状态 | **草案（Draft，待评审）**——尚未生效，尚无任何实现 |
```

替换为

```markdown
| 状态 | **草案（Draft，待评审）**——尚未合并主 spec；阶段 1–3 已按本草案实现（计划与执行记录见 docs/superpowers/plans/），仅 §62.3 的 `pcp close` 集成仍候 PLAN 世界 V0.2 |
```

4b. 「修订」行（第 10 行）——在 `见附录 D.6。` 之后、`需求 ID 按新增顺序编号` 之前插入：

```markdown
R4：阶段 3（`pcp graduate`）的实施契约，见附录 D.7。
```

4c. IDEA-D34（§55.3）——把

```markdown
`evidence_sources`（机械动作，阶段 1 由手工完成；`pcp graduate` 为已命名未承诺
的扩展点，见 §62.3）
```

替换为

```markdown
`evidence_sources`（机械动作；阶段 1–2 手工完成，阶段 3 起由 `pcp graduate`
自动执行——转录仍是内容复制，节点侧零字段；见 §62.3 与附录 D.7）
```

4d. IDEA-D50（§60 开头）——把

```markdown
**IDEA-D50** 新增只读子命令（写入面维持极小：想法的创建/编辑/毕业均为手工编辑
YAML，与"文件即源、仅 init/focus 写文件"的既有哲学一致）：
```

替换为

```markdown
**IDEA-D50** 想法层子命令（写入面维持极小：`ideas` 只读；想法的创建/编辑为手工
编辑 YAML；毕业自阶段 3 起可由 `pcp graduate` 代写两处编辑——与 `init`/`focus`
同级的第三条写命令，见附录 D.7）：
```

4e. §62.1 阶段 3 行——把

```markdown
| 3（扩展点，命名但未承诺） | `pcp graduate`（原子毕业+转录）、`pcp close` 集成（时刻 B 制度化） | 与 V0.2 候选合流评审 |
```

替换为

```markdown
| 3（扩展点，原"命名但未承诺"；`graduate` 已于 R4 落地） | `pcp graduate`（原子毕业+转录）已交付；`pcp close` 集成（时刻 B 制度化）仍候 PLAN 世界 | graduate 验收见 R4；close 集成与 V0.2 候选合流评审 |
```

4f. §62.3 第一条——把

```markdown
- `pcp graduate`：毕业向导（两文件原子写 + 论据转录自动化）；
```

替换为

```markdown
- `pcp graduate`：毕业向导（两文件原子写 + 论据转录自动化）——阶段 3 已实现，
  落地契约见附录 D.7；
```

4g. 附录 D 末尾（D.6 之后）追加：

```markdown
### D.7 修订记录 R4（阶段 3 实施：`pcp graduate`）

| # | 改动 | 依据 |
| --- | --- | --- |
| 1 | `pcp graduate` v1 的契约：只接线**既有**目标节点（`--to NODE`），不代建节点 | 代建节点意味着代写规划语义（type/parent/objective/scope 均是作者决策，§55.1 的毕业形态选择权在作者）；保持写入面最小（IDEA-D50）。手动流程"先建节点、后登记出处"的顺序因此保留，其半途状态（节点已建、想法仍 OPEN）本就是 §55.4 认定的"无害不可见" |
| 2 | 接受的源状态为 OPEN 与 PARKED；拒绝 PROMOTED（§54.2：毕业后迭代必须新建想法文件，不得重开终态）与 DISCARDED（§53.2：复活先回 OPEN，新证据先落盘再毕业）；非受控枚举值拒绝并指向 `pcp validate` | §53.2 迁移表是规范动作而非校验规则（不设迁移校验），命令作为 spec 原生工具按规范动作执行；PARKED→PROMOTED 虽不在表内，但 PARKED 是未承诺状态，直接毕业等价于"分诊结论：现在做"，不抹除任何历史 |
| 3 | 写入方式为**行级 YAML 手术**（`_top_level_key_span` / `_set_top_level_key` / `_append_to_top_level_list`，均在 `cli.py`）：只替换目标键块，其余字节原样，作者注释与 CRLF 保留（沿用 `pcp focus` 先例）；`evidence_sources` 为 flow 写法（`[a, b]`）时**拒绝执行**并提示改为块写法 | 节点/想法文件是手工 YAML，任何整文件重写（yaml dump）都会摧毁注释与排版；flow 列表的机械追加无法保真，拒绝比猜更强 |
| 4 | 原子性实现为三段式：全部拒绝判定先于首个字节写入；两文件写完后**重新加载真实文件**验证（PROMOTED + `outcome.node` + 证据已入列），失败则恢复两个原始文本；文件系统中途崩溃窗口仍存在，不劣于手工流程 | IDEA-D35 只承诺消除"可检出的半途状态"：pre-write 拒绝消除 `missing-outcome-target` 与状态违规，verify+restore 消除"写坏文件"；跨文件崩溃窗口由 git 承载（数据是源，§37） |
| 5 | 转录目标必须是 `nodes/` 下的独立文件；`roadmap.yaml` 内联节点被拒绝（提示先移出） | 内联节点的 YAML 是列表中的一项，行级手术没有安全的锚点；且每节点一文件本就是仓库惯例（与 IDEA-D8 的同源理由：合并冲突线性） |
```

- [x] **Step 5: 追加本计划的执行记录**

在本文件末尾追加「执行记录」一节：实际测试数、计划内修正（若有）、评审驱动的增量（若有）、Step 1–3 的验收结果、提交清单——格式参照阶段 2 计划的执行记录小节。

- [x] **Step 6: 最终全量回归**

Run: `python -m pytest`
Expected: 全绿，与 Step 1 记录的总数一致

- [x] **Step 7: Commit**

```bash
git add docs/superpowers/specs/ideas-spec-draft.zh-CN.md \
        docs/superpowers/plans/2026-08-28-ideas-phase3-graduate.md
git commit -m "docs(ideas): record phase-3 acceptance and spec R4 amendments"
```

---

## Self-Review

**1. Spec 覆盖（阶段 3 范围 = §62.3 的 `pcp graduate`）**

| spec 条目 | 任务 |
| --- | --- |
| §62.3 `pcp graduate`：两文件原子写 | Task 1–3（手术 + 三段式原子性） |
| IDEA-D34 论据转录（带 `ref` 条目 → `evidence_sources`，内容复制） | Task 3（转录 + 去重 + note-only 不触碰节点文件） |
| IDEA-D35 原子性与失败模式（消除可检出的半途状态） | Task 2（前置拒绝）+ Task 3（验证回滚，两个 restores 用例） |
| §55.2/IDEA-D32 outcome 语义（node 必填 + 可选 note） | Task 3（outcome 块构建；`--note` 单行约束） |
| §53.2/IDEA-D24 状态迁移的规范动作（PROMOTED 禁重开、DISCARDED 先复活） | Task 2（状态拒绝三用例） |
| §54.2 毕业后迭代走新想法文件 | Task 2（PROMOTED 拒绝文案） |
| IDEA-D15 撞号提示（镜像 IDEA-D52 的 `_idea_hint`） | Task 2（node-id 与 idea-id 双向提示） |
| 不变量 §59.1/2/3/4/5 | Task 6 Step 2（引擎零改动物理验证——源码只动 `cli.py`，投影与引擎未触碰，不变量无成本成立） |
| §62.1 阶段 3 收尾记录 / R4 / 状态行修正 | Task 6 Step 4 |
| §62.1 阶段 2 交付「README en/zh 更新」的对应义务 | Task 5 |

**不在本计划范围**（前置对话已确认）：`pcp close` 集成与 `CANCELLED` 终态（IDEA-D43：PLAN 世界自身的 V0.2 候选，独立立项）；附录 D.4 的 `pcp validate` CI 裁定（触发条件是接 CI，阶段 3 不触发；`pcp graduate` 不改变 validate 的退出码协议）；节点创建向导（R4 第 1 条记录裁定）。

**2. 占位符扫描**

Task 2 Step 3 的 `raise NotImplementedError("write path lands in Task 3")` 是**刻意的任务间接缝**（TDD 红绿节奏），Task 3 Step 3 给出完整替换代码，不留悬空。Task 3 Step 1 测试代码中有一处已标注的转写失误（`load_load_placeholder` 行）及其修正指令——实现时以修正后为准。除此之外无 TBD / TODO / "类似 Task N"；所有代码步骤均给出完整代码。

**3. 类型一致性**

- `_top_level_key_span(lines: list[str], key: str) -> tuple[int, int] | None` 在 Task 1 定义，`_set_top_level_key` / `_append_to_top_level_list` 两处调用，签名一致。
- `_set_top_level_key(text, key, rendered_lines: list[str])` 的 `rendered_lines` 是**不带行尾**的行列表（Task 3 的 `["status: PROMOTED"]` 与 `outcome_lines` 均按此构造）；函数内部统一补 EOL。
- `cmd_graduate` 消费的 `--to` 经 `dest="node"` 落到 `args.node`，与 `--for` 的 `dest="node"` 先例一致（`cli.py:738-743`）。
- `idea.source_file` / `node.source_file` 是仓库相对路径（loader 以 `f"{PLANNING_DIR}/{IDEAS_DIR}/{name}"` 构造），`project.root / source_file` 得到磁盘路径——Task 2 的目录校验与 Task 3 的读写都基于它，无第二套路径来源。
- 测试引用的私有符号（`cli_module._set_top_level_key` 等）沿用阶段 2 计划访问 `cli_module._idea_sort_key` 的既有先例。

---

## 合并主 spec 待办清单（阶段 3 收尾后、合并评审时处理）

本计划落地后，想法层实现侧完整；spec 自身的"完全收尾"剩这一份清单：

1. **草案评审**：R1–R4 修订逐条过会（附录 D.1–D.7 是全部改动的依据记录）；
2. **章节重排**：§50–§62 续编进主 spec（主 spec 已引用至 §43）；
3. **需求 ID 重排**：`IDEA-D1`–`IDEA-D64` 统一重排，附录 B/C 的引用同步；
4. **语言对齐**：草案中文、标识符英文——合并时是否统一语言，spec 头部标注"待定"，需裁定；
5. **附录 D 归档策略**：修订记录（R1–R4）保留为附录还是融入正文，需裁定；
6. **D.4 裁定**：接 CI 之前必须裁定 `pcp validate` 的作用域旗标（R3 已记录建议方向），本次评审一并处理或显式延后；
7. **§62.3 剩余项改写**：`pcp close` 集成转交 PLAN 世界 V0.2 候选清单，本补章范围内不再有未交付项。

---

## 执行记录（2026-08-28，subagent-driven 执行后追加）

分支 `feat/ideas-phase3-graduate`（自 `main` = `1429b15` 切出），共 6 个实现提交 + 本执行记录提交（合计 7 个）。环境同阶段 1/2（uv venv，CPython 3.14.3 + pytest 9.1.1 + PyYAML 6.0.3）。

**实际测试数（按 Task 收官口径，`python -m pytest` 全绿）：**

- Task 1 后 342；Task 2 后 351；Task 3 后 361（计划 360 + 评审 Amendment A 回归 1）；Task 4 后 369（计划 366 + 评审 3）；Task 5（纯文档）与 Task 6 复核仍 369。终态分布：`tests/test_graduate.py` 35 + 既有 334。计划终估 365，实际 369——+4 来源：Task 3 评审 Amendment A 的 1 个回归测试（`test_graduate_note_that_looks_like_a_yaml_scalar_round_trips`）+ Task 4 评审的 3 个（CLI 级 flow 拒绝、4 空格缩进采纳、缺键端到端创建）。

**计划内修正（计划文本自身缺陷，以计划自己的注记或实测为准）：**

1. **`load_load_placeholder` 转写失误**（Task 3 测试清单）：计划第 764 行原文自带注记——`monkeypatch.setattr(loader_module, "load_load_placeholder", None)` 一行删除，只保留对 `load_project` 的 monkeypatch。
2. **Task 6 Step 3 heredoc 引用文件名**：`docs/notes/2026-08-15-sequing-review.md` 为笔误——实测 `examples/demo-project/docs/notes/` 下唯一评审笔记是 `2026-08-15-sequencing-review.md`，heredoc 采用该真实路径；`docs/rollout/inventory.md` 实测存在，未替换。连带偏差：该方法论 ref 恰是 P2-A4 既有 `evidence_sources` 的唯一条目，故端到端结果是「新增 1 条 + 报告跳过 1 条已在」，而非验收句字面的「多出两个 ref」——想法的两个带 ref 论据在节点 `evidence_sources` 中均已出现（并集 + 去重跳过，正是 IDEA-D34 的转录语义）；`docs/notes/` 下没有第二个文件可供造出净增 2 条。
3. **Task 6 Step 4c 的 old-text 锚点缺陷**：计划钉定的 old 块止于「见 §62.3）」，未捕获其后同一行内的句尾规范句（「。转录是内容复制，不是结构链接——节点侧依旧零字段。」——IDEA-D34 的核心规范句），而 new 括注又重述了同一语义（「——转录仍是内容复制，节点侧零字段」），机械替换在 spec §55.3 产生可见重复。裁定：按计划意图裁掉括注内的重复子句，句尾规范句原样保留——终态括注为「（机械动作；阶段 1–2 手工完成，阶段 3 起由 `pcp graduate` 自动执行；见 §62.3 与附录 D.7）」。

**评审驱动的增量（超出计划文本、经评审批准）：**

- **Task 1（`e4b017b`）**：`_append_to_top_level_list` docstring 更正——原文承诺接受「(or null) list」，但显式 `null`/`~` 值会被（正确地）拒绝：在 `key: null` 之后追加会把列表折叠成纯标量，拒绝才是 fail-safe 行为。仅 docstring，无行为改动。
- **Task 3 Amendment A（`f337c04`）**：新增 `_plain_scalar_round_trips` 助手 + `_yaml_scalar` 末端 round-trip 子句——修复 `--note 42` 这类标量形 note 被静默丢弃（重解析为 int、命令却报成功）的漏洞；`outcome.note` 上加 belt-and-braces 验证合取；+1 回归测试。理由：成功输出必须与磁盘事实一致。
- **Task 3 Amendment B（`f337c04`）**：`_restore()` 改返回 bool（条件化字节比较回写）；两条失败消息如实报告恢复结果（"both files were restored…" vs "could not be fully restored — check them (git diff)…"）。理由：恢复未发生时不得声称已恢复。
- **Task 4（`d795fca`）**：+3 测试与 1 处加强——CLI 级 flow 写法 `evidence_sources` 拒绝钉死（两文件字节不变）、4 空格缩进采纳单测、缺键端到端创建测试；单行 note 拒绝测试补字节不变断言。理由：拒绝路径「不动文件」此前只有单元级证据，补 CLI 级与形状级钉子。

**验收结果（Task 6，Step 1–3 全部通过）：**

- **Step 1 全量测试**：369 passed（`--collect-only -q` 各文件计数合计亦为 369；计划估 365，+4 来源见上）。
- **Step 2 引擎零改动物理验证**：`git diff --stat main -- src/ tests/` 输出仅两项（`2 files changed, 835 insertions(+), 1 deletion(-)`）：

  ```text
   src/planning_control_plane/cli.py | 348 ++++++++++++++++++++++++++-
   tests/test_graduate.py            | 488 ++++++++++++++++++++++++++++++++++
  ```

  即 `src/` 下只有 `cli.py` 一个文件变更、`tests/` 下只有新建的 `test_graduate.py`；model/loader/validator/generator/i18n/templates/context/graph 全部零命中。
- **Step 3 手工端到端**（`examples/demo-project` 复制到 `/tmp/pcp-graduate-demo`，清空 dist、建入 IDEA-0007，heredoc 修正后的真实 ref）：
  1. [x] graduate 退出 0，输出 `graduated: IDEA-0007 -> P2-A4 (OPEN -> PROMOTED)` 与转录行 `evidence transcribed into P2-A4: docs/rollout/inventory.md`（另报 `skipped 1 ref(s) already present`）；
  2. [x] `P2-A4.yaml` 的 `evidence_sources` 新增 `docs/rollout/inventory.md`（第 41 行追加一条），对原文件的 diff 仅此一行——既有条目、注释与排版逐字节原样（「两个 ref」的句面偏差与原因见上文计划内修正第 2 条）；
  3. [x] `IDEA-0007.yaml`：`status: OPEN` → `status: PROMOTED`，末尾追加 `outcome:` 块（`node: P2-A4` / `note: pilot is the evidence`），对原文件的 diff 仅此两处——作者文本逐字节原样；
  4. [x] validate 退出 0（`OK: no issues found.`）——无 `promoted-without-outcome`、无 `outcome-without-promotion`；
  5. [x] build 退出 0（11 files：index + 7 节点页 + ideas 页 + assets）；`dist/ideas.html` 的唯一分组 `data-idea-group="PROMOTED"` 含 IDEA-0007 卡片，`outcome` 渲染为指向 `nodes/P2-A4.html` 的 `<a class="idea-node-link">` 链接 + `idea-outcome-note` 文本；
  6. [x] `dist/nodes/P2-A4.html` 的 evidence 列表含新 ref `docs/rollout/inventory.md`（与既有 sequencing-review 并列）；页面 `grep "IDEA-"` 零命中——侧栏 `<nav class="sidebar-extra">` 的 Ideas 入口是全站 chrome（P1.html / index.html 各有同款 1 处），非想法标记（IDEA-D55 成立）。

**提交清单（6 个实现提交 + 本执行记录提交，旧 → 新）：**

| SHA | 说明 |
| --- | --- |
| `e4b017b` | feat(graduate)：行级 YAML 手术助手（含评审的 docstring 更正） |
| `836e58e` | feat(graduate)：拒绝判定全部先于首个字节写入 |
| `f337c04` | feat(graduate)：两文件原子毕业 + 论据转录（含评审 Amendment A/B） |
| `5ebe49b` | test(graduate)：钉死文件形状边界（缺键、transition outcome、CRLF） |
| `d795fca` | test(graduate)：钉死 flow 拒绝与手术边界覆盖（评审） |
| `9c95f10` | docs(graduate)：双 README 记录 pcp graduate |
| （本提交） | docs(ideas)：record phase-3 acceptance and spec R4 amendments——spec R4 修订（4a–4g，含附录 D.7）+ 评审修正四处（状态元数据行、§62.3 标题、§62.2 cli.py 与测试行）+ 本执行记录 + 全部 Step 复选框勾选 |

**评审遗留（并入合并主 spec 待办清单）：**

1. §60 的命令 synopsis 与退出码契约仍未含 `graduate`（R4 契约由附录 D.7 承载；合并主 spec 时补正文）。
2. D.7 第 2 行引 §54.2（规则本体在 §53.2 迁移表，§54.2 载「新想法文件」语义；CLI 错误文案同引——合并评审时统一裁量）。
3. D.7 未单列两条次要拒绝（idea 文件须来自 `ideas/` 目录、`--note` 须单行——实现与测试均已固定，非契约级裁定）。
