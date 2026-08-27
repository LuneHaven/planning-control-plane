# PCP IDEA 子系统 · 阶段 2（投影层）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 spec §61/§62.1 阶段 2 把想法层投影到生成站点：条件化的 `ideas.html` 页与侧栏入口、en/zh 双语词条、README 双语更新，并顺手修掉阶段 1 复核留下的三个显示层问题。

**Architecture:** 投影是只读的单向映射——`Project.ideas` → 视图字典 → Jinja 模板，`Idea` 与 `Node` 数据结构零改动。核心约束是 **IDEA-D63 条件化**：`project.ideas` 为空时既不写 `ideas.html`、也不渲染侧栏入口，因此无想法的既有项目除 i18n payload 外看不到任何变化。CLI 与页面共用 `model.idea_sort_key()` 一个排序源（IDEA-D61），避免同一份数据在两处顺序不一致。

**Tech Stack:** Python 3.11+ 标准库 + PyYAML + Jinja2（均为既有依赖）；pytest。无新依赖，不引入前端框架、不引入 gettext/Babel。

**Spec:** `docs/superpowers/specs/ideas-spec-draft.zh-CN.md`（含 R1/R2 修订）

**前置状态:** 阶段 1 已合并进 `main`（`4a385a6`，fast-forward），297 测试全绿。本计划从 `main` 开新分支。

## Global Constraints

以下是 spec 的项目级要求，每个任务都隐含包含：

- **IDEA-D55 投影纯净**：想法内容不得出现在节点页、dashboard 计数、焦点标记、capsule、侧栏规划树。
- **IDEA-D63 条件化投影**：项目无 `ideas/` 目录或 `project.ideas` 为空时，不生成 `ideas.html`、不渲染侧栏入口。
- **不变量 §59.4 阶段 2**：无 `ideas/` 的既有项目，`pcp build` 产物的页面结构与可见内容不变，不新增页面、不新增导航入口；允许的唯一差异是每页内嵌的 i18n payload 多出想法相关词条。（style.css 的处理见 Task 4 的前缀闸与 append-only 闸，以及 Task 6 的 R3 备注。）
- **不变量 §59.5 确定性**：同数据 + 同 PCP 版本 = 字节级相同的构建输出。
- **不变量 §59.1/2/3**：`context.py` 零改动、`Node` 数据类零字段增删、进度计数/current_focus/ready queue/侧栏规划树零感知想法。
- **IDEA-D56 语言不碰数据**：id、title、detail、note、created/last_updated 恒为作者原文，任何 locale 下都不翻译，不得带 `data-i18n`。本地化文案 + 原始枚举并陈（`开放 OPEN`），沿用既有 `badge` + `badge-raw` 机制。
- **IDEA-D61 单一排序源**：`(last_updated 为空, last_updated 升序, id 升序)`，CLI 与 ideas 页共用。
- **IDEA-D5 非目标**：不做标签、想法互链、全文检索、分页、计数徽标（侧栏入口 MVP 不带计数）、想法成为 focus。
- **既有测试零修改**：只允许**新增**测试；唯一例外是 Task 4 对 `tests/test_lang_v012.py` 的两处受控扩展（`_build` 加想法数据、`ALL_PAGES` 加 `ideas.html`），目的是让 ideas 页接受既有 LANG 契约的全部审计。
- **命名空间隔离**：想法状态的 i18n 键用 `idea_status.*`，不复用节点侧的 `status.*`；CSS 选择器一律以 `.idea-` / `.ideas-` / `.sidebar-extra` 前缀命名，不得改写既有选择器（IDEA-D14 独立命名空间）。

---

## File Structure

| 文件 | 责任 | 任务 |
| --- | --- | --- |
| `src/planning_control_plane/cli.py` | `pcp ideas` 空态与「未展示记录」计数的作用域修正；`pcp build` 汇总行 | Task 1、Task 5 |
| `src/planning_control_plane/model.py` | `idea_sort_key()`——CLI 与页面共用的唯一排序源 | Task 3 |
| `src/planning_control_plane/i18n.py` | `ideas.*` / `idea_status.*` 词条 ×2 locale + `idea_status_label()` / `idea_status_key()` | Task 2 |
| `src/planning_control_plane/generator.py` | `_idea_view()` / `_ideas_context()`；`_base_context()` 的 `has_ideas` / `is_ideas`；`build_site()` 条件化写 `ideas.html` | Task 3、Task 4 |
| `src/planning_control_plane/templates/ideas.html` | **新建**：按状态分组的想法页 | Task 3 |
| `src/planning_control_plane/templates/base.html` | 侧栏「想法」入口（条件化，位于规划树之外的独立区段） | Task 4 |
| `src/planning_control_plane/templates/static/style.css` | `.ideas-*` / `.idea-*` / `.sidebar-extra` 样式块 | Task 3、Task 4 |
| `README.md` / `README.zh-CN.md` | `pcp ideas` 命令行 + 想法层小节 | Task 5 |
| `tests/test_ideas_ui.py` | **新建**：阶段 2 全部投影测试 | Task 1–6 |
| `tests/fixtures/phase1_style.css` | **新建**：阶段 1 stylesheet 的字节基线，把「只增不改」从手工步骤升级为永久回归闸 | Task 4 |
| `tests/test_ideas.py` | 追加 Task 1 的修正测试 | Task 1 |
| `tests/test_lang_v012.py` | 受控扩展：ideas 页纳入 LANG 审计 | Task 4 |

---

## 环境准备（一次性）

```bash
cd /home/asus/dev/planning-control-plane
source .venv/bin/activate
git status                       # 应为 clean（docs/superpowers/ 未跟踪，属预期）
git checkout -b feat/ideas-phase2-projection
python -m pytest                 # 基线：297 passed
```

**测试文件约定：** 阶段 2 的新测试全部进 `tests/test_ideas_ui.py`（Task 1 的 CLI 修正除外，追加进既有 `tests/test_ideas.py`）。fixture 来自 `tests/conftest.py`：`make_project(tmp_path, config_dict=, node_dicts=, raw_files=, repo_files=)` 返回 `(project, repo_root)`，`raw_files` 的键是 `.planning/` 下的相对路径；`cli(*argv)` 原地运行 CLI 返回 `(exit_code, stdout, stderr)`；`demo_root` 是只读的 `examples/demo-project`（无想法，用于不变量 4 验收）。

---

### Task 1: 阶段 1 遗留修正 —— `pcp ideas` 的计数作用域与空态文案

阶段 1 全分支复核发现的三个显示层问题，与投影无关但同属 `pcp ideas` 的输出，先清掉，避免阶段 2 的页面文案照抄错误口径。

**Files:**
- Modify: `src/planning_control_plane/cli.py:493-553`（`cmd_ideas`）
- Modify: `docs/superpowers/plans/2026-08-27-ideas-phase1-engine.md`（执行记录的测试数字）
- Test: `tests/test_ideas.py`（追加）

**Interfaces:**
- Consumes: 无（阶段 1 已有的 `cmd_ideas`）
- Produces: 无新公开符号；`cmd_ideas` 行为变化由测试固定

**问题陈述（复核实测）：**

1. `hidden` 计数在整个 `project.ideas` / `project.load_issues` 上求和，与 `--for` 选出的作用域无关。实测 `pcp ideas --for P2-A1` 在一个坏记录全部与 P2-A1 无关的项目上仍打印 `note: 7 idea record(s) not shown`——那 7 条无论健康与否都不会出现在这份列表里。
2. `pcp ideas --status DISCARDED --for P2` 打印 `no matching ideas for node 'P2'`，但 P2 确有命中想法，空的是与状态过滤的交集；文案把空归因给节点。
3. `ideas/` 只含坏文件时打印 `no ideas yet; add .planning/ideas/<id>.yaml`——目录里有文件，只是没加载成功。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_ideas.py` 末尾：

```python
# --------------------------------------------- phase-1 review follow-ups


def _three_nodes():
    return [
        {"id": "P1", "title": "P1", "type": "PROGRAM", "status": "IMPLEMENTING"},
        {"id": "P2", "title": "P2", "type": "PHASE", "status": "READY", "parent": "P1"},
        {"id": "P3", "title": "P3", "type": "PHASE", "status": "READY", "parent": "P1"},
    ]


def test_cli_ideas_hidden_note_is_scoped_to_the_query(make_project, tmp_path, cli):
    """The 'not shown' note must describe THIS listing. A broken record that
    relates to nothing can never appear under --for, so counting it there
    tells the reader to go fix something that was never being shown."""
    raw = {
        "ideas/IDEA-OK.yaml": "id: IDEA-OK\ntitle: ok\nstatus: OPEN\nrelates_to: [P2]\n",
        "ideas/IDEA-BADSTATUS.yaml": "id: IDEA-BADSTATUS\ntitle: bad\nstatus: WISHLIST\n",
        "ideas/broken.yaml": "id: [unclosed\n",
    }
    _project, root = make_project(tmp_path, node_dicts=_three_nodes(), raw_files=raw)

    code, out, _err = cli("-p", str(root), "ideas")
    assert code == 0
    assert "2 idea record(s) not shown" in out  # global listing: both are hidden

    code, out, _err = cli("-p", str(root), "ideas", "--for", "P2")
    assert code == 0
    assert "IDEA-OK" in out
    assert "not shown" not in out  # neither hidden record relates to P2


def test_cli_ideas_status_filter_empty_says_so_even_under_for(make_project, tmp_path, cli):
    """Blaming the node when the status filter is what emptied the result
    sends the reader looking for a relates_to bug that isn't there."""
    raw = {"ideas/IDEA-OK.yaml": "id: IDEA-OK\ntitle: ok\nstatus: OPEN\nrelates_to: [P2]\n"}
    _project, root = make_project(tmp_path, node_dicts=_three_nodes(), raw_files=raw)

    code, out, _err = cli("-p", str(root), "ideas", "--for", "P2", "--status", "DISCARDED")
    assert code == 0
    assert "status filter" in out
    assert "no matching ideas for node 'P2'" not in out


def test_cli_ideas_for_no_match_still_blames_the_node(make_project, tmp_path, cli):
    """The node-scoped wording stays when the scope really is what is empty."""
    raw = {"ideas/IDEA-OK.yaml": "id: IDEA-OK\ntitle: ok\nstatus: OPEN\nrelates_to: [P2]\n"}
    _project, root = make_project(tmp_path, node_dicts=_three_nodes(), raw_files=raw)

    code, out, _err = cli("-p", str(root), "ideas", "--for", "P3")
    assert code == 0
    assert "no matching ideas for node 'P3'" in out


def test_cli_ideas_all_files_broken_does_not_claim_there_are_none(make_project, tmp_path, cli):
    """'no ideas yet' tells the reader to create a file they already created."""
    raw = {"ideas/broken.yaml": "id: [unclosed\n"}
    _project, root = make_project(tmp_path, node_dicts=_three_nodes(), raw_files=raw)

    code, out, _err = cli("-p", str(root), "ideas")
    assert code == 0
    assert "no ideas yet" not in out
    assert "could not be loaded" in out
    assert "1 idea record(s) not shown" in out
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_ideas.py -k "hidden_note_is_scoped or status_filter_empty_says_so or all_files_broken" -v`
Expected: FAIL —— 第一个断言 `"not shown" not in out` 失败（作用域外的记录被计入），文案断言 `"status filter" in out` / `"could not be loaded" in out` 找不到字符串。

- [ ] **Step 3: 实现修正**

`cmd_ideas` 内，把 `selected` 计算之后到函数结束的部分替换为下面的版本。三处改动：`hidden` 只统计**本次列表本可展示、却因数据问题缺席**的记录；空态文案区分三种原因；全坏文件不再说 "no ideas yet"。

```python
    if args.status:
        wanted = set(args.status)
    elif args.node is not None:
        wanted = {IdeaStatus.OPEN.value, IdeaStatus.PARKED.value}  # IDEA-D62
    else:
        wanted = set(_IDEA_STATUS_ORDER)

    groups: dict[str, list[tuple[Idea, list[str] | None]]] = {status: [] for status in _IDEA_STATUS_ORDER}
    for idea, via in selected:
        if idea.status in groups:
            groups[idea.status].append((idea, via))

    shown = 0
    for status in _IDEA_STATUS_ORDER:
        if status not in wanted:
            continue
        entries = sorted(groups[status], key=lambda pair: _idea_sort_key(pair[0]))
        if not entries:
            continue
        print(f"== {status} ({len(entries)}) ==")
        for idea, via in entries:
            print(_idea_line(idea, via))
        shown += len(entries)

    # Records that this listing would have shown but cannot: files that never
    # parsed, entries dropped as unusable or duplicate, and loaded ideas whose
    # status falls outside the fixed group order. Ordinary status filtering
    # never counts — that is a display choice, not a data problem. Neither
    # does a record outside the --for scope: it was never part of this
    # listing, so reporting it here sends the reader after a phantom.
    file_level = sum(1 for i in project.load_issues if i.rule in _HIDDEN_IDEA_RULES)
    if args.node is None:
        bad_status = sum(1 for idea in project.ideas.values() if idea.status not in _IDEA_STATUS_ORDER)
        hidden = file_level + bad_status
    else:
        # A file-level failure has no relates_to to test against the scope, so
        # it stays reportable; a loaded idea does, and only counts when it hits.
        hidden = file_level + sum(
            1 for idea, _via in selected if idea.status not in _IDEA_STATUS_ORDER
        )

    if shown == 0:
        if args.node is not None and any(groups[status] for status in _IDEA_STATUS_ORDER):
            print(f"no ideas match the requested status filter for node '{args.node}'")
        elif args.node is not None:
            print(f"no matching ideas for node '{args.node}'" + (" (subtree)" if args.subtree else ""))
        elif project.ideas:
            print("no ideas match the requested status filter")
        elif hidden:
            print("no ideas could be loaded from .planning/ideas/")
        else:
            print("no ideas yet; add .planning/ideas/<id>.yaml")

    if hidden:
        print(
            f"note: {hidden} idea record(s) not shown (broken or duplicate "
            "entry, or invalid status); run 'pcp validate'"
        )
    return EXIT_OK
```

注意 `selected` 在 `--for` 分支里只装命中作用域的想法，所以 `for idea, _via in selected` 天然是作用域内的集合；`file_level` 无 `relates_to` 可比对，按「无法判断即报告」保留——这是有意的保守选择，写在注释里。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_ideas.py -v`
Expected: PASS（68 + 4 = 72 个用例）

- [ ] **Step 5: 回填阶段 1 计划的执行记录数字**

`docs/superpowers/plans/2026-08-27-ideas-phase1-engine.md` 末尾「验收」一行写的是 `294 passed（229 基线 + 65 新增）`，实际为 297（229 + 68）——后续三个评审提交追加了测试但未回填。改为：

```markdown
**验收：** Task 8 全部通过——297 passed（229 基线 + 68 新增）；不变量 1/2 物理验证零 diff；不变量 4 以 dist 清单字节级一致验证；失败域用例（坏 YAML 下 status/context/build 全 exit 0）通过。
```

- [ ] **Step 6: 全量回归**

Run: `python -m pytest`
Expected: 301 passed

- [ ] **Step 7: Commit**

```bash
git add src/planning_control_plane/cli.py tests/test_ideas.py docs/superpowers/plans/2026-08-27-ideas-phase1-engine.md
git commit -m "fix(ideas): scope the hidden-record note to the listing; accurate empty states"
```

---

### Task 2: i18n —— 想法层词条 ×2 locale 与 `idea_status_label` / `idea_status_key`

**Files:**
- Modify: `src/planning_control_plane/i18n.py`
- Test: `tests/test_ideas_ui.py`（新建）

**Interfaces:**
- Consumes: 既有 `translator()` / `resolve_locale()` / `_EN` / `_ZH_CN` / `TRANSLATIONS`
- Produces:
  - `i18n.idea_status_label(locale: str, status: str) -> str`——受控枚举外的值原样返回
  - `i18n.idea_status_key(status: str) -> str | None`——`None` 表示「这不是受控枚举值，运行时翻译器不得覆盖」
  - 键命名空间 `ideas.*`（页面文案）与 `idea_status.*`（四个状态标签）

规范锚点：IDEA-D56（双语 + 原始枚举并陈）、IDEA-D14（独立命名空间）、IDEA-D54（页面字段）。

- [ ] **Step 1: 写失败测试**

新建 `tests/test_ideas_ui.py`：

```python
"""Idea layer projection tests (spec: specs/ideas-spec-draft.zh-CN.md, phase 2).

Covers the generated ideas page, the conditional sidebar entry, the
bilingual strings and the phase-2 wording of backward-compatibility
invariant 4.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from planning_control_plane import generator, i18n
from planning_control_plane.model import IdeaStatus


def test_idea_status_labels_exist_in_both_locales():
    for status in IdeaStatus:
        for locale in i18n.SUPPORTED_LOCALES:
            assert i18n.idea_status_label(locale, status.value)


def test_english_idea_status_labels_are_the_raw_enum():
    """Mirrors status_label: under en the label IS the enum, so the page
    never prints the same value twice (the badge-raw chip is CSS-hidden)."""
    for status in IdeaStatus:
        assert i18n.idea_status_label("en", status.value) == status.value


def test_chinese_idea_status_labels_are_translated_and_distinct():
    labels = {s.value: i18n.idea_status_label("zh-CN", s.value) for s in IdeaStatus}
    for raw, label in labels.items():
        assert label != raw
    assert len(set(labels.values())) == len(labels)


def test_idea_status_key_is_none_outside_the_controlled_enum():
    assert i18n.idea_status_key("OPEN") == "idea_status.OPEN"
    assert i18n.idea_status_key("WISHLIST") is None
    assert i18n.idea_status_label("zh-CN", "WISHLIST") == "WISHLIST"


def test_idea_status_namespace_does_not_collide_with_node_status():
    """Two enums, two namespaces (IDEA-D14). A shared key would let a node
    status re-label an idea badge at runtime, or the reverse."""
    node_keys = {k for k in i18n.TRANSLATIONS["en"] if k.startswith("status.")}
    idea_keys = {k for k in i18n.TRANSLATIONS["en"] if k.startswith("idea_status.")}
    assert idea_keys
    assert not node_keys & idea_keys
    assert i18n.status_key("OPEN") is None  # OPEN is not a NodeStatus


def test_ideas_page_strings_exist_in_both_locales():
    required = {
        "ideas.nav", "ideas.nav_label", "ideas.title", "ideas.subtitle",
        "ideas.detail", "ideas.benchmark", "ideas.methodology",
        "ideas.relates_to", "ideas.outcome", "ideas.created", "ideas.updated",
        "ideas.no_sources", "ideas.unknown_node", "ideas.group_count",
    }
    for locale in i18n.SUPPORTED_LOCALES:
        missing = required - set(i18n.TRANSLATIONS[locale])
        assert not missing, (locale, sorted(missing))
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_ideas_ui.py -v`
Expected: FAIL —— `AttributeError: module 'planning_control_plane.i18n' has no attribute 'idea_status_label'`

- [ ] **Step 3: 实现 i18n 增量**

3a. `__all__`（`src/planning_control_plane/i18n.py:44` 起）按字母序插入两项：

```python
    "html_lang",
    "idea_status_key",
    "idea_status_label",
    "is_supported",
```

3b. `from planning_control_plane.model import NodeStatus, TrackStatus` 保持不变（`idea_status_*` 只读字典，不需要 `IdeaStatus`）。

3c. `_EN` 字典末尾（最后一个 `"action.*"` 条目之后、右花括号之前）追加：

```python
    # -------------------------------------------------------------- ideas
    # Idea layer (spec §61). Uncommitted thinking: presentation only, and a
    # namespace of its own — `idea_status.*` never shares a key with the
    # node-side `status.*` (IDEA-D14).
    "ideas.nav": "Ideas",
    "ideas.nav_label": "Idea layer (sidebar)",
    "ideas.title": "Ideas",
    "ideas.subtitle": (
        "Uncommitted thinking. An idea reaches the planning graph only by graduating."
    ),
    "ideas.group_count": "{n}",
    "ideas.detail": "Detail",
    "ideas.benchmark": "Benchmark sources",
    "ideas.methodology": "Methodology sources",
    "ideas.relates_to": "Born from",
    "ideas.outcome": "Graduated to",
    "ideas.created": "Created",
    "ideas.updated": "Updated",
    "ideas.no_sources": "None recorded",
    "ideas.unknown_node": "unknown node",
    "idea_status.OPEN": "OPEN",
    "idea_status.PARKED": "PARKED",
    "idea_status.PROMOTED": "PROMOTED",
    "idea_status.DISCARDED": "DISCARDED",
```

3d. `_ZH_CN` 字典末尾同位置追加（键集必须与 `_EN` 完全一致，`test_locales_have_identical_key_sets` 会强制这一点）：

```python
    # -------------------------------------------------------------- ideas
    "ideas.nav": "想法",
    "ideas.nav_label": "想法层（侧栏）",
    "ideas.title": "想法",
    "ideas.subtitle": "尚未承诺的思考。想法只能通过毕业进入规划图。",
    "ideas.group_count": "{n}",
    "ideas.detail": "原文",
    "ideas.benchmark": "对标论据",
    "ideas.methodology": "方法论论据",
    "ideas.relates_to": "诞生上下文",
    "ideas.outcome": "毕业去向",
    "ideas.created": "创建",
    "ideas.updated": "更新",
    "ideas.no_sources": "暂无",
    "ideas.unknown_node": "未知节点",
    "idea_status.OPEN": "开放",
    "idea_status.PARKED": "搁置",
    "idea_status.PROMOTED": "已毕业",
    "idea_status.DISCARDED": "已否决",
```

3e. 在 `status_key()` 之后（`track_key()` 之前）加两个函数：

```python
def idea_status_label(locale: str, status: str) -> str:
    """Localized label for an idea status (spec §53.1, IDEA-D56).

    Values outside :class:`~planning_control_plane.model.IdeaStatus` are
    returned unchanged — the generator projects idea data defensively and
    leaves the verdict to ``pcp validate``, exactly as it does for nodes.
    """
    key = f"idea_status.{status}"
    return translator(locale)(key) if key in _EN else status


def idea_status_key(status: str) -> str | None:
    """Translation key that re-labels an idea status at runtime, or ``None``.

    A separate namespace from :func:`status_key`: the two enums never
    interoperate (IDEA-D14), so a shared key would let a node status
    re-label an idea badge in the browser.
    """
    key = f"idea_status.{status}"
    return key if key in _EN else None
```

3f. 模块 docstring 第一段的 scope 说明后追加一句（与既有措辞同风格）：

```
Since the idea layer (spec §61) the same discipline covers ideas: their
statuses live in the ``idea_status.*`` namespace, and idea ids, titles,
detail text and justification notes are author data that no locale
touches.
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_ideas_ui.py tests/test_i18n.py -v`
Expected: PASS —— 其中既有的 `test_locales_have_identical_key_sets` 与 `test_no_translation_value_is_empty` 自动覆盖新词条的键集一致性与非空。

- [ ] **Step 5: Commit**

```bash
git add src/planning_control_plane/i18n.py tests/test_ideas_ui.py
git commit -m "feat(ideas): bilingual idea-layer strings and idea_status label helpers"
```

---

### Task 3: generator 视图 + `ideas.html` 模板 + 条件化写页

**Files:**
- Modify: `src/planning_control_plane/model.py`（+`idea_sort_key`）
- Modify: `src/planning_control_plane/cli.py`（`_idea_sort_key` 改为复用 `model.idea_sort_key`）
- Modify: `src/planning_control_plane/generator.py`
- Create: `src/planning_control_plane/templates/ideas.html`
- Modify: `src/planning_control_plane/templates/static/style.css`
- Test: `tests/test_ideas_ui.py`（追加）

**Interfaces:**
- Consumes: `i18n.idea_status_label` / `i18n.idea_status_key`（Task 2）；既有 `_Ctx`、`_base_context`、`_node_ref`、`_write_text`
- Produces:
  - `model.idea_sort_key(idea: Idea) -> tuple[bool, str, str]`
  - `generator._idea_view(ctx: _Ctx, idea: Idea) -> dict`
  - `generator._ideas_context(ctx: _Ctx) -> dict`——含 `groups: list[dict]`，每个 `{"status": {"raw","label","i18n"}, "count": int, "ideas": [view...]}`
  - `build_site()` 在 `project.ideas` 非空时多写一个 `<out_dir>/ideas.html`

规范锚点：IDEA-D54（页面字段与分组）、IDEA-D61（排序）、IDEA-D63（条件化）、IDEA-D55（不外溢）。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_ideas_ui.py`：

```python
# ---------------------------------------------------------- fixtures


IDEA_NODES = [
    {"id": "P1", "title": "Program One", "type": "PROGRAM", "status": "IMPLEMENTING"},
    {"id": "P2", "title": "Phase Two", "type": "PHASE", "status": "READY", "parent": "P1"},
]

IDEA_FILES = {
    "ideas/IDEA-0007.yaml": (
        "id: IDEA-0007\n"
        "title: Trend comparison view 趋势对比\n"
        "status: OPEN\n"
        "detail: One paragraph, no structure required at capture time.\n"
        "relates_to: [P2]\n"
        "benchmark_sources:\n"
        "  - ref: docs/bench.md\n"
        "    note: Grafana time-compare panels\n"
        "  - note: Stripe dashboard month-over-month\n"
        "methodology_sources:\n"
        "  - ref: docs/method.md\n"
        "created: 2026-08-27\n"
        "last_updated: 2026-08-27\n"
    ),
    "ideas/IDEA-0001.yaml": (
        "id: IDEA-0001\ntitle: Stale open idea\nstatus: OPEN\nlast_updated: 2026-01-05\n"
    ),
    "ideas/IDEA-0003.yaml": "id: IDEA-0003\ntitle: Undated idea\nstatus: OPEN\n",
    "ideas/IDEA-0020.yaml": (
        "id: IDEA-0020\ntitle: Parked idea\nstatus: PARKED\nlast_updated: 2026-07-01\n"
    ),
    "ideas/IDEA-0012.yaml": (
        "id: IDEA-0012\n"
        "title: Graduated idea\n"
        "status: PROMOTED\n"
        "outcome:\n"
        "  node: P2\n"
        "  note: pilot is the evidence\n"
        "last_updated: 2026-08-20\n"
    ),
    "ideas/IDEA-0030.yaml": (
        "id: IDEA-0030\ntitle: Discarded idea\nstatus: DISCARDED\nlast_updated: 2026-06-01\n"
    ),
    "ideas/IDEA-DANGLING.yaml": (
        "id: IDEA-DANGLING\ntitle: Dangling relation\nstatus: OPEN\nrelates_to: [NOSUCH]\n"
    ),
}


def _build_with_ideas(make_project, tmp_path, locale=None, name="repo-ideas"):
    room = tmp_path / name
    room.mkdir()
    config = {"project": {"id": "p", "name": "Ideas Project"}, "planning": {"current_focus": "P2"}}
    if locale is not None:
        config["ui"] = {"locale": locale}
    project, root = make_project(
        room,
        config_dict=config,
        node_dicts=IDEA_NODES,
        raw_files=IDEA_FILES,
        repo_files={"docs/bench.md": "b", "docs/method.md": "m"},
    )
    dist = root / ".planning" / "dist"
    generator.build_site(project, dist)
    return dist


@pytest.fixture
def ideas_dist(make_project, tmp_path):
    return _build_with_ideas(make_project, tmp_path)


@pytest.fixture
def ideas_dist_zh(make_project, tmp_path):
    return _build_with_ideas(make_project, tmp_path, "zh-CN", "repo-ideas-zh")


def _page(dist, name):
    return (dist / name).read_text(encoding="utf-8")


# ---------------------------------------------------- ordering source


def test_idea_sort_key_is_shared_by_cli_and_generator():
    """IDEA-D61: one ordering source, so the same data never lists in two
    different orders across the CLI and the page."""
    from planning_control_plane import cli as cli_module
    from planning_control_plane.model import Idea, idea_sort_key

    undated = Idea(id="B", title="b")
    stale = Idea(id="A", title="a", last_updated="2026-01-05")
    fresh = Idea(id="C", title="c", last_updated="2026-08-27")
    assert sorted([undated, fresh, stale], key=idea_sort_key) == [stale, fresh, undated]
    assert cli_module._idea_sort_key is idea_sort_key


# ------------------------------------------------------- the ideas page


def test_ideas_page_is_generated_when_the_project_has_ideas(ideas_dist):
    assert (ideas_dist / "ideas.html").is_file()


def test_ideas_page_groups_statuses_in_the_fixed_order(ideas_dist):
    page = _page(ideas_dist, "ideas.html")
    positions = [page.index(f'data-idea-group="{s}"') for s in ("OPEN", "PARKED", "PROMOTED", "DISCARDED")]
    assert positions == sorted(positions)


def test_ideas_page_orders_each_group_by_the_shared_key(ideas_dist):
    """Stale first, undated last (IDEA-D61) — identical to `pcp ideas`."""
    page = _page(ideas_dist, "ideas.html")
    open_block = page[page.index('data-idea-group="OPEN"'):page.index('data-idea-group="PARKED"')]
    order = re.findall(r'data-idea-id="([^"]+)"', open_block)
    assert order == ["IDEA-0001", "IDEA-0007", "IDEA-DANGLING", "IDEA-0003"]


def test_ideas_page_shows_every_documented_field(ideas_dist):
    """IDEA-D54: id + status + title, detail, both justification slots
    (ref as text), relates_to and outcome as node links, created/updated."""
    page = _page(ideas_dist, "ideas.html")
    assert "IDEA-0007" in page
    assert "Trend comparison view 趋势对比" in page
    assert "One paragraph, no structure required at capture time." in page
    assert "docs/bench.md" in page                       # ref rendered as text
    assert "Grafana time-compare panels" in page         # note
    assert "Stripe dashboard month-over-month" in page   # note-only entry
    assert "docs/method.md" in page
    assert "2026-08-27" in page
    assert 'href="nodes/P2.html"' in page                # relates_to link
    assert "pilot is the evidence" in page               # outcome note


def test_ideas_page_never_links_a_node_it_did_not_generate(ideas_dist):
    """Mirrors _node_ref: an unknown target stays plain text (no fabricated
    href), so a dangling relates_to can never produce a 404 link."""
    page = _page(ideas_dist, "ideas.html")
    assert "NOSUCH" in page
    assert 'href="nodes/NOSUCH.html"' not in page


def test_ideas_page_ref_is_text_not_a_link(ideas_dist):
    """IDEA-D18/§52.2: PCP describes repository paths, it does not resolve
    them into the generated site."""
    page = _page(ideas_dist, "ideas.html")
    assert 'href="docs/bench.md"' not in page
    assert "docs/bench.md</" in page


def test_ideas_page_shows_localized_label_and_raw_enum(ideas_dist_zh):
    """IDEA-D56: `开放 OPEN` — localized text plus the stored enum."""
    page = _page(ideas_dist_zh, "ideas.html")
    assert 'data-i18n="idea_status.OPEN"' in page
    assert "开放" in page
    assert ">OPEN</span>" in page  # badge-raw chip keeps the enum greppable


def test_ideas_page_does_not_translate_author_data(ideas_dist_zh):
    """IDEA-D56 / LANG-D3: ids, titles, detail and notes are author text."""
    page = _page(ideas_dist_zh, "ideas.html")
    for user_class in ("idea-id", "idea-title", "idea-detail", "idea-source-note", "idea-source-ref"):
        assert not re.search(rf'class="[^"]*{user_class}[^"]*"[^>]*data-i18n=', page), user_class
    assert "Trend comparison view 趋势对比" in page


# ------------------------------------------- IDEA-D63 conditional output


def test_no_ideas_project_gets_no_ideas_page(make_project, tmp_path):
    project, root = make_project(tmp_path, node_dicts=IDEA_NODES)
    dist = root / ".planning" / "dist"
    generator.build_site(project, dist)
    assert not (dist / "ideas.html").exists()


def test_ideas_directory_with_only_broken_files_gets_no_page(make_project, tmp_path):
    """IDEA-D63 keys off the loaded idea set, not off the directory: a
    directory of unparseable files projects nothing."""
    project, root = make_project(
        tmp_path, node_dicts=IDEA_NODES, raw_files={"ideas/broken.yaml": "id: [unclosed\n"}
    )
    assert project.ideas == {}
    dist = root / ".planning" / "dist"
    generator.build_site(project, dist)
    assert not (dist / "ideas.html").exists()


# --------------------------------------------------- IDEA-D55 no overflow


def test_ideas_never_reach_node_pages_or_the_dashboard(ideas_dist):
    """Invariants 1–3 at the projection layer: idea content appears on the
    ideas page and nowhere else."""
    for name in ("index.html", "nodes/P1.html", "nodes/P2.html"):
        page = _page(ideas_dist, name)
        body = re.sub(
            r'<script type="application/json" id="pcp-i18n">.*?</script>', "", page, flags=re.DOTALL
        )
        assert "IDEA-0007" not in body, name
        assert "Trend comparison view" not in body, name
        assert "pilot is the evidence" not in body, name


def test_build_with_ideas_is_deterministic(make_project, tmp_path):
    """Invariant §59.5 extends to the ideas page."""
    first = _build_with_ideas(make_project, tmp_path, name="det-a")
    second = _build_with_ideas(make_project, tmp_path, name="det-b")
    assert _page(first, "ideas.html") == _page(second, "ideas.html")
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_ideas_ui.py -v`
Expected: FAIL —— `ImportError: cannot import name 'idea_sort_key' from planning_control_plane.model`

- [ ] **Step 3: model.py 加共享排序键**

在 `Idea` 数据类之后（`Node` 之前）加：

```python
def idea_sort_key(idea: Idea) -> tuple[bool, str, str]:
    """Display order inside one idea status group (spec IDEA-D61).

    ``(last_updated is empty, last_updated, id)``: dated ideas sort oldest
    first so stale thinking surfaces at the top of its group, and undated
    ideas sort last. ``last_updated`` is an unvalidated free string that
    defaults to ``""``, so a plain ascending sort would float *undated*
    ideas rather than *stale* ones — the opposite of the intent.

    The single ordering source for ``pcp ideas`` and the generated ideas
    page, so the same data never lists in two different orders. Relative
    order of non-ISO spellings is undefined (documented cost of not
    validating the format; no date parsing is introduced).
    """
    return (idea.last_updated == "", idea.last_updated, idea.id)
```

model.py 模块 docstring 的第二个 bullet 已列 `:class:`Idea``，无需再改。

- [ ] **Step 4: cli.py 改为复用**

删除 `cli.py` 中的 `_idea_sort_key` 函数体，改为从 model 导入并保留同名别名（保持既有测试与调用点不变）：

`from planning_control_plane.model import (...)` 的导入清单里加 `idea_sort_key`，然后把原函数替换为：

```python
#: Ordering inside one status group — shared with the generated ideas page
#: so the two never disagree (spec IDEA-D61, defined in model.py).
_idea_sort_key = idea_sort_key
```

- [ ] **Step 5: generator.py 加视图构建器**

5a. 导入行加 `Idea` 与 `idea_sort_key`：

```python
from planning_control_plane.model import Decision, Idea, Project, TrackStatus, idea_sort_key
```
（按文件里既有的导入清单原样合并，保持字母序；`Decision` / `Project` / `TrackStatus` 已在其中。）

5b. 在 `_source_views()` 之后加两个函数：

```python
def _idea_source_views(sources: list) -> list[dict]:
    """One justification slot as template rows (spec §52.2).

    ``ref`` renders as text, never as a link: it points into the *source*
    repository, which the generated site does not contain, and PCP links
    only pages it generated. ``note`` is the only channel for the world
    outside the repository (IDEA-D18) and is author text in every locale.
    """
    return [{"ref": entry.ref or "", "note": entry.note or ""} for entry in sources]


def _idea_view(ctx: _Ctx, idea: Idea) -> dict:
    """One idea as the template sees it (spec IDEA-D54).

    Node references go through :func:`_node_ref`, so a dangling
    ``relates_to`` or ``outcome.node`` renders as plain text with
    ``known=False`` — the generator never fabricates a link to a page it
    did not write. The stored status string is projected defensively:
    values outside :class:`IdeaStatus` keep their text and carry no
    runtime translation key.
    """
    return {
        "id": idea.id,
        "title": idea.title,
        "detail": idea.detail,
        "status": {
            "raw": idea.status,
            "label": i18n.idea_status_label(ctx.locale, idea.status),
            "i18n": i18n.idea_status_key(idea.status),
        },
        "relates_to": _sorted_refs(ctx, list(dict.fromkeys(idea.relates_to))),
        "outcome": (
            {"ref": _node_ref(ctx, idea.outcome.node), "note": idea.outcome.note}
            if idea.outcome is not None
            else None
        ),
        "benchmark_sources": _idea_source_views(idea.benchmark_sources),
        "methodology_sources": _idea_source_views(idea.methodology_sources),
        "created": idea.created,
        "last_updated": idea.last_updated,
    }


def _ideas_context(ctx: _Ctx) -> dict:
    """Ideas page context: status groups in the fixed order (spec §61).

    Statuses outside :class:`IdeaStatus` have no group of their own — the
    page projects the controlled enum, and ``pcp validate`` is where an
    invalid status gets reported (spec §12: the site stores and shows, it
    never judges). Groups with no members are dropped rather than rendered
    empty.
    """
    grouped: dict[str, list] = {member.value: [] for member in IdeaStatus}
    for idea in sorted(ctx.project.ideas.values(), key=idea_sort_key):
        if idea.status in grouped:
            grouped[idea.status].append(_idea_view(ctx, idea))
    groups = [
        {
            "status": {
                "raw": member.value,
                "label": i18n.idea_status_label(ctx.locale, member.value),
                "i18n": i18n.idea_status_key(member.value),
            },
            "count": len(grouped[member.value]),
            "ideas": grouped[member.value],
        }
        for member in IdeaStatus
        if grouped[member.value]
    ]
    return {**_base_context(ctx, None, is_ideas_page=True), "groups": groups}
```

5c. generator 的 model 导入还需 `IdeaStatus`：把 5a 的导入行改为

```python
from planning_control_plane.model import Decision, Idea, IdeaStatus, Project, TrackStatus, idea_sort_key
```

5d. `_base_context()` 签名与返回值改动（`generator.py:375`）——本步只加参数与三个键，模板消费留到 Task 4：

```python
def _base_context(ctx: _Ctx, current_page_id: str | None, is_ideas_page: bool = False) -> dict:
    """Context every page shares: project name, locale, relative link bases
    and the sidebar planning tree (with the current focus highlighted).

    The sidebar owns the full planning topology; no other region of the
    site renders the whole tree again (UI-D3). ``has_ideas`` gates the idea
    layer's sidebar entry: a project with no ideas renders no entry at all
    (IDEA-D63), which is what keeps every existing page unchanged.
    """
    project = ctx.project
    return {
        "project_name": project.config.name or project.config.id,
        # Lets the topbar mark its own entry as the current page instead of
        # hiding it, so the global navigation never shifts position.
        "is_dashboard": current_page_id is None and not is_ideas_page,
        "is_ideas": is_ideas_page,
        "has_ideas": bool(project.ideas),
        "locale": ctx.locale,
        "html_lang": i18n.html_lang(ctx.locale),
        "t": i18n.translator(ctx.locale),
        "i18n_payload": i18n.runtime_payload(ctx.locale),
        "focus_id": project.config.current_focus,
        "tree": _planning_tree(ctx, project.config.current_focus, current_page_id),
        "base": {
            "index": f"{ctx.prefix}index.html",
            "ideas": f"{ctx.prefix}ideas.html",
            "nodes": f"{ctx.prefix}nodes/",
            "assets": f"{ctx.prefix}assets/",
        },
    }
```

5e. `build_site()`：在写完 `index.html` 之后、节点页循环之前插入条件化写页。

```python
    written.append(
        _write_text(out_dir / "index.html", env.get_template("index.html").render(**_index_context(index_ctx)))
    )

    # Idea layer projection (spec §61). Conditional by IDEA-D63: no ideas
    # means no page and no sidebar entry, so a project that never adopted
    # the idea layer keeps exactly the site it had before.
    if project.ideas:
        ideas_ctx = _Ctx(project=project, graph=graph, safe=safe, locale=locale, prefix="")
        written.append(
            _write_text(out_dir / "ideas.html", env.get_template("ideas.html").render(**_ideas_context(ideas_ctx)))
        )
```

5f. `build_site()` docstring 的第一段补一句：

```
Projects that carry ideas also get a single ``ideas.html`` at the site
root; projects without ideas get no such page and no navigation entry
for it (IDEA-D63).
```

- [ ] **Step 6: 写 `templates/ideas.html`**

新建 `src/planning_control_plane/templates/ideas.html`：

```html
{% extends "base.html" %}
{% block title %}{{ t("ideas.title") }} · {{ project_name }} · {{ t("site.tool") }}{% endblock %}
{% block content %}
<header class="page-head">
  <h1 data-i18n="ideas.title">{{ t("ideas.title") }}</h1>
  <p class="muted" data-i18n="ideas.subtitle">{{ t("ideas.subtitle") }}</p>
</header>
{% for group in groups %}
<section class="panel ideas-group" data-idea-group="{{ group.status.raw }}" aria-labelledby="ideas-{{ group.status.raw }}">
  <h2 id="ideas-{{ group.status.raw }}">
    <span class="idea-badge badge badge--lg" data-idea-status="{{ group.status.raw }}"><span{% if group.status.i18n %} data-i18n="{{ group.status.i18n }}"{% endif %}>{{ group.status.label }}</span>{% if group.status.i18n %} <span class="badge-raw mono">{{ group.status.raw }}</span>{% endif %}</span>
    <span class="count" data-i18n="ideas.group_count" data-i18n-args='{{ {"n": group.count} | tojson }}'>{{ t("ideas.group_count", n=group.count) }}</span>
  </h2>
  <ul class="idea-list">
{% for idea in group.ideas %}
    <li class="idea-card" data-idea-id="{{ idea.id }}">
      <div class="idea-head">
        <span class="idea-id mono">{{ idea.id }}</span>
        <span class="idea-title">{{ idea.title }}</span>
      </div>
{% if idea.detail %}
      <p class="idea-detail prose">{{ idea.detail }}</p>
{% endif %}
      <dl class="idea-meta">
        <dt data-i18n="ideas.benchmark">{{ t("ideas.benchmark") }}</dt>
        <dd>
{% if idea.benchmark_sources %}
          <ul class="idea-sources">
{% for source in idea.benchmark_sources %}
            <li>{% if source.ref %}<span class="idea-source-ref mono">{{ source.ref }}</span>{% endif %}{% if source.note %}<span class="idea-source-note">{{ source.note }}</span>{% endif %}</li>
{% endfor %}
          </ul>
{% else %}
          <span class="muted" data-i18n="ideas.no_sources">{{ t("ideas.no_sources") }}</span>
{% endif %}
        </dd>
        <dt data-i18n="ideas.methodology">{{ t("ideas.methodology") }}</dt>
        <dd>
{% if idea.methodology_sources %}
          <ul class="idea-sources">
{% for source in idea.methodology_sources %}
            <li>{% if source.ref %}<span class="idea-source-ref mono">{{ source.ref }}</span>{% endif %}{% if source.note %}<span class="idea-source-note">{{ source.note }}</span>{% endif %}</li>
{% endfor %}
          </ul>
{% else %}
          <span class="muted" data-i18n="ideas.no_sources">{{ t("ideas.no_sources") }}</span>
{% endif %}
        </dd>
{% if idea.relates_to %}
        <dt data-i18n="ideas.relates_to">{{ t("ideas.relates_to") }}</dt>
        <dd>
{% for ref in idea.relates_to %}
{% if ref.known %}
          <a class="idea-node-link" href="{{ base.nodes }}{{ ref.id }}.html" title="{{ ref.id }} — {{ ref.title }}"><span class="mono">{{ ref.id }}</span></a>
{% else %}
          <span class="idea-node-missing"><span class="mono">{{ ref.id }}</span> <span class="muted" data-i18n="ideas.unknown_node">{{ t("ideas.unknown_node") }}</span></span>
{% endif %}
{% endfor %}
        </dd>
{% endif %}
{% if idea.outcome %}
        <dt data-i18n="ideas.outcome">{{ t("ideas.outcome") }}</dt>
        <dd>
{% if idea.outcome.ref.known %}
          <a class="idea-node-link" href="{{ base.nodes }}{{ idea.outcome.ref.id }}.html" title="{{ idea.outcome.ref.id }} — {{ idea.outcome.ref.title }}"><span class="mono">{{ idea.outcome.ref.id }}</span></a>
{% else %}
          <span class="idea-node-missing"><span class="mono">{{ idea.outcome.ref.id }}</span> <span class="muted" data-i18n="ideas.unknown_node">{{ t("ideas.unknown_node") }}</span></span>
{% endif %}
{% if idea.outcome.note %}
          <span class="idea-outcome-note">{{ idea.outcome.note }}</span>
{% endif %}
        </dd>
{% endif %}
      </dl>
      <p class="idea-dates muted">
{% if idea.created %}
        <span data-i18n="ideas.created">{{ t("ideas.created") }}</span> <span class="mono">{{ idea.created }}</span>
{% endif %}
{% if idea.last_updated %}
        <span data-i18n="ideas.updated">{{ t("ideas.updated") }}</span> <span class="mono">{{ idea.last_updated }}</span>
{% endif %}
      </p>
    </li>
{% endfor %}
  </ul>
</section>
{% endfor %}
{% endblock %}
```

**注意**：`href="{{ base.nodes }}{{ ref.id }}.html"` 使用的是 **id 而非 safe stem**，与 `_node_ref` 返回的 `url` 不一致。改用 `_node_ref` 已经算好的 `url`——它已经过 `_safe_stem` 处理，含特殊字符的 id 才不会生成打不开的链接。把上面两处 `href` 改为：

```html
          <a class="idea-node-link" href="{{ ref.url }}" title="{{ ref.id }} — {{ ref.title }}"><span class="mono">{{ ref.id }}</span></a>
```
```html
          <a class="idea-node-link" href="{{ idea.outcome.ref.url }}" title="{{ idea.outcome.ref.id }} — {{ idea.outcome.ref.title }}"><span class="mono">{{ idea.outcome.ref.id }}</span></a>
```

- [ ] **Step 7: 加 CSS**

在 `style.css` 末尾追加（全部选择器以 `.ideas-` / `.idea-` 前缀命名，不触碰任何既有选择器）：

```css
/* ----------------------------------------------------------- idea layer */
/* Spec §61. The idea layer is a separate world: its own status attribute
   (`data-idea-status`, never `data-status`), its own card list, and one
   neutral badge treatment — idea statuses carry no colour or shape system
   of their own, because the group heading already names the status and the
   colour vocabulary belongs to the planning graph. */

.ideas-group + .ideas-group {
  margin-top: 16px;
}

.ideas-group h2 {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.idea-badge {
  background: var(--surface-3);
  color: var(--text-muted);
  border-color: var(--border);
}

.idea-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 12px;
}

.idea-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 14px;
  background: var(--surface-2);
}

.idea-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}

.idea-id {
  font-size: 12px;
  color: var(--text-muted);
}

.idea-title {
  font-weight: 600;
}

.idea-detail {
  margin: 8px 0 0;
}

.idea-meta {
  margin: 10px 0 0;
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 4px 12px;
}

.idea-meta dt {
  font-size: 12px;
  color: var(--text-muted);
}

.idea-meta dd {
  margin: 0;
}

.idea-sources {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 4px;
}

.idea-sources li {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: baseline;
}

.idea-source-ref {
  font-size: 12px;
  color: var(--text-muted);
}

.idea-node-link + .idea-node-link,
.idea-node-link + .idea-node-missing,
.idea-node-missing + .idea-node-link {
  margin-left: 8px;
}

.idea-outcome-note {
  margin-left: 8px;
}

.idea-dates {
  margin: 10px 0 0;
  font-size: 12px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
```

若 `--surface-2` / `--surface-3` / `--border` / `--radius` / `--text-muted` 中有变量名与 style.css 顶部的 `:root` 定义不符，以文件里实际定义的变量名为准（`grep -n '^\s*--' style.css | head -40` 查看）——**不得新增 CSS 变量**，只复用既有调色板，dark mode 才会自动跟随。

- [ ] **Step 8: 运行确认通过**

Run: `python -m pytest tests/test_ideas_ui.py -v`
Expected: PASS

- [ ] **Step 9: 全量回归**

Run: `python -m pytest`
Expected: 全绿。若 `tests/test_generator.py` 或 `tests/test_html_smoke.py` 失败——它们跑的是无想法的 demo 项目，失败即说明条件化没生效，回到 Step 5e 检查。

- [ ] **Step 10: Commit**

```bash
git add src/planning_control_plane/model.py src/planning_control_plane/cli.py \
        src/planning_control_plane/generator.py \
        src/planning_control_plane/templates/ideas.html \
        src/planning_control_plane/templates/static/style.css \
        tests/test_ideas_ui.py
git commit -m "feat(ideas): conditional ideas page with shared IDEA-D61 ordering"
```

---

### Task 4: 侧栏条件化入口 + 阶段 2 向后兼容验收

**Files:**
- Modify: `src/planning_control_plane/templates/base.html:81-82`（`</nav>` 之后、`</aside>` 之前）
- Modify: `src/planning_control_plane/templates/static/style.css`（`.sidebar-extra` 样式）
- Modify: `tests/test_lang_v012.py`（受控扩展）
- Create: `tests/fixtures/phase1_style.css`（阶段 1 stylesheet 的字节副本，**必须从 `main` 抓**，见 Step 1b）
- Test: `tests/test_ideas_ui.py`（追加）

**Interfaces:**
- Consumes: `has_ideas` / `is_ideas` / `base.ideas`（Task 3 Step 5d 已放进 `_base_context`）
- Produces: 无新 Python 符号；侧栏入口的 DOM 契约由测试固定（`class="sidebar-extra"`、`data-i18n="ideas.nav"`）

规范锚点：IDEA-D54（侧栏独立入口，位于规划树之外的独立区段，MVP 不带计数徽标）、IDEA-D63（条件化）、不变量 §59.4 阶段 2。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_ideas_ui.py`：

```python
# ------------------------------------------------- IDEA-D54 sidebar entry


def test_sidebar_entry_appears_on_every_page_of_an_ideas_project(ideas_dist):
    for name in ("index.html", "ideas.html", "nodes/P1.html"):
        page = _page(ideas_dist, name)
        assert 'class="sidebar-extra"' in page, name
        assert 'data-i18n="ideas.nav"' in page, name


def test_sidebar_entry_sits_outside_the_planning_tree(ideas_dist):
    """IDEA-D54: a separate section, not a tree node — the sidebar tree
    stays the planning graph and nothing else (invariant 3)."""
    page = _page(ideas_dist, "index.html")
    tree = page[page.index('id="planning-tree"'):page.index("</ul>", page.index('id="planning-tree"'))]
    assert "sidebar-extra" not in tree
    assert page.index('id="planning-tree"') < page.index('class="sidebar-extra"')


def test_sidebar_entry_carries_no_count_badge(ideas_dist):
    """IDEA-D54: MVP has no count badge on the entry."""
    page = _page(ideas_dist, "index.html")
    entry = page[page.index('class="sidebar-extra"'):]
    entry = entry[: entry.index("</nav>")]
    assert not re.search(r"\d", entry)


def test_ideas_page_marks_its_own_sidebar_entry_as_current(ideas_dist):
    page = _page(ideas_dist, "ideas.html")
    assert re.search(r'class="sidebar-extra-link"[^>]*aria-current="page"', page)
    assert 'href="index.html" aria-current="page"' not in page  # topbar Overview is not current


# ------------------------------ invariant §59.4 phase 2: no-ideas projects


@pytest.fixture
def plain_dist(demo_root, tmp_path):
    """The shipped demo project — seven nodes, no ideas/ directory."""
    from planning_control_plane.loader import load_project

    project = load_project(demo_root)
    dist = tmp_path / "plain-dist"
    generator.build_site(project, dist)
    return dist


def test_no_ideas_project_keeps_the_exact_phase1_file_list(plain_dist):
    """'No new page' in its literal, checkable form."""
    files = sorted(p.relative_to(plain_dist).as_posix() for p in plain_dist.rglob("*") if p.is_file())
    assert files == [
        "assets/app.js",
        "assets/style.css",
        "index.html",
        "nodes/P1.html",
        "nodes/P2-A.html",
        "nodes/P2-A1.html",
        "nodes/P2-A2.html",
        "nodes/P2-A3.html",
        "nodes/P2-A4.html",
        "nodes/P2.html",
    ]


def test_no_ideas_pages_contain_no_idea_markup_outside_the_payload(plain_dist):
    """'No new navigation entry, no new visible content' — the i18n payload
    is the one allowed increment (invariant §59.4 phase 2), so it is cut out
    before the check."""
    for path in sorted(plain_dist.rglob("*.html")):
        page = path.read_text(encoding="utf-8")
        body = re.sub(
            r'<script type="application/json" id="pcp-i18n">.*?</script>', "", page, flags=re.DOTALL
        )
        assert "idea" not in body.lower(), path.name


def test_idea_css_cannot_restyle_pages_that_have_no_ideas(plain_dist):
    """style.css is a shared asset, so the idea rules ship to every project.
    They are inert there only if every selector is namespaced — this pins
    that, so a future edit cannot silently restyle existing pages."""
    css = (plain_dist / "assets" / "style.css").read_text(encoding="utf-8")
    block = css[css.index("/* ----------------------------------------------------------- idea layer */"):]

    # The selector regex below cannot see a single-line at-rule: `@` is not
    # in its character class, so `@media print { body { … } }` is skipped
    # whole. (A *multi-line* at-rule still trips the check, because its
    # indented inner selectors do match.) The idea layer needs no at-rule
    # at all — it styles with the existing tokens, which style.css already
    # redefines under `@media (prefers-color-scheme: dark)`, so dark mode
    # follows for free. Needing one here would mean someone introduced a
    # hard-coded colour: exactly when a review should happen.
    assert "@media" not in block and "@keyframes" not in block and "@import" not in block

    selectors = re.findall(r"^([.\w\[\]\"=~^$*|:>+ ,-]+)\{", block, flags=re.MULTILINE)
    for selector in selectors:
        for part in selector.split(","):
            part = part.strip()
            assert part.startswith((".idea-", ".ideas-", ".sidebar-extra")), part


def test_idea_css_is_append_only_over_phase1(plain_dist):
    """The prefix check above proves new rules stay inert; this proves no
    *existing* rule was rewritten. Together they are 'append only'.

    The fixture is the phase-1 stylesheet captured byte-for-byte from
    ``main``. It is not frozen forever: a later, unrelated UI change may
    legitimately edit existing rules — but it must then update this fixture
    **in its own commit**, which is precisely the visibility this gate
    exists to force. What it must never do is drift silently as a
    side effect of idea-layer work.
    """
    built = (plain_dist / "assets" / "style.css").read_bytes()
    phase1 = (Path(__file__).parent / "fixtures" / "phase1_style.css").read_bytes()
    assert built.startswith(phase1)
```

模块顶部的导入需要加 `Path`（当前只有 `re` / `pytest` / `generator` / `i18n` / `IdeaStatus`）：

```python
from pathlib import Path
```

两侧都用 `read_bytes()` 而不是 `read_text().encode()`：文本模式默认开 universal newlines，CRLF 会在读取时被折成 LF，往返后字节与 fixture 不等——那是假红。

- [ ] **Step 1b: 从 main 抓 fixture（顺序至关重要）**

Task 3 Step 7 **已经**往 `style.css` 追加过想法层样式块。因此**不得**复制工作区当前的文件——那会把 Task 3 的追加烤进基线，闸门从此永远绿，且是自证式的绿。必须从 main 取：

```bash
mkdir -p tests/fixtures
git show main:src/planning_control_plane/templates/static/style.css > tests/fixtures/phase1_style.css
# 自检：基线必须是当前文件的真前缀，且严格短于它
python - <<'EOF'
import pathlib
a = pathlib.Path("tests/fixtures/phase1_style.css").read_bytes()
b = pathlib.Path("src/planning_control_plane/templates/static/style.css").read_bytes()
assert b.startswith(a) and len(b) > len(a), "fixture 不是 main 版本，或 Task 3 的追加没生效"
print(f"OK: baseline {len(a)} bytes, current {len(b)} bytes")
EOF
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_ideas_ui.py -k "sidebar_entry or no_ideas or idea_css" -v`
Expected: 侧栏相关用例 FAIL —— `'class="sidebar-extra"' in page` 断言失败（模板还没有该区段）。**两个 `idea_css_` 用例此时应当 PASS**：前缀闸在 Task 3 的样式块上已成立，append-only 闸在只追加的前提下也成立。它们是回归护栏，不参与本步的红绿确认——看到 `-k` 选出的用例里有绿的，不代表条件化提前生效了。

- [ ] **Step 3: base.html 加条件化侧栏区段**

在 `</nav>`（第 81 行）与 `</aside>`（第 82 行）之间插入：

```html
{% if has_ideas %}
    {# Idea layer entry (spec IDEA-D54): a section of its own, outside the
       planning tree — the tree is the planning graph and stays that way
       (invariant 3). Rendered only when the project actually has ideas
       (IDEA-D63), which is what keeps every existing project's pages
       unchanged. No count badge in the MVP. #}
    <nav class="sidebar-extra" aria-label="{{ t("ideas.nav_label") }}" data-i18n-attr="aria-label=ideas.nav_label">
      <a class="sidebar-extra-link" href="{{ base.ideas }}"{% if is_ideas %} aria-current="page"{% endif %} data-i18n="ideas.nav">{{ t("ideas.nav") }}</a>
    </nav>
{% endif %}
```

- [ ] **Step 4: 加侧栏入口 CSS**

在 Task 3 追加的 idea layer 样式块**内部**（同一注释段下）追加，保持前缀约束：

```css
.sidebar-extra {
  border-top: 1px solid var(--border);
  margin-top: 8px;
  padding: 8px 12px;
}

.sidebar-extra-link {
  display: block;
  padding: 4px 6px;
  border-radius: var(--radius);
  color: var(--text-muted);
  text-decoration: none;
  font-size: 13px;
}

.sidebar-extra-link:hover,
.sidebar-extra-link:focus-visible {
  color: var(--text);
  background: var(--surface-3);
}

.sidebar-extra-link[aria-current="page"] {
  color: var(--text);
  font-weight: 600;
}
```

- [ ] **Step 5: 让 ideas 页接受既有 LANG 契约审计**

`tests/test_lang_v012.py` 两处受控扩展——目的是让 ideas 页和其他页一样，被「每个 `data-i18n` 键都必须在两个语言表里存在」「每页都嵌完整双语表」等既有契约覆盖。

5a. `_build()` 里给 `make_project` 加想法数据（`_build` 定义在第 70 行）：

```python
def _build(make_project, tmp_path, locale, name):
    room = tmp_path / name
    room.mkdir()
    project, root = make_project(
        room,
        config_dict=_config(locale),
        node_dicts=_nodes(),
        # The ideas page must pass the same LANG contracts as every other
        # page, so the fixture carries one idea (spec §61 / IDEA-D56).
        raw_files={
            "ideas/IDEA-L1.yaml": (
                "id: IDEA-L1\n"
                "title: Lang fixture idea 语言夹具\n"
                "status: OPEN\n"
                "detail: Author text that no locale may translate.\n"
                "relates_to: [LEAF]\n"
                "last_updated: 2026-08-28\n"
            )
        },
    )
    dist = root / ".planning" / "dist"
    generator.build_site(project, dist)
    return dist
```

5b. `ALL_PAGES`（第 110 行）加 ideas 页：

```python
ALL_PAGES = ("index.html", "ideas.html", "nodes/LEAF.html")
```

- [ ] **Step 6: 运行确认通过**

Run: `python -m pytest tests/test_ideas_ui.py tests/test_lang_v012.py -v`
Expected: PASS。若 `test_every_marked_key_and_attribute_key_exists_in_the_payload` 报某个键不存在，说明 Task 2 漏了词条——补进 `_EN` 和 `_ZH_CN` 两张表（键集必须一致）。

- [ ] **Step 7: 全量回归**

Run: `python -m pytest`
Expected: 全绿

- [ ] **Step 8: Commit**

```bash
git add src/planning_control_plane/templates/base.html \
        src/planning_control_plane/templates/static/style.css \
        tests/test_lang_v012.py tests/test_ideas_ui.py
git commit -m "feat(ideas): conditional sidebar entry; pin phase-2 backward compatibility"
```

---

### Task 5: `pcp build` 汇总行 + README 双语更新

**Files:**
- Modify: `src/planning_control_plane/cli.py:600-604`
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Test: `tests/test_ideas_ui.py`（追加）

**Interfaces:**
- Consumes: `project.ideas`（阶段 1）
- Produces: 无新符号

规范锚点：§62.1 阶段 2 交付项「README en/zh 更新」；阶段 1 复核记录的「README 未列 `pcp ideas`」缺口在此补齐。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_ideas_ui.py`：

```python
# ------------------------------------------------------- build summary line


def test_build_summary_counts_the_ideas_page(make_project, tmp_path, cli):
    project, root = make_project(
        make_project_room(tmp_path),
        node_dicts=IDEA_NODES,
        raw_files={"ideas/IDEA-1.yaml": "id: IDEA-1\ntitle: T\nstatus: OPEN\n"},
    )
    code, out, _err = cli("-p", str(root), "build")
    assert code == 0
    assert "+ ideas page" in out


def test_build_summary_omits_the_ideas_page_without_ideas(make_project, tmp_path, cli):
    _project, root = make_project(make_project_room(tmp_path), node_dicts=IDEA_NODES)
    code, out, _err = cli("-p", str(root), "build")
    assert code == 0
    assert "ideas" not in out
```

`make_project` 的第一个参数是 `tmp_path`，两个测试在同一 `tmp_path` 下会互相覆盖，因此加一个小助手放在文件的 fixtures 区：

```python
def make_project_room(tmp_path, name=None):
    """A fresh sub-directory so two builds in one test module never share
    a repository root."""
    room = tmp_path / (name or "room")
    room.mkdir(exist_ok=True)
    return room
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_ideas_ui.py -k build_summary -v`
Expected: FAIL —— `assert "+ ideas page" in out`（当前汇总行是 `(index + N node pages + assets)`）

- [ ] **Step 3: 改汇总行**

`cli.py` 的 `cmd_build` 中：

```python
    ideas_part = " + ideas page" if project.ideas else ""
    print(
        f"Built {len(paths)} files into {out_display} "
        f"(index + {len(project.nodes)} node pages{ideas_part} + assets)"
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_ideas_ui.py -k build_summary -v`
Expected: PASS

- [ ] **Step 5: README.md（英文）**

5a. CLI 表格（`## CLI` 小节，`pcp focus` 一行之后）插入：

```markdown
| `pcp ideas [--status S] [--for NODE [--subtree]]` | List the idea layer, grouped by status. `--for` selects ideas related to a node or its ancestors; `--subtree` switches to the node's subtree |
```

5b. 在 `## Planning Model` 小节之前插入新小节：

```markdown
## Idea Layer

Planning nodes are a *post-decision* control system: a node exists because
something was already committed to. The idea layer holds what comes before
that — captured thinking that has not earned a place in the plan yet.

```
.planning/ideas/IDEA-0007.yaml     # one file per idea
```

```yaml
id: IDEA-0007
title: Add a trend comparison view to the dashboard
status: OPEN                       # OPEN | PARKED | PROMOTED | DISCARDED
detail: One paragraph. Capture asks for no structure.
relates_to: [P2]                   # the node this thought was born from
benchmark_sources:                 # what mature products actually do
  - ref: docs/benchmarks/grafana-panels.md
    note: Grafana's time-compare panel shows the demand is stable
  - note: Stripe's month-over-month dashboard      # outside the repo: note only
methodology_sources:               # why it holds, decoupled from any product
  - ref: docs/method/heuristics.md
outcome: ~                         # set when the idea graduates into a node
created: 2026-08-27
last_updated: 2026-08-27
```

Four properties are deliberate:

- **Capture has no gate.** Empty justification slots are a valid state, and
  they produce no warning.
- **One bridge.** An idea enters the planning graph only by graduating:
  create the node, then point `outcome.node` at it. Nodes never reference
  ideas back, so reading the plan never drags in unfinished thinking.
- **Ideas cannot break the plan.** A malformed idea file becomes a
  validation issue and is skipped — `pcp status`, `pcp context` and
  `pcp build` keep working, and idea-layer errors never block a build.
- **Ideas are never in a capsule.** `pcp context` carries planning data
  only; `pcp ideas --for <node>` is the separate, deliberate second lookup.

The generated site gets an `ideas.html` page and a sidebar entry — only
when the project actually has ideas.
```

（注意：上面代码块内部的三反引号在实际 README 中是正常嵌套；写入时保持原样。）

5c. `## Features` 列表末尾追加一条：

```markdown
- **Idea layer** — `.planning/ideas/` captures uncommitted thinking with
  benchmark and methodology justification slots; `pcp ideas` lists and
  triages it, and a bad idea file can never block the plan
```

- [ ] **Step 6: README.zh-CN.md（中文）**

在与英文版**对应位置**做同样三处改动。中文措辞：

```markdown
| `pcp ideas [--status S] [--for NODE [--subtree]]` | 按状态分组列出想法层。`--for` 选出与某节点或其祖先相关的想法，`--subtree` 切换为该节点的子树方向 |
```

```markdown
## 想法层

规划节点是**决策之后**的控制系统：节点存在，是因为某件事已经被承诺。想法层
承载在此之前的东西——已经捕获、但还没有资格进入计划的思考。

（YAML 示例与英文版相同，注释译为中文）

四条性质是刻意的：

- **捕获零门槛。** 论据槽全空是合法状态，不产生任何 WARNING。
- **只有一座桥。** 想法进入规划图的唯一途径是毕业：先建节点，再把
  `outcome.node` 指向它。节点永不反向引用想法，因此读计划不会牵扯到未完成的
  思考。
- **想法弄不坏计划。** 想法文件格式错误只会降级为一条校验 issue 并跳过该文件，
  `pcp status` / `pcp context` / `pcp build` 照常工作；想法层 ERROR 也不阻断构建。
- **capsule 永不含想法。** `pcp context` 只携带规划数据；
  `pcp ideas --for <node>` 是另一次显式的、有意的查询。

生成站点会多出 `ideas.html` 页与侧栏入口——仅当项目确实有想法时才出现。
```

Features 列表对应追加：

```markdown
- **想法层** —— `.planning/ideas/` 捕获尚未承诺的思考，带对标与方法论两个论据槽；
  `pcp ideas` 负责列出与分诊，坏的想法文件永远不会阻断计划
```

- [ ] **Step 7: 检查 README 双语结构一致**

Run:

```bash
grep -c '^| `pcp' README.md README.zh-CN.md
grep -n '^## ' README.md README.zh-CN.md | sed 's/:.*## /  /' | head -40
```
Expected: 两个文件的 CLI 表格行数相同；小节标题一一对应（`Idea Layer` ↔ `想法层`）。

- [ ] **Step 8: 全量回归**

Run: `python -m pytest`
Expected: 全绿

- [ ] **Step 9: Commit**

```bash
git add src/planning_control_plane/cli.py README.md README.zh-CN.md tests/test_ideas_ui.py
git commit -m "docs(ideas): document the idea layer in both READMEs; count the ideas page in build output"
```

---

### Task 6: 阶段 2 验收 + spec R3 备注

**Files:**
- Modify: `docs/superpowers/specs/ideas-spec-draft.zh-CN.md`（附录 D 增加 R3 一节）
- Modify: `docs/superpowers/plans/2026-08-28-ideas-phase2-projection.md`（本文件，追加执行记录）
- Test: 无新测试文件；本任务是端到端验收

**Interfaces:**
- Consumes: Task 1–5 的全部产出
- Produces: 验收记录 + 一条 spec 修订

- [ ] **Step 1: 跑全量测试**

Run: `python -m pytest`
Expected: 全绿。记录总数（预计 301 + 阶段 2 新增约 25 = 约 326）。

- [ ] **Step 2: 物理验证不变量 1/2/3**

Run:

```bash
git diff --stat main -- src/planning_control_plane/context.py src/planning_control_plane/graph.py
git diff main -- src/planning_control_plane/model.py | grep -E '^[-+]' | grep -vE '^[-+]{3}' | grep -iE 'class Node|tracks|objective|scope|next_action|blocking_decisions|evidence_sources'
```
Expected: 第一条输出为空（`context.py` / `graph.py` 零改动）；第二条无 `Node` 字段级增删（只应命中 `Idea` 的 docstring 文字）。

- [ ] **Step 3: 手工验收不变量 4（阶段 2 口径）**

Run:

```bash
SP=$(mktemp -d)
git worktree add -f "$SP/base" main
SITE=$(python -c "import site;print(site.getsitepackages()[0])")
cat > "$SP/run_base.py" <<EOF
import sys
sys.path[:0] = ["$SP/base/src", "$SITE"]
from planning_control_plane.cli import main
sys.exit(main())
EOF
cp -r examples/demo-project "$SP/A"; cp -r examples/demo-project "$SP/B"
rm -rf "$SP/A/.planning/dist" "$SP/B/.planning/dist"
(cd "$SP/A" && python -S "$SP/run_base.py" build) >/dev/null
(cd "$SP/B" && python -m planning_control_plane.cli build) >/dev/null
diff -r "$SP/A/.planning/dist" "$SP/B/.planning/dist"
```

Expected（阶段 2 口径下**允许**的差异，逐条确认，不得有第四类）：

1. 每个 `.html` 只在 `<script type="application/json" id="pcp-i18n">` 的内容上不同（多出 `ideas.*` / `idea_status.*` 词条）；
2. `assets/style.css` 只有**新增行**，无删除、无修改行；
3. 文件清单完全一致（无 `ideas.html`）。

第 2 点现在已有 Task 4 的 `test_idea_css_is_append_only_over_phase1` 作为永久回归闸；此处的手工命令是端到端复核（比对的是**真实构建产物**，而非源文件），两者互补，都要跑：

```bash
diff --unchanged-line-format= --old-line-format='DELETED:%L' --new-line-format='' \
  "$SP/A/.planning/dist/assets/style.css" "$SP/B/.planning/dist/assets/style.css"
```
Expected: 无输出（没有被删除或改写的行）。

验证第 1 点：

```bash
python - <<'EOF'
import re, sys, pathlib
A = pathlib.Path(sys.argv[1]); B = pathlib.Path(sys.argv[2])
strip = lambda t: re.sub(r'<script type="application/json" id="pcp-i18n">.*?</script>', "", t, flags=re.S)
for a in sorted(A.rglob("*.html")):
    b = B / a.relative_to(A)
    assert strip(a.read_text("utf-8")) == strip(b.read_text("utf-8")), a.name
print("all html identical outside the i18n payload")
EOF
```
（把两个 dist 路径作为参数传入。）

跑完清理：`git worktree remove --force "$SP/base"; rm -rf "$SP"`

- [ ] **Step 4: 人眼验收生成的页面**

Run:

```bash
rm -rf /tmp/pcp-ideas-demo && cp -r examples/demo-project /tmp/pcp-ideas-demo
mkdir -p /tmp/pcp-ideas-demo/.planning/ideas
cat > /tmp/pcp-ideas-demo/.planning/ideas/IDEA-0007.yaml <<'EOF'
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
(cd /tmp/pcp-ideas-demo && python -m planning_control_plane.cli build)
```

打开 `/tmp/pcp-ideas-demo/.planning/dist/ideas.html`，确认：侧栏出现「Ideas」入口且高亮为当前页；分组顺序 OPEN → PARKED → PROMOTED → DISCARDED；`relates_to` 的 P2 是可点链接；`ref` 是纯文本；切到中文后状态显示为 `开放 OPEN`，而 id / 标题 / detail / note 保持英文原文。同时打开 `index.html` 确认 dashboard 上没有任何想法内容。

- [ ] **Step 5: spec 追加 R3 修订记录**

`docs/superpowers/specs/ideas-spec-draft.zh-CN.md` 的附录 D 末尾（D.5 之后）追加：

```markdown
### D.6 修订记录 R3（阶段 2 实施发现）

| # | 改动 | 依据 |
| --- | --- | --- |
| 1 | 不变量 §59.4 阶段 2 的「允许的唯一差异是 i18n payload」补一条：`assets/style.css` 允许**只增不改**的想法层样式增量，且全部选择器须以 `.idea-` / `.ideas-` / `.sidebar-extra` 前缀命名 | `style.css` 是全站共享的单一静态资源，由 `build_site()` 逐字节复制进每个项目的 dist（`generator.py:77` 的 `_STATIC_FILES` + `generator.py:702-704` 的复制循环，docstring `generator.py:671` 明写 "copied verbatim"）。想法页与侧栏入口需要样式，而侧栏入口出现在有想法项目的**每一个**页面上（含节点页），因此样式必然作用到全站。选择器前缀约束使这些规则在无想法项目上不匹配任何元素——「页面结构与可见内容不变」的实质因此成立，字节层面则与 i18n payload 属同一类不可避免的共享资源增量。「只增不改」由两道闸合起来固定：`test_idea_css_cannot_restyle_pages_that_have_no_ideas`（新增规则不外溢——前缀 + 禁 at-rule）与 `test_idea_css_is_append_only_over_phase1`（既有规则不被改写——对 `main` 版 stylesheet 的字节前缀断言）。<br><br>**落选方案与否决理由**（照 R1 第 1 条的体例记全，以免后续评审重开同一条杠）：<br>① **条件化独立 `ideas.css`**——字面上最干净（不变量 4 一字不改），但要给 `_STATIC_FILES` 的无条件复制循环开洞、打破 `generator.py:671` "copied verbatim" 的建产线契约，使资产集合随项目而变。那是**主 spec §22 层面**的改动，本补章无权自行修改；用主 spec 的永久复杂度换补章的一行修订，方向反了。<br>② **样式内联进 `ideas.html`**——覆盖不到节点页：侧栏入口出自全站共享的 `base.html`，有想法项目的每个页面都渲染它。<br>③ **放弃侧栏入口、只从 dashboard 进**——既推翻 IDEA-D54，又**不消除冲突**：`ideas.html` 自身的样式照样要进 `style.css`，无想法项目的字节照样变。只有叠加方案 ② 才成立，等于两笔成本换免写一条修订 |
| 2 | IDEA-D54 的「侧栏独立入口」明确为：位于侧栏规划树 `<nav>` 之后的独立 `<nav class="sidebar-extra">` 区段，条件化渲染 | 规划树 `<nav>` 内新增任何条目都会让想法进入侧栏规划树，与不变量 3 冲突 |
| 3 | 记录阶段 2 的排序实现：`IDEA-D61` 的排序键实现为 `model.idea_sort_key()`，CLI 与 ideas 页共用同一函数 | 「CLI 与 ideas 页使用同一排序」若靠两处各写一遍，只能靠纪律维持；提到共享函数后由 `test_idea_sort_key_is_shared_by_cli_and_generator` 固定 |

同时给 D.4 那条未决裁定加一句状态标记（附录 D.4 段末追加）：

> **状态（R3 时点）：仍未裁定，且「把 `pcp validate` 接进 CI」是它的触发条件。** 阶段 1、阶段 2 均未改动 `pcp validate` 的退出码协议，`IDEA-D59` 的不对称（validate 退出 1 而 build 退出 0）是刻意的，不变量 §59.6 本就只保 `pcp status` / `pcp context` / `pcp build`。接 CI 时的建议方向是**给 `pcp validate` 加作用域旗标**（D.4 自己提的方案），而不是改默认退出码——人工执行 validate 应保持最大信息量，CI 门禁用旗标绕开想法层。**在裁定之前不得把 `pcp validate` 作为 CI 门禁**，否则一个坏想法文件会让门禁失败。

修订表头「修订」一栏同步追加：`R3：阶段 2 实施发现的三条落地约束 + D.4 的 CI 触发条件标记，见附录 D.6`。
```

- [ ] **Step 6: 追加本计划的执行记录**

在本文件末尾追加一节，记录实际测试数、计划内修正、评审驱动的增量与验收结果——格式参照阶段 1 计划的「执行记录」小节。

- [ ] **Step 7: 最终全量回归**

Run: `python -m pytest && python -m pytest --collect-only -q | tail -1`
Expected: 全绿，记录最终用例总数

- [ ] **Step 8: Commit**

```bash
git add docs/superpowers/specs/ideas-spec-draft.zh-CN.md \
        docs/superpowers/plans/2026-08-28-ideas-phase2-projection.md
git commit -m "docs(ideas): record phase-2 acceptance and spec R3 amendments"
```

---

## Self-Review

**1. Spec 覆盖（阶段 2 范围）**

| spec 条目 | 任务 |
| --- | --- |
| §61 IDEA-D54（ideas 页 + 侧栏入口 + 字段 + 分组 + 排序） | Task 3（页）、Task 4（入口） |
| §61 IDEA-D55（不外溢到节点页/dashboard/焦点/capsule/规划树） | Task 3 `test_ideas_never_reach_node_pages_or_the_dashboard`、Task 4 `test_sidebar_entry_sits_outside_the_planning_tree` |
| §61 IDEA-D56（i18n 双语 + 原始枚举并陈 + 语言不碰数据） | Task 2（词条）、Task 3（badge 标记）、Task 4（LANG 契约审计） |
| §61 IDEA-D63（投影条件化） | Task 3 Step 5e + 两个条件化测试 |
| §60 IDEA-D61（CLI 与页面同一排序） | Task 3 `model.idea_sort_key` + 共享性测试 |
| §59.4 阶段 2（向后兼容收窄口径） | Task 4 的三个 `plain_dist` 测试 + Task 6 Step 3 手工 A/B |
| §59.5（确定性） | Task 3 `test_build_with_ideas_is_deterministic` + 既有 `test_generator.py` |
| §59.1/2/3（capsule / Node / 规划语义纯净） | Task 6 Step 2 物理验证 |
| §62.1 阶段 2 交付「README en/zh 更新」 | Task 5 |
| §62.2 模块影响面（generator/templates/i18n/cli） | Task 2–5 逐一对应；`context.py` / `graph.py` 零改动由 Task 6 Step 2 验证 |
| 阶段 1 复核遗留（F1/F2/F3） | Task 1 |

**不在本计划范围**（spec 明示归阶段 3 或 PLAN 世界）：`pcp graduate`（§62.3）、`pcp close` / 时刻 B 制度化（§57.3、§62.3）、`CANCELLED` 终态（§56.3、IDEA-D43）。

**未解决、需在阶段 2 之外裁定的一项**：spec 附录 D.4 记录的 `pcp validate` 退出码问题——想法层 ERROR 使 `pcp validate` 退出 1，若把它用作 CI 门禁，坏想法文件会让门禁失败，而 `pcp build` 不受影响。本计划**不动**这条（IDEA-D59 明写「刻意的不对称」），但 Task 6 Step 5 会给 D.4 补一句状态标记，把触发条件写死为「把 `pcp validate` 接进 CI 之前必须先裁定」，并记下建议方向（加作用域旗标，而不是改默认退出码），免得它在接 CI 那天变成隐形炸弹。

**2. 占位符扫描**

无 TBD / TODO / 「类似 Task N」/ 无代码的代码步骤。Task 3 Step 6 有一处**刻意的自我更正**（先给出用 `ref.id` 拼 href 的写法，紧接着说明必须改用 `ref.url`）——实现时**只采用 `ref.url` 版本**；保留前一版是为了让实现者看到这个陷阱本身（`_safe_stem` 与 id 不总相等）。Task 3 Step 7 的 CSS 变量名有一句条件说明（以 style.css 实际定义为准），附了查看命令，不是占位符。

**3. 类型一致性**

- `idea_sort_key(idea: Idea) -> tuple[bool, str, str]` 在 Task 3 Step 3 定义，Task 3 Step 4（cli 别名）、Step 5b（`_ideas_context`）、Task 3 测试三处使用，签名一致。
- `i18n.idea_status_label(locale, status)` / `i18n.idea_status_key(status)` 在 Task 2 定义，Task 3 Step 5b 使用，参数顺序与 `status_label` / `status_key` 先例一致。
- `_idea_view()` 产出的键（`id/title/detail/status/relates_to/outcome/benchmark_sources/methodology_sources/created/last_updated`）与 `ideas.html` 模板消费的键逐一对应；`outcome` 为 `{"ref": <node_ref dict>, "note": str}`，模板用 `idea.outcome.ref.known` / `.url` / `.id` / `.title`，与 `_node_ref` 的返回键一致。
- `_base_context(ctx, current_page_id, is_ideas_page=False)` 新增的第三个参数有默认值，`_index_context` / `_node_context` 的既有调用点无需改动——这正是无想法项目字节级不变的前提。
- `groups` 元素结构 `{"status": {"raw","label","i18n"}, "count": int, "ideas": [...]}` 在 Task 3 Step 5b 定义，`ideas.html` 与 Task 4 的分组测试一致。

---

## 执行记录（2026-08-28，subagent-driven 执行后追加）

分支 `feat/ideas-phase2-projection`（自 `main` = `4a385a6` 切出），共 11 个实现提交 + 本执行记录提交。环境同阶段 1（uv venv，CPython 3.14.3 + pytest 9.1.1 + PyYAML 6.0.3）。

**实际测试数（按 Task 收官口径，`python -m pytest` 全绿）：**

- Task 1 后 302（main 基线 297 + CLI 侧新增）；Task 2 后 308；Task 3 后 321（评审 51864b0 再 +3 → 324）；Task 4 后 332；Task 5 后 334；Task 6 复核仍 334。终态分布：`tests/test_ideas.py` 73 + `tests/test_ideas_ui.py` 32 + 既有 229。

**计划内修正（计划文本自身缺陷，实现时以计划自己的测试契约为准，逐条经独立评审裁定）：**

1. **scoped 隐藏计数含文件级失败**（Task 1）：计划的代码片段把文件级加载失败计入 `--for` 作用域的隐藏记录数，而计划自己的测试断言该提示缺席——裁定为文件级失败不进作用域清单（全局计数仍含）。
2. **提示文案缺被断言的子串**（Task 1）：计划的文案串缺少其测试断言的 "could not be loaded"——实际文案为 `idea files exist but could not be loaded; run 'pcp validate'`。
3. **既有测试钉死了旧措辞**（Task 1）：`test_cli_ideas_notes_broken_idea_file_in_empty_state` 对同一输入钉住旧文案，与新测试互斥——更新该既有断言中冲突的一处（全分支仅有的两处授权既有测试编辑之一，另一处在 51864b0）。
4. **期望排序字面量自相矛盾**（Task 3）：计划期望 `[..., "IDEA-DANGLING", "IDEA-0003"]`，与 IDEA-D61 键自身的无日期 id 决胜（`"IDEA-0003" < "IDEA-DANGLING"`）矛盾——修正为 `[..., "IDEA-0003", "IDEA-DANGLING"]`（与 CLI 输出一致，docstring 要求 CLI/页面同一顺序）；同 Task 计划的测试数估计（新增 14 / 总 322）差一（实为 13 / 321）。
5. **无计数徽章测试误报**（Task 4）：计划用 `\d` 裸 grep 原始 HTML，而 `data-i18n` 属性名本身含数字——改为对剥离标签后的可见文本断言。
6. **文件清单转写重复**（Task 4）：计划的文件清单块有一处转写重复——采用经实证核对的正确清单。

**评审驱动的增量（超出计划文本、经评审批准的提交）：**

- `2809d04`（Task 1 评审）：+1 回归测试（坏状态想法命中 `--for` 作用域时仍计数）；状态过滤空态恢复 `(subtree)` 标记。
- `6349f06`（Task 2 评审）：以跨枚举循环替换同义反复的前缀集合交集（每个 IdeaStatus 值 → `status_key` 为 None；每个 NodeStatus 值 → `idea_status_key` 为 None）。
- `51864b0`（Task 3 评审）：删除 `_idea_view` 未消费的 `status` 键与两语言中死掉的 `ideas.detail` 词条（同步 Task 2 的必需键集——第二处授权既有测试编辑）；+3 测试（空分组丢弃 / 未知 outcome 以文本呈现 / relates_to 去重）；`list[IdeaSource]` 类型标注；ideas 页复用 `index_ctx`；`.idea-node-missing + .idea-node-missing` 相邻规则。
- `7eef56e`（Task 4 评审）：全部经变异测试验证——选择器提取重写（剥注释、取 `}`/`{` 之间片段 + 首前缀，可捕获 `#id`、`:not()`、跨行分组）；at-rule 禁令放宽为行首任意 `@`；树放置测试重绑到 sidebar-nav 元素边界；闭合两道 CSS 闸之间的 1 字节缝隙（`built[:marker] == phase1 + b"\n"`）；标记守卫常量化；hover 对齐 `--surface-2`；补说明性注释。
- `cafefd2`（Task 5 评审，spec 保真一行）：build 摘要缺省测试补 nodes 前置条件。
- `fd5e93b`（Task 5 评审收尾）：两个 build 摘要测试改精确括号断言；`make_project_room` docstring 更正；README CLI 行注明 `--for` 不带 `--status` 时仅列 OPEN+PARKED；树注释注明直接位于 ideas/ 下的 `.yaml`。

**验收结果（Task 6，Step 1–4 全部通过）：**

- **Step 1 全量测试**：334 passed（计划估约 326，实记 334）。
- **Step 2 不变量 1/2/3 物理验证**：`git diff --stat main -- context.py graph.py` 输出为空（两文件零改动）；`model.py` 对 `main` 仅 17 行新增，对 `class Node|tracks|objective|scope|next_action|blocking_decisions|evidence_sources` 的增删行 grep 零命中（唯一新增函数为 `idea_sort_key`）。
- **Step 3 A/B dist 对比**：`git worktree` 检出 `main`（`4a385a6`），以 `PYTHONPATH` 前置并用 `planning_control_plane.__file__` 显式核实 A 构建确用 worktree 代码；`examples/demo-project` 双份构建（A/B 各 10 文件，均无 ideas.html）。三类允许差异逐条确认，无第四类：(1) 剥离 `pcp-i18n` payload 后所有 `.html` 字节级一致；(2) `assets/style.css` 零删除/改写行（`DELETED:%L` 输出为空），A 1762 行 → B 1902 行（+140 全为追加）；(3) 文件清单完全一致。附加复核：payload 差异纯增量——每语言 +17 键（Task 2 的 18 键减去 51864b0 删除的死键 `ideas.detail`），全部 `ideas.*` / `idea_status.*` 前缀，0 删除 0 改写。
- **Step 4 人眼验收**：`ideas.html`——侧栏 `<nav class="sidebar-extra">` 的 Ideas 入口在本页带 `aria-current="page"`；分组仅 OPEN 出现（空分组已丢弃），组序 OPEN → PARKED → PROMOTED → DISCARDED；`relates_to` P2 渲染为指向 `nodes/P2.html` 的链接；benchmark/methodology 引用为纯文本 span（无指向 docs/ 的 href），仅含 note 的条目只渲染 note；payload `idea_status.OPEN` 中文为「开放」；id/title/detail/notes 等作者数据均无 `data-i18n`。`index.html`——侧栏入口存在（项目有想法）但不带 aria-current（页面上仅焦点树链接 `aria-current="true"` 与 Overview `aria-current="page"`，均为既有行为）；dashboard 主体无任何想法标记。zh-CN 变体（`ui.locale: zh-CN`）——徽章「开放」与原始 chip `OPEN` 并存，标题/导航为「想法」，本页 aria-current 正常。
- **Step 5 spec R3**：附录 D.6 三条修订（style.css 只增不改 + 前缀闸、`sidebar-extra` 独立 nav、`model.idea_sort_key()` 共享排序）+ D.4 的 CI 触发条件状态标记 + 头部修订行 R3；文中引用的 `generator.py` 行号按当前代码重核（`_STATIC_FILES` 81、复制循环 780-783、"copied verbatim" docstring 745），三道闸测试名经仓库核实存在。

**提交清单（11 个实现提交，旧 → 新）：**

| SHA | 说明 |
| --- | --- |
| `96f61eb` | fix(ideas)：隐藏记录提示收窄到清单；空态文案准确（3 处 CLI 展示修复 + 计划的 4 个测试） |
| `2809d04` | test(ideas)：钉死作用域坏状态计数；恢复 subtree 标记（评审） |
| `fe86dd4` | feat(ideas)：双语想法层词条与 `idea_status` 标签助手（18 键 ×2 语言，6 测试） |
| `6349f06` | test(ideas)：`idea_status` 命名空间守卫改跨枚举断言（评审） |
| `f04cf63` | feat(ideas)：条件化 ideas 页，CLI/页面共享 IDEA-D61 排序（13 测试） |
| `51864b0` | refactor(ideas)：删除未消费视图键；钉死分组丢弃、outcome 与去重行为（评审） |
| `fb153c8` | feat(ideas)：条件化侧栏入口；钉死阶段 2 向后兼容（+8 测试 + `plain_dist` fixture） |
| `7eef56e` | test(ideas)：堵闸测试盲区；对齐 sidebar hover token（评审加固） |
| `a6a9627` | docs(ideas)：双 README 记录想法层；build 输出计数 ideas 页（+2 测试） |
| `cafefd2` | test(ideas)：build 摘要缺省测试补 nodes 前置（spec 保真） |
| `fd5e93b` | test(ideas)：钉死精确 build 摘要行；README 注明 --for 默认过滤（评审收尾） |
