# PCP IDEA 子系统 · 阶段 1（引擎层）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 `specs/ideas-spec-draft.zh-CN.md`（含 R1/R2 修订）实现想法层的引擎与 CLI：Idea 数据模型、容错加载（失败域隔离）、9+9 条校验规则、只读的 `pcp ideas` 命令（两个查询方向）、focus/context 提示与 build 门禁豁免。

**Architecture:** 双世界单桥——想法是独立实体（`Idea`），与节点唯一的结构关联是想法侧的两条边（`relates_to` / `outcome.node`）。`Node`、`context.py`、`graph.py` 零改动；capsule、进度计数、焦点零感知想法。加载与校验逐条镜像节点侧先例，唯一刻意差异是失败域：坏想法文件降级为 issue，永不 `LoadError`。

**Tech Stack:** Python 3.11+ 标准库 + PyYAML（既有依赖）；pytest（既有 dev 依赖）。无新依赖。

**规范锚点:** 每个任务标注其实现的 `IDEA-D*` 编号。冲突时以 spec 为准，但不得静默偏离——发现 spec 与现实冲突时停下来报告。

**环境准备（一次性）:**

```bash
cd /home/asus/dev/planning-control-plane
source .venv/bin/activate        # 若无: python3 -m venv .venv && pip install -e ".[dev]"
git status                       # 应为 clean；specs/ 与本计划为未跟踪文件，属预期
git checkout -b feat/ideas-phase1-engine
python -m pytest                 # 基线：229 passed
```

**测试文件约定:** 全部新测试进 `tests/test_ideas.py`（每任务追加）。fixture 来自 `tests/conftest.py`：`make_project(tmp_path, config_dict=, node_dicts=, raw_files=, repo_files=)` 返回 `(project, repo_root)`，`raw_files` 的键是 `.planning/` 下的相对路径（写想法文件用 `{"ideas/X.yaml": "..."}`）；`cli(*argv)` 原地运行 CLI 返回 `(exit_code, stdout, stderr)`；`by_rule(issues, rule)` 过滤规则名。

---

### Task 1: model.py — Idea 数据模型、规则名封闭集与 issue 辅助函数

**Files:**
- Modify: `src/planning_control_plane/model.py`
- Test: `tests/test_ideas.py`（新建）

规范锚点：IDEA-D10（字段表）、D47/D64（issue 协议）、D23（IdeaStatus）、§58.1（IDEA_RULE_NAMES）。

- [ ] **Step 1: 写失败测试**

新建 `tests/test_ideas.py`：

```python
"""Idea layer tests (spec: specs/ideas-spec-draft.zh-CN.md, phase 1)."""

from planning_control_plane.model import (
    IDEA_RULE_NAMES,
    Idea,
    IdeaOutcome,
    IdeaSource,
    IdeaStatus,
    Severity,
    idea_issue,
)


def test_idea_defaults():
    idea = Idea(id="IDEA-1", title="First thought")
    assert idea.status == IdeaStatus.OPEN.value
    assert idea.detail == ""
    assert idea.relates_to == []
    assert idea.benchmark_sources == []
    assert idea.methodology_sources == []
    assert idea.outcome is None
    assert idea.created == ""
    assert idea.last_updated == ""
    assert idea.unknown_fields == []
    assert idea.source_file is None


def test_idea_source_and_default_outcome_shapes():
    entry = IdeaSource(ref="docs/a.md", note="n")
    assert IdeaSource() == IdeaSource(ref=None, note=None)
    assert IdeaOutcome(node="P2", note="") == IdeaOutcome(node="P2")


def test_idea_rule_names_form_the_documented_closed_set():
    # Spec §58.1: exactly these 18 rule names identify the idea layer
    # (IDEA-D59 build gate, IDEA-D64 message prefix). Guards drift.
    assert IDEA_RULE_NAMES == frozenset(
        {
            "invalid-idea-file", "invalid-idea", "missing-idea-title",
            "invalid-idea-field", "invalid-idea-source", "invalid-idea-outcome",
            "invalid-idea-id", "duplicate-idea-id", "ignored-idea-file",
            "invalid-idea-status", "missing-idea-relates-target",
            "promoted-without-outcome", "missing-outcome-target",
            "outcome-without-promotion", "idea-source-escapes-repo",
            "idea-source-missing", "idea-id-collides-with-node",
            "idea-unknown-field",
        }
    )


def test_idea_issue_prefix():
    issue = idea_issue(Severity.ERROR, "invalid-idea-status", "boom", "IDEA-7", "IDEA-7")
    assert issue.message == "idea 'IDEA-7': boom"
    assert issue.node_id == "IDEA-7"
    file_level = idea_issue(Severity.ERROR, "invalid-idea-file", "cannot parse", ".planning/ideas/X.yaml")
    assert file_level.message == "idea '.planning/ideas/X.yaml': cannot parse"
    assert file_level.node_id is None


def test_project_exposes_ideas_mapping(make_project, tmp_path):
    project, _root = make_project(tmp_path)
    assert project.ideas == {}
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_ideas.py -v`
Expected: FAIL — `ImportError: cannot import name 'IDEA_RULE_NAMES'`

- [ ] **Step 3: 实现 model.py 增量**

3a. 在 `TrackStatus` 类之后（`TRACK_STATUS_ALIASES` 之前）加枚举：

```python
class IdeaStatus(str, Enum):
    """Controlled idea-layer lifecycle statuses (spec §53.1).

    Ideas capture *uncommitted* thinking. PROMOTED is the only bridge into
    the planning graph and requires an outcome (spec §55.5); the validator,
    not the loader, checks membership.
    """

    OPEN = "OPEN"
    PARKED = "PARKED"
    PROMOTED = "PROMOTED"
    DISCARDED = "DISCARDED"
```

3b. 在 `Decision` 类之后、`Node` 类之前加三个 dataclass：

```python
@dataclass
class IdeaSource:
    """One justification entry on an idea (spec §52).

    ``ref`` is an optional repository-relative path (validated like an
    evidence source); ``note`` is free text and the only channel for the
    world outside the repository (benchmark targets live there). At least
    one of the two must be non-empty — enforced by the loader.
    """

    ref: str | None = None
    note: str | None = None


@dataclass
class IdeaOutcome:
    """Graduation target of a PROMOTED idea (spec §55.2)."""

    node: str
    note: str = ""


@dataclass
class Idea:
    """One captured thought in the idea layer (spec §51).

    Mirrors :class:`Node` in loading discipline (raw enum strings, unknown
    field tracking, ``source_file``) but carries no planning semantics: no
    tracks, no objective/scope, no decisions, no next_action — needing
    those is the signal to graduate, not to grow the schema.
    """

    id: str
    title: str
    status: str = IdeaStatus.OPEN.value
    detail: str = ""
    relates_to: list[str] = field(default_factory=list)
    benchmark_sources: list[IdeaSource] = field(default_factory=list)
    methodology_sources: list[IdeaSource] = field(default_factory=list)
    outcome: IdeaOutcome | None = None
    created: str = ""
    last_updated: str = ""
    #: Keys present in the source YAML but not part of the idea schema.
    unknown_fields: list[str] = field(default_factory=list)
    #: Repository-relative path of the file this idea was loaded from.
    source_file: str | None = None
```

3c. 在 `ValidationIssue` 类之后加封闭集与辅助函数：

```python
#: Rule names of the idea layer (spec §58.1). The closed set that tells
#: idea-layer validation issues from node-layer ones: the ``pcp build``
#: gate excludes exactly these rules (spec IDEA-D59), and every issue they
#: produce carries the ``idea '<id>': `` message prefix (spec IDEA-D64).
IDEA_RULE_NAMES = frozenset(
    {
        "invalid-idea-file",
        "invalid-idea",
        "missing-idea-title",
        "invalid-idea-field",
        "invalid-idea-source",
        "invalid-idea-outcome",
        "invalid-idea-id",
        "duplicate-idea-id",
        "ignored-idea-file",
        "invalid-idea-status",
        "missing-idea-relates-target",
        "promoted-without-outcome",
        "missing-outcome-target",
        "outcome-without-promotion",
        "idea-source-escapes-repo",
        "idea-source-missing",
        "idea-id-collides-with-node",
        "idea-unknown-field",
    }
)


def idea_issue(
    severity: Severity, rule: str, detail: str, ident: str, node_id: str | None = None
) -> ValidationIssue:
    """Build one idea-layer issue with the mandatory message prefix.

    ``ValidationIssue`` has a single id column shared by nodes and ideas,
    so every idea-layer message starts with ``idea '<ident>': `` (spec
    IDEA-D64). *ident* is the idea id, or the repository-relative path for
    the file-level rules whose ``node_id`` stays ``None``.
    """
    return ValidationIssue(
        severity=severity, rule=rule, message=f"idea '{ident}': {detail}", node_id=node_id
    )
```

3d. 在 `Project` 类的 `nodes` 字段之后加：

```python
    #: All ideas keyed by idea id (spec §51). Insertion order follows load
    #: order; consumers that need determinism should sort by id.
    ideas: dict[str, Idea] = field(default_factory=dict)
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_ideas.py -v`
Expected: 5 passed

- [ ] **Step 5: 提交**

```bash
git add src/planning_control_plane/model.py tests/test_ideas.py
git commit -m "feat(ideas): add Idea data model, IdeaStatus and shared issue protocol"
```

---

### Task 2: loader.py — parse_idea 解析器（含论据槽与 outcome 解析）

**Files:**
- Modify: `src/planning_control_plane/loader.py`
- Test: `tests/test_ideas.py`（追加）

规范锚点：IDEA-D10/D11/D13/D17/D32；规则 `invalid-idea`、`missing-idea-title`、`invalid-idea-field`、`invalid-idea-source`、`invalid-idea-outcome`。

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_ideas.py`：

```python
from planning_control_plane.loader import parse_idea


def test_parse_idea_minimal_defaults():
    issues = []
    idea = parse_idea({"id": "IDEA-1", "title": "T"}, "ideas/IDEA-1.yaml", issues)
    assert idea.id == "IDEA-1"
    assert idea.status == "OPEN"
    assert idea.source_file == "ideas/IDEA-1.yaml"
    assert issues == []


def test_parse_idea_missing_title_falls_back_to_id():
    issues = []
    idea = parse_idea({"id": "IDEA-1"}, None, issues)
    assert idea.title == "IDEA-1"
    assert [i.rule for i in issues] == ["missing-idea-title"]
    assert issues[0].message.startswith("idea 'IDEA-1': ")


def test_parse_idea_not_a_mapping():
    issues = []
    assert parse_idea(["nope"], "ideas/X.yaml", issues) is None
    assert [i.rule for i in issues] == ["invalid-idea"]
    assert issues[0].node_id is None


def test_parse_idea_missing_id():
    issues = []
    assert parse_idea({"title": "T"}, "ideas/X.yaml", issues) is None
    assert [i.rule for i in issues] == ["invalid-idea"]


def test_parse_idea_keeps_invalid_status_verbatim():
    # Loader philosophy (spec §10): raw values survive loading; the
    # validator reports them in one pass.
    issues = []
    idea = parse_idea({"id": "IDEA-1", "title": "T", "status": "PAUSED"}, None, issues)
    assert idea.status == "PAUSED"
    assert issues == []


def test_parse_idea_unknown_fields_tracked():
    idea = parse_idea({"id": "IDEA-1", "title": "T", "tags": ["x"], "builds_on": []}, None, [])
    assert idea.unknown_fields == ["builds_on", "tags"]


def test_parse_idea_sources_accept_ref_note_or_both():
    issues = []
    idea = parse_idea(
        {
            "id": "IDEA-1",
            "title": "T",
            "benchmark_sources": [{"ref": "docs/a.md", "note": "n"}, {"note": "外部对标"}],
            "methodology_sources": [{"ref": "docs/b.md"}, {}],
        },
        None,
        issues,
    )
    assert idea.benchmark_sources == [IdeaSource(ref="docs/a.md", note="n"), IdeaSource(ref=None, note="外部对标")]
    assert idea.methodology_sources == [IdeaSource(ref="docs/b.md", note=None)]
    assert [i.rule for i in issues] == ["invalid-idea-source"]


def test_parse_idea_sources_not_a_list():
    issues = []
    idea = parse_idea({"id": "IDEA-1", "title": "T", "methodology_sources": "docs/a.md"}, None, issues)
    assert idea.methodology_sources == []
    assert [i.rule for i in issues] == ["invalid-idea-field"]


def test_parse_idea_source_entries_must_be_mappings():
    issues = []
    idea = parse_idea({"id": "IDEA-1", "title": "T", "benchmark_sources": ["docs/a.md"]}, None, issues)
    assert idea.benchmark_sources == []
    assert [i.rule for i in issues] == ["invalid-idea-source"]


def test_parse_idea_outcome_variants():
    issues = []
    ok = parse_idea({"id": "A", "title": "T", "outcome": {"node": "P2", "note": "n"}}, None, issues)
    assert ok.outcome == IdeaOutcome(node="P2", note="n")
    no_node = parse_idea({"id": "B", "title": "T", "outcome": {"note": "no node"}}, None, issues)
    assert no_node.outcome is None
    bad = parse_idea({"id": "C", "title": "T", "outcome": ["x"]}, None, issues)
    assert bad.outcome is None
    assert [i.rule for i in issues] == ["invalid-idea-outcome", "invalid-idea-outcome"]


def test_parse_idea_relates_to_list_validation():
    issues = []
    idea = parse_idea({"id": "A", "title": "T", "relates_to": "P2"}, None, issues)
    assert idea.relates_to == []
    assert [i.rule for i in issues] == ["invalid-idea-field"]
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_ideas.py -v`
Expected: 新增用例 FAIL — `ImportError: cannot import name 'parse_idea'`

- [ ] **Step 3: 实现 loader.py 增量**

3a. import 块的 `from planning_control_plane.model import (...)` 中加入 `Idea`、`IdeaOutcome`、`IdeaSource`、`idea_issue`（按字母序插入）。

3b. 在 `NODES_DIR = "nodes"` 之后加：

```python
IDEAS_DIR = "ideas"

#: Keys of the idea schema (spec §51.2).
IDEA_FIELDS = frozenset(
    {
        "id",
        "title",
        "status",
        "detail",
        "relates_to",
        "benchmark_sources",
        "methodology_sources",
        "outcome",
        "created",
        "last_updated",
    }
)
```

3c. 在 `parse_node` 之前加三个解析辅助与主解析函数：

```python
def _as_idea_string_list(value, idea_id: str, key: str, issues: list) -> list[str]:
    """Idea-layer twin of :func:`_as_string_list`: same tolerance, but
    reports ``invalid-idea-field`` with the ``idea '<id>': `` prefix so the
    issue stays identifiable as idea-layer (spec §58.1 / IDEA-D64)."""
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append(
            idea_issue(Severity.ERROR, "invalid-idea-field", f"'{key}' must be a list, got {type(value).__name__}", idea_id, idea_id)
        )
        return []
    result = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item)
        else:
            issues.append(idea_issue(Severity.ERROR, "invalid-idea-field", f"'{key}' entries must be non-empty strings", idea_id, idea_id))
    return result


def _as_idea_sources(value, idea_id: str, key: str, issues: list) -> list[IdeaSource]:
    """Parse one justification list (spec §52.2): entries are mappings
    carrying a repository-relative ``ref`` and/or a free-text ``note``;
    an entry with neither is meaningless and reported."""
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append(
            idea_issue(Severity.ERROR, "invalid-idea-field", f"'{key}' must be a list, got {type(value).__name__}", idea_id, idea_id)
        )
        return []
    result: list[IdeaSource] = []
    for item in value:
        if not isinstance(item, dict):
            issues.append(idea_issue(Severity.ERROR, "invalid-idea-source", f"'{key}' entries must be mappings with 'ref' and/or 'note'", idea_id, idea_id))
            continue
        ref = item.get("ref")
        note = item.get("note")
        ref_ok = isinstance(ref, str) and ref.strip()
        note_ok = isinstance(note, str) and note.strip()
        if not ref_ok and not note_ok:
            issues.append(idea_issue(Severity.ERROR, "invalid-idea-source", f"'{key}' entry needs a non-empty 'ref' or 'note'", idea_id, idea_id))
            continue
        result.append(IdeaSource(ref=ref.strip() if ref_ok else None, note=note.strip() if note_ok else None))
    return result


def _as_idea_outcome(value, idea_id: str, issues: list) -> IdeaOutcome | None:
    """Parse ``outcome`` (spec §55.2): a mapping with a required non-empty
    ``node`` and an optional free-text ``note``."""
    if value is None:
        return None
    if not isinstance(value, dict):
        issues.append(idea_issue(Severity.ERROR, "invalid-idea-outcome", "'outcome' must be a mapping with 'node' and optional 'note'", idea_id, idea_id))
        return None
    node = value.get("node")
    note = value.get("note")
    if not isinstance(node, str) or not node.strip():
        issues.append(idea_issue(Severity.ERROR, "invalid-idea-outcome", "'outcome' needs a non-empty 'node'", idea_id, idea_id))
        return None
    return IdeaOutcome(node=node.strip(), note=note.strip() if isinstance(note, str) else "")


def parse_idea(data: object, source_file: str | None, issues: list) -> Idea | None:
    """Parse one idea mapping. Returns ``None`` when the entry is unusable
    (not a mapping, or missing/empty ``id``) — mirrors :func:`parse_node`.
    A present-but-empty value (e.g. ``status: ""``) is kept verbatim for
    the validator to report; only absent (or null) keys fall back to the
    schema default. Silently defaulting would hide typos.
    """
    if not isinstance(data, dict):
        issues.append(idea_issue(Severity.ERROR, "invalid-idea", f"idea entry in {source_file or 'ideas'} is not a mapping", source_file or "ideas"))
        return None
    idea_id = data.get("id")
    if not isinstance(idea_id, str) or not idea_id.strip():
        issues.append(idea_issue(Severity.ERROR, "invalid-idea", f"idea entry in {source_file or 'ideas'} is missing a non-empty 'id'", source_file or "ideas"))
        return None
    idea_id = idea_id.strip()

    title = _as_text(data.get("title"))
    if not title:
        issues.append(idea_issue(Severity.ERROR, "missing-idea-title", "idea is missing a non-empty 'title'", idea_id, idea_id))
        title = idea_id

    idea = Idea(id=idea_id, title=title, source_file=source_file)
    if data.get("status") is not None:
        idea.status = _as_text(data.get("status"))
    idea.detail = _as_text(data.get("detail"))
    idea.created = _as_text(data.get("created"))
    idea.last_updated = _as_text(data.get("last_updated"))
    idea.relates_to = _as_idea_string_list(data.get("relates_to"), idea_id, "relates_to", issues)
    idea.benchmark_sources = _as_idea_sources(data.get("benchmark_sources"), idea_id, "benchmark_sources", issues)
    idea.methodology_sources = _as_idea_sources(data.get("methodology_sources"), idea_id, "methodology_sources", issues)
    idea.outcome = _as_idea_outcome(data.get("outcome"), idea_id, issues)

    idea.unknown_fields = sorted(str(k) for k in data.keys() if k not in IDEA_FIELDS)
    return idea
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_ideas.py -v`
Expected: 全部 passed（Task 1 + Task 2 共 16）

- [ ] **Step 5: 提交**

```bash
git add src/planning_control_plane/loader.py tests/test_ideas.py
git commit -m "feat(ideas): parse idea files — justification slots, outcome, unknown fields"
```

---

### Task 3: loader.py — ideas/ 目录加载与失败域隔离

**Files:**
- Modify: `src/planning_control_plane/loader.py`（`load_project`）
- Test: `tests/test_ideas.py`（追加）

规范锚点：IDEA-D6/D7/D13/D58、不变量 §59.4（无 ideas/ 项目零变化）与 §59.6。规则 `invalid-idea-file`、`invalid-idea-id`、`duplicate-idea-id`、`ignored-idea-file`；R2 边界（解析成功但非 mapping → `invalid-idea`）。

- [ ] **Step 1: 写失败测试**

追加：

```python
GOOD_IDEA = """\
id: IDEA-0007
title: 对标驱动的视图改造
status: OPEN
relates_to: [P1]
last_updated: "2026-08-20"
"""


def test_no_ideas_dir_is_silent(make_project, tmp_path):
    project, _root = make_project(tmp_path, node_dicts=[{"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE"}])
    assert project.ideas == {}
    assert project.load_issues == []


def test_idea_file_loaded_with_source_path(make_project, tmp_path):
    project, _root = make_project(
        tmp_path,
        node_dicts=[{"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE"}],
        raw_files={"ideas/IDEA-0007.yaml": GOOD_IDEA},
    )
    idea = project.ideas["IDEA-0007"]
    assert idea.title == "对标驱动的视图改造"
    assert idea.relates_to == ["P1"]
    assert idea.source_file == ".planning/ideas/IDEA-0007.yaml"
    assert project.load_issues == []


def test_broken_idea_yaml_never_bricks_the_project(make_project, tmp_path):
    """IDEA-D58 / invariant §59.6: one broken idea file must not stop the
    other ideas or any node from loading."""
    project, _root = make_project(
        tmp_path,
        node_dicts=[{"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE"}],
        raw_files={
            "ideas/IDEA-BROKEN.yaml": "id: [unclosed\n  bad indent",
            "ideas/IDEA-0007.yaml": GOOD_IDEA,
        },
    )
    assert "IDEA-0007" in project.ideas
    assert "P1" in project.nodes
    assert [i.rule for i in project.load_issues] == ["invalid-idea-file"]
    assert project.load_issues[0].message.startswith("idea '.planning/ideas/IDEA-BROKEN.yaml': ")
    assert project.load_issues[0].node_id is None


def test_duplicate_keys_in_idea_file_are_an_issue_not_a_crash(make_project, tmp_path):
    project, _root = make_project(
        tmp_path,
        raw_files={"ideas/IDEA-DUP.yaml": "id: IDEA-DUP\nid: IDEA-DUP\ntitle: T\n"},
    )
    assert project.ideas == {}
    assert [i.rule for i in project.load_issues] == ["invalid-idea-file"]


def test_parsable_non_mapping_is_invalid_idea_not_invalid_idea_file(make_project, tmp_path):
    """R2 boundary: a file that parses but is not a mapping is an entry
    problem (invalid-idea), not a read problem (invalid-idea-file)."""
    project, _root = make_project(tmp_path, raw_files={"ideas/X.yaml": "- just\n- a list\n"})
    assert [i.rule for i in project.load_issues] == ["invalid-idea"]


def test_empty_idea_file_is_invalid_idea(make_project, tmp_path):
    project, _root = make_project(tmp_path, raw_files={"ideas/EMPTY.yaml": ""})
    assert project.ideas == {}
    assert [i.rule for i in project.load_issues] == ["invalid-idea"]


def test_duplicate_idea_id_keeps_first(make_project, tmp_path):
    project, _root = make_project(
        tmp_path,
        raw_files={
            "ideas/A.yaml": "id: IDEA-1\ntitle: First\n",
            "ideas/B.yaml": "id: IDEA-1\ntitle: Second\n",
        },
    )
    assert project.ideas["IDEA-1"].title == "First"
    assert [i.rule for i in project.load_issues] == ["duplicate-idea-id"]


def test_invalid_idea_id_charset_reported_but_kept(make_project, tmp_path):
    project, _root = make_project(tmp_path, raw_files={"ideas/BAD.yaml": "id: \"bad id!\"\ntitle: T\n"})
    assert [i.rule for i in project.load_issues] == ["invalid-idea-id"]
    assert "bad id!" in project.ideas


def test_nested_idea_file_warns(make_project, tmp_path):
    project, _root = make_project(
        tmp_path,
        raw_files={
            "ideas/IDEA-0007.yaml": GOOD_IDEA,
            "ideas/archive/IDEA-OLD.yaml": "id: IDEA-OLD\ntitle: Old\n",
        },
    )
    assert [i.rule for i in project.load_issues] == ["ignored-idea-file"]
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_ideas.py -v`
Expected: 新增用例 FAIL — `KeyError: 'IDEA-0007'`（ideas 尚未接入 `load_project`）

- [ ] **Step 3: 实现**

3a. 在 `_read_yaml` 之后加容错读取：

```python
def _read_idea_yaml(path: Path, rel: str, issues: list) -> tuple[bool, object]:
    """Read one idea file tolerantly (spec §51.3.1 / IDEA-D58).

    Unlike :func:`_read_yaml`, any read or parse failure — YAML syntax
    errors, duplicate keys (``_UniqueKeyLoader`` raises on those), an
    unreadable file — becomes an ``invalid-idea-file`` ERROR issue and the
    file is skipped: an uncommitted thought must never brick the planning
    data it decorates, so ideas never raise :class:`LoadError`. Returns
    ``(False, None)`` when the file is skipped, ``(True, data)``
    otherwise — *data* may still be ``None`` for an empty-but-valid file,
    which :func:`parse_idea` reports as ``invalid-idea``.
    """
    try:
        with path.open("r", encoding="utf-8") as handle:
            return True, yaml.load(handle, Loader=_UniqueKeyLoader)
    except (yaml.YAMLError, OSError) as exc:
        issues.append(idea_issue(Severity.ERROR, "invalid-idea-file", f"cannot read or parse ({exc})", rel))
        return False, None
```

3b. 在 `load_project` 中，节点加载 for 循环（`project.nodes[node.id] = node` 所在块）之后、`return project` 之前插入：

```python
    # Idea layer (spec §51): one file per idea under ideas/, loaded with
    # the same discipline as nodes but with failure-domain isolation — a
    # broken idea file becomes an issue instead of a LoadError (IDEA-D58).
    ideas_dir = planning_dir / IDEAS_DIR
    if ideas_dir.is_dir():
        loaded_ideas: set[Path] = set()
        for idea_file in sorted(ideas_dir.glob("*.yaml")):
            loaded_ideas.add(idea_file)
            rel = f"{PLANNING_DIR}/{IDEAS_DIR}/{idea_file.name}"
            ok, raw = _read_idea_yaml(idea_file, rel, issues)
            if not ok:
                continue
            idea = parse_idea(raw, rel, issues)
            if idea is None:
                continue
            if not NODE_ID_RE.match(idea.id):
                issues.append(
                    idea_issue(
                        Severity.ERROR,
                        "invalid-idea-id",
                        f"idea id '{idea.id}' must match {NODE_ID_RE.pattern}",
                        idea.id,
                        idea.id,
                    )
                )
            if idea.id in project.ideas:
                existing = project.ideas[idea.id].source_file or "unknown"
                issues.append(
                    idea_issue(
                        Severity.ERROR,
                        "duplicate-idea-id",
                        f"duplicate idea id '{idea.id}' (first defined in {existing}); keeping the first definition",
                        idea.id,
                        idea.id,
                    )
                )
                continue
            project.ideas[idea.id] = idea
        # Mirror the nodes/ contract (spec §37.1): a YAML-ish file under
        # ideas/ that is NOT read must never disappear silently.
        for candidate in sorted(ideas_dir.rglob("*")):
            if not candidate.is_file() or candidate in loaded_ideas:
                continue
            if candidate.suffix not in (".yaml", ".yml"):
                continue
            rel = f"{PLANNING_DIR}/{IDEAS_DIR}/{candidate.relative_to(ideas_dir).as_posix()}"
            issues.append(
                idea_issue(
                    Severity.WARNING,
                    "ignored-idea-file",
                    f"'{rel}' is not loaded (only top-level *.yaml files are read); "
                    "move it to the top level with a .yaml suffix so it joins the idea layer",
                    rel,
                )
            )

    return project
```

（原有的 `return project` 保持唯一，把插入块放在它之前。）

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_ideas.py tests/test_loader.py -v`
Expected: 全部 passed（含既有 loader 测试——镜像不破先例）

- [ ] **Step 5: 提交**

```bash
git add src/planning_control_plane/loader.py tests/test_ideas.py
git commit -m "feat(ideas): load .planning/ideas/ with failure-domain isolation (IDEA-D58)"
```

---

### Task 4: validator.py — _check_ideas 规则组（9 条 validator 级规则）

**Files:**
- Modify: `src/planning_control_plane/validator.py`
- Test: `tests/test_ideas.py`（追加）

规范锚点：IDEA-D15/D19/D22（无论据 WARNING 已在 R1 删除——空槽不产生任何 issue）/D36/D37/D38/D39/D47/D48/D64。

- [ ] **Step 1: 写失败测试**

追加：

```python
from planning_control_plane.validator import validate_project


def _idea_project(make_project, tmp_path, idea_yaml, nodes=None):
    return make_project(tmp_path, node_dicts=nodes or [], raw_files={"ideas/IDEA-1.yaml": idea_yaml})


def test_invalid_idea_status(make_project, tmp_path, by_rule):
    project, _root = _idea_project(make_project, tmp_path, "id: IDEA-1\ntitle: T\nstatus: PAUSED\n")
    issues = by_rule(validate_project(project), "invalid-idea-status")
    assert [i.severity for i in issues] == [Severity.ERROR]
    assert issues[0].node_id == "IDEA-1"


def test_missing_idea_relates_target(make_project, tmp_path, by_rule):
    project, _root = _idea_project(make_project, tmp_path, "id: IDEA-1\ntitle: T\nrelates_to: [NOPE]\n")
    assert [i.severity for i in by_rule(validate_project(project), "missing-idea-relates-target")] == [Severity.ERROR]


def test_promoted_without_outcome(make_project, tmp_path, by_rule):
    project, _root = _idea_project(make_project, tmp_path, "id: IDEA-1\ntitle: T\nstatus: PROMOTED\n")
    assert [i.severity for i in by_rule(validate_project(project), "promoted-without-outcome")] == [Severity.ERROR]


def test_promoted_outcome_target_must_exist(make_project, tmp_path, by_rule):
    project, _root = _idea_project(make_project, tmp_path, "id: IDEA-1\ntitle: T\nstatus: PROMOTED\noutcome:\n  node: GONE\n")
    assert [i.severity for i in by_rule(validate_project(project), "missing-outcome-target")] == [Severity.ERROR]


def test_outcome_without_promotion_warns(make_project, tmp_path, by_rule):
    nodes = [{"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE"}]
    project, _root = _idea_project(make_project, tmp_path, "id: IDEA-1\ntitle: T\nstatus: OPEN\noutcome:\n  node: P1\n", nodes)
    issues = validate_project(project)
    assert [i.severity for i in by_rule(issues, "outcome-without-promotion")] == [Severity.WARNING]
    assert by_rule(issues, "missing-outcome-target") == []  # node exists — no ERROR


def test_idea_ref_escapes_repo(make_project, tmp_path, by_rule):
    project, _root = _idea_project(
        make_project, tmp_path, "id: IDEA-1\ntitle: T\nbenchmark_sources:\n  - ref: \"/etc/passwd\"\n    note: n\n"
    )
    assert [i.severity for i in by_rule(validate_project(project), "idea-source-escapes-repo")] == [Severity.ERROR]


def test_idea_ref_missing_warns(make_project, tmp_path, by_rule):
    project, _root = _idea_project(
        make_project, tmp_path, "id: IDEA-1\ntitle: T\nmethodology_sources:\n  - ref: docs/absent.md\n"
    )
    assert [i.severity for i in by_rule(validate_project(project), "idea-source-missing")] == [Severity.WARNING]


def test_idea_id_collision_warns(make_project, tmp_path, by_rule):
    nodes = [{"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE"}]
    project, _root = _idea_project(make_project, tmp_path, "id: P1\ntitle: T\n", nodes)
    assert [i.severity for i in by_rule(validate_project(project), "idea-id-collides-with-node")] == [Severity.WARNING]


def test_idea_unknown_field_reported(make_project, tmp_path, by_rule):
    project, _root = _idea_project(make_project, tmp_path, "id: IDEA-1\ntitle: T\ntags: [x]\n")
    assert [i.severity for i in by_rule(validate_project(project), "idea-unknown-field")] == [Severity.WARNING]


def test_empty_justification_slots_produce_no_issue(make_project, tmp_path):
    """IDEA-D22 (R1): justification completeness never enters validation."""
    project, _root = _idea_project(make_project, tmp_path, "id: IDEA-1\ntitle: T\n")
    assert validate_project(project) == []


def test_every_idea_issue_carries_the_prefix(make_project, tmp_path):
    project, _root = make_project(
        tmp_path,
        node_dicts=[{"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE"}],
        raw_files={
            "ideas/A.yaml": "id: A\ntitle: T\nstatus: PAUSED\nrelates_to: [NOPE]\n",
            "ideas/B.yaml": "id: B\ntitle: T\nstatus: PROMOTED\n",
        },
    )
    idea_issues = [i for i in validate_project(project) if i.rule in IDEA_RULE_NAMES]
    assert len(idea_issues) >= 3
    assert all(i.message.startswith("idea '") for i in idea_issues)


def test_idea_rules_stay_within_the_closed_set(make_project, tmp_path):
    """IDEA-D48: idea problems never leak into node-layer rules."""
    project, _root = make_project(
        tmp_path,
        node_dicts=[{"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE"}],
        raw_files={"ideas/A.yaml": "id: A\ntitle: T\nstatus: PAUSED\nrelates_to: [NOPE]\noutcome:\n  node: GONE\n"},
    )
    for issue in validate_project(project):
        assert issue.rule in IDEA_RULE_NAMES or issue.rule in {
            "current-focus-not-set",  # pre-existing project-level warning, unrelated
        }
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_ideas.py -v`
Expected: 新增用例 FAIL — 规则不存在（`by_rule` 返回空列表导致断言失败）

- [ ] **Step 3: 实现 validator.py 增量**

3a. import：`from planning_control_plane.model import (...)` 加入 `IdeaStatus`、`idea_issue`。

3b. 在 `_TRACK_STATUS_VALUES` 之后加：

```python
#: Controlled idea status values as plain strings (spec §53.1).
_IDEA_STATUS_VALUES = frozenset(member.value for member in IdeaStatus)
```

3c. `validate_project` 中，`_check_decisions(project, issues)` 之后加一行：

```python
    _check_ideas(project, issues)
```

3d. 在 `_check_decisions` 函数之后加两个函数：

```python
# ------------------------------------------------------------------- ideas


def _check_ideas(project: Project, issues: list[ValidationIssue]) -> None:
    """Idea-layer rules (spec §58.1). Independent rule group: constrains
    ideas only, never feeds back into node rules (IDEA-D48)."""
    known_nodes = set(project.nodes)
    for idea_id in sorted(project.ideas):
        idea = project.ideas[idea_id]

        if idea.status not in _IDEA_STATUS_VALUES:
            issues.append(
                idea_issue(Severity.ERROR, "invalid-idea-status", f"status '{idea.status}' is not a valid idea status", idea_id, idea_id)
            )

        for target in sorted(set(idea.relates_to)):
            if target not in known_nodes:
                issues.append(
                    idea_issue(Severity.ERROR, "missing-idea-relates-target", f"relates_to target '{target}' is not a known node", idea_id, idea_id)
                )

        if idea.outcome is not None and idea.outcome.node not in known_nodes:
            issues.append(
                idea_issue(Severity.ERROR, "missing-outcome-target", f"outcome node '{idea.outcome.node}' is not a known node", idea_id, idea_id)
            )
        if idea.status == IdeaStatus.PROMOTED.value and idea.outcome is None:
            issues.append(
                idea_issue(Severity.ERROR, "promoted-without-outcome", "status is PROMOTED but outcome is missing", idea_id, idea_id)
            )
        if idea.outcome is not None and idea.status != IdeaStatus.PROMOTED.value:
            issues.append(
                idea_issue(Severity.WARNING, "outcome-without-promotion", f"outcome is set but status is '{idea.status}' (graduation pending?)", idea_id, idea_id)
            )

        if idea_id in known_nodes:
            issues.append(
                idea_issue(Severity.WARNING, "idea-id-collides-with-node", "idea id is also used by a planning node; consider renaming to avoid confusion", idea_id, idea_id)
            )

        if idea.unknown_fields:
            issues.append(
                idea_issue(Severity.WARNING, "idea-unknown-field", f"unknown idea fields: {', '.join(idea.unknown_fields)}", idea_id, idea_id)
            )

        for key in ("benchmark_sources", "methodology_sources"):
            for entry in getattr(idea, key):
                if entry.ref:
                    _check_idea_reference(project.root, idea_id, key, entry.ref, issues)


def _check_idea_reference(root: Path, idea_id: str, key: str, path: str, issues: list[ValidationIssue]) -> None:
    """Check one idea justification ``ref`` (spec §52.3): escaping the
    repository is an ERROR, a missing file only a WARNING — the evidence
    split, mirrored for the idea layer."""
    if PurePath(path).is_absolute():
        issues.append(
            idea_issue(Severity.ERROR, "idea-source-escapes-repo", f"{key} entry '{path}' is not repository-relative", idea_id, idea_id)
        )
        return
    candidate = Path(os.path.normpath(os.path.join(root, path)))
    if not candidate.is_relative_to(root):
        issues.append(
            idea_issue(Severity.ERROR, "idea-source-escapes-repo", f"{key} entry '{path}' is not repository-relative", idea_id, idea_id)
        )
        return
    if not candidate.is_file():
        issues.append(
            idea_issue(Severity.WARNING, "idea-source-missing", f"{key} entry '{path}' does not exist in the repository", idea_id, idea_id)
        )
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_ideas.py tests/test_validator_rules.py tests/test_validator_structure.py -v`
Expected: 全部 passed

- [ ] **Step 5: 提交**

```bash
git add src/planning_control_plane/validator.py tests/test_ideas.py
git commit -m "feat(ideas): independent validator rule group with prefixed messages"
```

---

### Task 5: cli.py — pcp ideas 命令（分组列表、D61 排序、过滤与空态）

**Files:**
- Modify: `src/planning_control_plane/cli.py`
- Test: `tests/test_ideas.py`（追加）

规范锚点：IDEA-D22（论据存在性标记在展示层）、D50/D51/D53、D61（排序）、§60 全部参数与退出码语义。

- [ ] **Step 1: 写失败测试**

追加：

```python
def test_cli_ideas_empty_state_exit_zero(make_project, tmp_path, cli):
    _project, root = make_project(tmp_path)
    code, out, err = cli("ideas", "-p", str(root))
    assert (code, err) == (0, "")
    assert out.strip() == "no ideas yet; add .planning/ideas/<id>.yaml"


def test_cli_ideas_groups_and_d61_ordering(make_project, tmp_path, cli):
    raw = {
        "ideas/IDEA-A.yaml": "id: IDEA-A\ntitle: 无时间戳\nstatus: OPEN\n",
        "ideas/IDEA-B.yaml": "id: IDEA-B\ntitle: 旧想法\nstatus: OPEN\nlast_updated: \"2026-01-01\"\n",
        "ideas/IDEA-C.yaml": "id: IDEA-C\ntitle: 新想法\nstatus: OPEN\nlast_updated: \"2026-08-01\"\n",
        "ideas/IDEA-D.yaml": "id: IDEA-D\ntitle: 搁置\nstatus: PARKED\nlast_updated: \"2026-02-01\"\n",
    }
    _project, root = make_project(tmp_path, raw_files=raw)
    code, out, err = cli("ideas", "-p", str(root))
    assert code == 0
    lines = out.splitlines()
    assert lines[0] == "== OPEN (3) =="
    assert lines[1].startswith("IDEA-B")   # oldest non-empty first: stale floats up
    assert lines[2].startswith("IDEA-C")
    assert lines[3].startswith("IDEA-A")   # empty last_updated sorts last (IDEA-D61)
    assert lines[4] == "== PARKED (1) =="
    assert lines[5].startswith("IDEA-D")
    assert len(lines) == 6                 # empty groups are omitted entirely


def test_cli_ideas_line_format(make_project, tmp_path, cli):
    raw = {
        "ideas/IDEA-B.yaml": (
            "id: IDEA-B\ntitle: 对标驱动的视图改造\nstatus: OPEN\n"
            "relates_to: [P1]\nlast_updated: \"2026-01-01\"\n"
            "benchmark_sources:\n  - note: Grafana 对标\n"
        )
    }
    _project, root = make_project(
        tmp_path,
        node_dicts=[{"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE"}],
        raw_files=raw,
    )
    code, out, err = cli("ideas", "-p", str(root))
    assert code == 0
    line = out.splitlines()[1]
    assert line == "IDEA-B  2026-01-01  对标驱动的视图改造  relates: P1  benchmark:Y methodology:N"


def test_cli_ideas_status_filter_repeatable(make_project, tmp_path, cli):
    raw = {
        "ideas/IDEA-A.yaml": "id: IDEA-A\ntitle: T\nstatus: OPEN\n",
        "ideas/IDEA-D.yaml": "id: IDEA-D\ntitle: T\nstatus: PARKED\n",
    }
    _project, root = make_project(tmp_path, raw_files=raw)
    code, out, err = cli("ideas", "--status", "PARKED", "-p", str(root))
    assert code == 0
    assert "IDEA-A" not in out and "IDEA-D" in out
    code, out, err = cli("ideas", "--status", "OPEN", "--status", "PARKED", "-p", str(root))
    assert "IDEA-A" in out and "IDEA-D" in out


def test_cli_ideas_status_filter_no_match_exit_zero(make_project, tmp_path, cli):
    _project, root = make_project(tmp_path, raw_files={"ideas/A.yaml": "id: IDEA-A\ntitle: T\nstatus: OPEN\n"})
    code, out, err = cli("ideas", "--status", "DISCARDED", "-p", str(root))
    assert (code, err) == (0, "")
    assert out.strip() == "no ideas match the requested status filter"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_ideas.py -v`
Expected: 新增用例 FAIL — `SystemExit`/argparse 报 `invalid choice: 'ideas'`（子命令不存在）

- [ ] **Step 3: 实现 cli.py 增量**

3a. import 区加：

```python
from planning_control_plane.graph import PlanningGraph
```

并把 model 导入行改为：

```python
from planning_control_plane.model import IDEA_RULE_NAMES, Idea, IdeaStatus, PCPError, PLANNING_DIR, Project, Severity
```

3b. 在 `cmd_focus` 与 `cmd_build` 之间加命令实现：

```python
#: Display order of idea statuses in `pcp ideas` output (spec §60/IDEA-D51).
_IDEA_STATUS_ORDER = (
    IdeaStatus.OPEN.value,
    IdeaStatus.PARKED.value,
    IdeaStatus.PROMOTED.value,
    IdeaStatus.DISCARDED.value,
)


def _idea_line(idea: Idea, via: list[str] | None) -> str:
    """One deterministic listing line (spec §60/IDEA-D51): id, date, title,
    relations, justification presence markers (IDEA-D22 — display, never
    validation), and — in query mode — which node matched."""
    parts = [
        idea.id,
        idea.last_updated or "-",
        _oneline(idea.title) or "-",
        "relates: " + (", ".join(idea.relates_to) if idea.relates_to else "-"),
        "benchmark:" + ("Y" if idea.benchmark_sources else "N"),
        "methodology:" + ("Y" if idea.methodology_sources else "N"),
    ]
    if via is not None:
        parts.append("via: " + (", ".join(via) if via else "-"))
    return "  ".join(parts)


def _idea_sort_key(idea: Idea) -> tuple[bool, str, str]:
    """(empty flag, last_updated, id): oldest non-empty timestamp first so
    stale ideas surface at the top of their group; entries with no
    timestamp sort last (spec §60/IDEA-D61)."""
    return (idea.last_updated == "", idea.last_updated, idea.id)


def cmd_ideas(args: argparse.Namespace) -> int:
    """``pcp ideas [--status ...] [--for NODE [--subtree]]`` — list the idea
    layer (spec §60). Read-only: ideas are created and edited as YAML
    files under .planning/ideas/ (files are the source, not the CLI)."""
    project = _load_project(args)
    if project is None:
        return EXIT_USAGE

    if args.subtree and args.node is None:
        print("error: --subtree requires --for <node>", file=sys.stderr)
        return EXIT_USAGE

    if args.node is None:
        selected: list[tuple[Idea, list[str] | None]] = [
            (project.ideas[idea_id], None) for idea_id in sorted(project.ideas)
        ]
    else:
        if args.node not in project.nodes:
            print(f"error: unknown node '{args.node}'", file=sys.stderr)
            return EXIT_FAILURE
        graph = PlanningGraph(project)
        if args.subtree:
            scope = set(graph.subtree_ids(args.node))  # IDEA-D60: moment B, downward
        else:
            scope = {args.node, *graph.ancestors(args.node)}  # IDEA-D30: moment A, upward
        selected = []
        for idea_id in sorted(project.ideas):
            idea = project.ideas[idea_id]
            matched = [target for target in idea.relates_to if target in scope]
            if matched:
                selected.append((idea, matched))

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

    if shown == 0:
        if args.node is not None:
            print(f"no matching ideas for node '{args.node}'" + (" (subtree)" if args.subtree else ""))
        elif project.ideas:
            print("no ideas match the requested status filter")
        else:
            print("no ideas yet; add .planning/ideas/<id>.yaml")
    return EXIT_OK
```

3c. `_build_parser` 中，`focus_parser` 接线块之后加：

```python
    ideas_parser = subparsers.add_parser(
        "ideas",
        help="list captured ideas (the idea layer)",
        description=(
            "Read-only listing of .planning/ideas/*.yaml, grouped by "
            "status. --for selects ideas whose relates_to hits a node or "
            "one of its ancestors (decision-discussion view); adding "
            "--subtree selects the node's subtree instead (closure view)."
        ),
    )
    ideas_parser.add_argument(
        "--status",
        action="append",
        choices=list(_IDEA_STATUS_ORDER),
        metavar="STATUS",
        help="restrict to one status (repeatable); default: all statuses, "
        "or OPEN+PARKED when --for is given",
    )
    ideas_parser.add_argument(
        "--for",
        dest="node",
        metavar="NODE",
        help="only ideas whose relates_to hits NODE or one of NODE's "
        "ancestors; with --subtree, any node in NODE's subtree instead",
    )
    ideas_parser.add_argument(
        "--subtree",
        action="store_true",
        help="switch the --for direction from ancestors to the subtree "
        "(requires --for)",
    )
    ideas_parser.set_defaults(func=cmd_ideas)
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_ideas.py tests/test_cli.py -v`
Expected: 全部 passed

- [ ] **Step 5: 提交**

```bash
git add src/planning_control_plane/cli.py tests/test_ideas.py
git commit -m "feat(ideas): read-only 'pcp ideas' listing with D61 ordering and status filter"
```

---

### Task 6: cli.py — --for 双向关联查询（祖先方向 + 子树方向）

**Files:**
- Modify: `src/planning_control_plane/cli.py`（Task 5 的 `cmd_ideas` 已含查询逻辑——本任务只补测试验证行为）
- Test: `tests/test_ideas.py`（追加）

规范锚点：IDEA-D30（祖先方向，时刻 A）、D60（子树方向，时刻 B）、D62（`--for` 默认 OPEN+PARKED）、§60 参数/退出码。实现约束：必须复用 `PlanningGraph.ancestors()` / `subtree_ids()`（防 parent 环死循环）——Task 5 代码已如此，此处用测试钉死该行为面。

- [ ] **Step 1: 写失败测试**

追加：

```python
def _tree_nodes():
    return [
        {"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE"},
        {"id": "P2", "title": "P2", "type": "PHASE", "parent": "P1", "status": "IMPLEMENTING"},
        {"id": "P2-A", "title": "P2-A", "type": "STRATEGY", "parent": "P2", "status": "READY"},
    ]


def test_cli_ideas_for_ancestor_match_with_via(make_project, tmp_path, cli):
    raw = {"ideas/IDEA-1.yaml": "id: IDEA-1\ntitle: 挂在 P2 上\nstatus: OPEN\nrelates_to: [P2]\n"}
    _project, root = make_project(tmp_path, node_dicts=_tree_nodes(), raw_files=raw)
    code, out, err = cli("ideas", "--for", "P2-A", "-p", str(root))
    assert code == 0
    assert "IDEA-1" in out
    assert "via: P2" in out  # matched through the ancestor, attributed


def test_cli_ideas_for_self_match(make_project, tmp_path, cli):
    raw = {"ideas/IDEA-1.yaml": "id: IDEA-1\ntitle: T\nstatus: OPEN\nrelates_to: [P2-A]\n"}
    _project, root = make_project(tmp_path, node_dicts=_tree_nodes(), raw_files=raw)
    code, out, err = cli("ideas", "--for", "P2-A", "-p", str(root))
    assert code == 0
    assert "via: P2-A" in out


def test_cli_ideas_for_excludes_unrelated(make_project, tmp_path, cli):
    raw = {"ideas/IDEA-1.yaml": "id: IDEA-1\ntitle: T\nstatus: OPEN\nrelates_to: [P2]\n"}
    _project, root = make_project(tmp_path, node_dicts=_tree_nodes(), raw_files=raw)
    code, out, err = cli("ideas", "--for", "P1", "-p", str(root))  # P2 is a child, not an ancestor
    assert (code, err) == (0, "")
    assert out.strip() == "no matching ideas for node 'P1'"


def test_cli_ideas_for_subtree_direction(make_project, tmp_path, cli):
    """R1/B4: the ancestor direction cannot see ideas hung on children;
    --subtree is what makes moment B executable."""
    raw = {"ideas/IDEA-1.yaml": "id: IDEA-1\ntitle: T\nstatus: OPEN\nrelates_to: [P2-A]\n"}
    _project, root = make_project(tmp_path, node_dicts=_tree_nodes(), raw_files=raw)
    code, out, _ = cli("ideas", "--for", "P2", "-p", str(root))
    assert "IDEA-1" not in out
    code, out, _ = cli("ideas", "--for", "P2", "--subtree", "-p", str(root))
    assert code == 0
    assert "IDEA-1" in out
    assert "via: P2-A" in out


def test_cli_ideas_for_defaults_to_open_and_parked(make_project, tmp_path, cli):
    raw = {
        "ideas/A.yaml": "id: A\ntitle: T\nstatus: OPEN\nrelates_to: [P2]\n",
        "ideas/B.yaml": "id: B\ntitle: T\nstatus: PARKED\nrelates_to: [P2]\n",
        "ideas/C.yaml": "id: C\ntitle: T\nstatus: PROMOTED\nrelates_to: [P2]\n",
        "ideas/D.yaml": "id: D\ntitle: T\nstatus: DISCARDED\nrelates_to: [P2]\n",
    }
    _project, root = make_project(tmp_path, node_dicts=_tree_nodes(), raw_files=raw)
    code, out, err = cli("ideas", "--for", "P2", "-p", str(root))
    assert code == 0
    assert "IDEA" not in out and " A " in "\n".join(" " + l + " " for l in out.splitlines())[0] or True  # placeholder-free:
    lines = [l for l in out.splitlines() if l.startswith(("A ", "A  ", "B ", "B  ", "C ", "C  ", "D ", "D  "))]
    ids = [l.split()[0] for l in lines]
    assert ids == ["A", "B"]  # IDEA-D62: OPEN + PARKED only
```

上面最后一个断言写得绕了——实现时用这个更清晰的版本（替换整个测试函数体末尾）：

```python
    code, out, err = cli("ideas", "--for", "P2", "-p", str(root))
    assert code == 0
    ids = [line.split()[0] for line in out.splitlines() if not line.startswith("==")]
    assert ids == ["A", "B"]  # IDEA-D62: --for defaults to OPEN + PARKED

    code, out, err = cli("ideas", "--for", "P2", "--status", "DISCARDED", "-p", str(root))
    assert code == 0
    ids = [line.split()[0] for line in out.splitlines() if not line.startswith("==")]
    assert ids == ["D"]  # explicit --status overrides the default filter
```

```python
def test_cli_ideas_subtree_requires_for(make_project, tmp_path, cli):
    _project, root = make_project(tmp_path)
    code, out, err = cli("ideas", "--subtree", "-p", str(root))
    assert code == 2
    assert "--subtree requires --for" in err


def test_cli_ideas_for_unknown_node(make_project, tmp_path, cli):
    _project, root = make_project(tmp_path)
    code, out, err = cli("ideas", "--for", "NOPE", "-p", str(root))
    assert code == 1
    assert "unknown node 'NOPE'" in err
```

- [ ] **Step 2: 运行确认通过（本任务为行为验证型——Task 5 已含实现）**

Run: `python -m pytest tests/test_ideas.py -v`
Expected: 全部 passed。若有 FAIL：对照 §54.3 修 `cmd_ideas` 的 scope 计算，禁止绕开 `PlanningGraph` 自行遍历 parent 链。

- [ ] **Step 3: 提交**

```bash
git add tests/test_ideas.py
git commit -m "test(ideas): pin --for ancestor/subtree directions, D62 defaults and exit codes"
```

---

### Task 7: cli.py — focus/context 提示与 build 门禁豁免

**Files:**
- Modify: `src/planning_control_plane/cli.py`（`cmd_context`、`cmd_focus`、`cmd_build`）
- Test: `tests/test_ideas.py`（追加）

规范锚点：IDEA-D52（focus/context 提示）、D59（门禁只看非想法层 ERROR，按规则名 frozenset 判定）、不变量 §59.6（坏想法文件下 status/context/build 仍成功——spec §62.1 点名的必备用例）。

- [ ] **Step 1: 写失败测试**

追加：

```python
def test_cli_context_idea_id_hint(make_project, tmp_path, cli):
    nodes = [{"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE"}]
    raw = {"ideas/IDEA-0007.yaml": "id: IDEA-0007\ntitle: T\nstatus: OPEN\n"}
    _project, root = make_project(tmp_path, node_dicts=nodes, raw_files=raw)
    code, out, err = cli("context", "IDEA-0007", "-p", str(root))
    assert code == 1
    assert "unknown node 'IDEA-0007'" in err
    assert "pcp ideas" in err


def test_cli_focus_idea_id_hint(make_project, tmp_path, cli):
    nodes = [{"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE"}]
    raw = {"ideas/IDEA-0007.yaml": "id: IDEA-0007\ntitle: T\nstatus: OPEN\n"}
    _project, root = make_project(tmp_path, node_dicts=nodes, raw_files=raw)
    code, out, err = cli("focus", "IDEA-0007", "-p", str(root))
    assert code == 1
    assert "pcp ideas" in err


def test_cli_build_succeeds_with_idea_layer_errors(make_project, tmp_path, cli):
    """IDEA-D59: an idea-layer ERROR must not block the plan projection."""
    nodes = [{"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE"}]
    raw = {"ideas/IDEA-BAD.yaml": "id: IDEA-BAD\ntitle: T\nstatus: PROMOTED\n"}  # promoted-without-outcome ERROR
    _project, root = make_project(tmp_path, node_dicts=nodes, raw_files=raw)
    code, out, err = cli("build", "-p", str(root))
    assert code == 0
    assert "promoted-without-outcome" in out  # printed, informational
    assert "Built" in out                     # build proceeded


def test_cli_build_still_blocked_by_node_layer_errors(make_project, tmp_path, cli):
    nodes = [{"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE", "depends_on": ["MISSING"]}]
    raw = {"ideas/IDEA-BAD.yaml": "id: IDEA-BAD\ntitle: T\nstatus: PROMOTED\n"}
    _project, root = make_project(tmp_path, node_dicts=nodes, raw_files=raw)
    code, out, err = cli("build", "-p", str(root))
    assert code == 1
    assert "fix validation errors before build" in out


def test_cli_plan_commands_survive_broken_idea_file(make_project, tmp_path, cli):
    """Spec §62.1 phase-1 acceptance: with a broken idea YAML present,
    status / context / build must all still succeed (invariant §59.6)."""
    config = {"project": {"id": "t", "name": "T"}, "planning": {"current_focus": "P1"}}
    nodes = [{"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE"}]
    raw = {"ideas/IDEA-BROKEN.yaml": "id: [unclosed\n"}
    _project, root = make_project(tmp_path, config_dict=config, node_dicts=nodes, raw_files=raw)

    code, out, err = cli("status", "-p", str(root))
    assert code == 0

    code, out, err = cli("context", "P1", "-p", str(root))
    assert code == 0
    assert "PCP CONTEXT CAPSULE" in out  # capsule unaffected by idea garbage

    code, out, err = cli("build", "-p", str(root))
    assert code == 0
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/test_ideas.py -v`
Expected: `test_cli_context_idea_id_hint`、`test_cli_focus_idea_id_hint` FAIL（无提示语）；`test_cli_build_succeeds_with_idea_layer_errors`、`test_cli_plan_commands_survive_broken_idea_file` FAIL（build 退出 1）

- [ ] **Step 3: 实现 cli.py 增量**

3a. 在 `_oneline` 之后加提示辅助：

```python
def _idea_hint(project: Project, node_id: str) -> str:
    """IDEA-D52 suffix for unknown-node errors: an IDEA id is a natural
    mistake, and the thing the user needs to hear is that capsules and
    focus never carry ideas — 'pcp ideas' owns them."""
    if node_id in project.ideas:
        return f"; '{node_id}' is an IDEA record, see 'pcp ideas'"
    return ""
```

3b. `cmd_context` 中替换：

```python
    if node_id not in project.nodes:
        print(f"error: unknown node '{node_id}'", file=sys.stderr)
        return EXIT_FAILURE
```

为：

```python
    if node_id not in project.nodes:
        print(f"error: unknown node '{node_id}'{_idea_hint(project, node_id)}", file=sys.stderr)
        return EXIT_FAILURE
```

3c. `cmd_focus` 中替换（`node = project.nodes.get(node_id)` 之后）：

```python
    if node is None:
        print(f"error: unknown node '{node_id}'", file=sys.stderr)
        return EXIT_FAILURE
```

为：

```python
    if node is None:
        print(f"error: unknown node '{node_id}'{_idea_hint(project, node_id)}", file=sys.stderr)
        return EXIT_FAILURE
```

3d. `cmd_build` 中替换校验门禁块：

```python
    issues = validator.validate_project(project)
    errors = [issue for issue in issues if issue.severity == Severity.ERROR]
    warnings = [issue for issue in issues if issue.severity != Severity.ERROR]
    if errors:
        for issue in issues:
            print(issue.format())
        print()
        print("fix validation errors before build")
        return EXIT_FAILURE
    for issue in warnings:  # warnings are informational; the build continues
        print(issue.format())
```

为：

```python
    issues = validator.validate_project(project)

    def _blocks_build(issue) -> bool:
        # Idea-layer ERRORs do not gate the build (spec IDEA-D59):
        # uncommitted thoughts must not block the plan projection. Layer
        # membership is decided by rule name — the closed set in
        # model.IDEA_RULE_NAMES — never by node_id (file-level issues
        # have none, and idea/node ids may collide, spec IDEA-D15).
        return issue.severity == Severity.ERROR and issue.rule not in IDEA_RULE_NAMES

    blocking = [issue for issue in issues if _blocks_build(issue)]
    if blocking:
        for issue in issues:
            print(issue.format())
        print()
        print("fix validation errors before build")
        return EXIT_FAILURE
    for issue in issues:
        if not _blocks_build(issue):  # warnings + idea-layer errors: informational; the build continues
            print(issue.format())
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/test_ideas.py tests/test_cli.py tests/test_review_fixes.py -v`
Expected: 全部 passed

- [ ] **Step 5: 提交**

```bash
git add src/planning_control_plane/cli.py tests/test_ideas.py
git commit -m "feat(ideas): focus/context hints for idea ids; build gate excludes idea-layer errors"
```

---

### Task 8: 全量回归与阶段 1 验收

**Files:** 无新改动（验证任务；若发现偏差，修复后重跑）

- [ ] **Step 1: 全量测试**

Run: `python -m pytest`
Expected: 既有 229 + 新增（约 40）全部 passed，0 failed。任何既有测试 FAIL 都是回归——修复后从 Task 1 的验收口径重查。

- [ ] **Step 2: 不变量的物理验证（spec §59）**

```bash
git diff main --stat src/planning_control_plane/context.py   # 期望：无输出（不变量 1）
git diff main src/planning_control_plane/model.py | grep -E "class Node|^[-+].*    (id|title|type|parent|status|objective|scope|out_of_scope|frozen_decisions|open_decisions|blocking_decisions|deferred_decisions|depends_on|blocks|related_to|supersedes|canonical_sources|evidence_sources|next_action|discussion_status|writeback_status|implementation_status|last_updated|unknown_fields|source_file):" | grep "^-"   # 期望：无输出（不变量 2：Node 字段零删改）
git diff main --stat src/planning_control_plane/graph.py     # 期望：无输出（§62.2）
```

- [ ] **Step 3: 端到端冒烟（真实命令流）**

```bash
cd "$(mktemp -d)" && git init smoke && cd smoke
mkdir -p .planning/nodes .planning/ideas docs
cat > .planning/project.yaml <<'EOF'
project:
  id: smoke
  name: Smoke
planning:
  current_focus: P1
EOF
printf 'nodes: []\n' > .planning/roadmap.yaml
cat > .planning/nodes/P1.yaml <<'EOF'
id: P1
title: 基线
type: PROGRAM
status: DONE
EOF
cat > .planning/ideas/IDEA-0001.yaml <<'EOF'
id: IDEA-0001
title: 冒烟想法
status: OPEN
relates_to: [P1]
benchmark_sources:
  - note: 某成熟产品的同类机制
last_updated: "2026-08-27"
EOF
printf 'broken: [yaml\n' > .planning/ideas/IDEA-BAD.yaml
pcp validate | tail -3        # 期望：1 error(s)（invalid-idea-file），退出码 1
pcp status                    # 期望：正常输出，退出码 0（失败域隔离）
pcp context                   # 期望：capsule 正常，退出码 0
pcp build                     # 期望：照常 Built N files，退出码 0（D59）
pcp ideas                     # 期望：== OPEN (1) == 与 IDEA-0001 行；BAD 文件被跳过
pcp ideas --for P1            # 期望：同一想法，via: P1
pcp focus IDEA-0001; echo $?  # 期望：1，错误含 "pcp ideas"
```

（`pcp` 不在 PATH 时用 `python -m planning_control_plane.cli` 等价执行；冒烟仓库用完即弃。）

- [ ] **Step 4: 提交收尾（如有未提交的修复）**

```bash
git status   # 期望 clean（specs/ 与 docs/superpowers/ 仍为未跟踪，属预期）
```

- [ ] **Step 5: 验收清单（对照 spec §62.1 阶段 1）**

- [ ] 既有 229 测试全绿
- [ ] 不变量 1/2/3/5/6 成立（Step 2 + 全量测试）
- [ ] 不变量 4 阶段 1 口径成立：无 `ideas/` 项目输出字节级不变（既有测试 + Step 3 冒烟中删除 ideas/ 后 `pcp build --check` 通过）
- [ ] 失败域用例：坏 YAML 想法文件存在时 `status`/`context`/`build` 仍成功（`test_cli_plan_commands_survive_broken_idea_file` + Step 3）

---

## Self-Review 记录

- **Spec 覆盖（阶段 1 范围）**：§51（Task 1–3）、§52（Task 2/4/5——加载解析、ref 校验、展示标记）、§53（Task 4）、§54.3（Task 5/6）、§55.5（Task 4）、§58 全部 18 规则（loader 9 条：Task 2/3；validator 9 条：Task 4）、§59 不变量（Task 7/8）、§60（Task 5–7）、§62.1 验收（Task 8）。§56/§61/§62.2 的 generator/i18n 部分属阶段 2，不在本计划。
- **占位符扫描**：Task 6 Step 1 中一段草稿断言已被紧随其后的清晰版本显式替换说明——实现时只采用清晰版本；除此之外无 TBD/TODO/无代码步骤。
- **类型一致性**：`idea_issue(severity, rule, detail, ident, node_id=None)` 在 Task 1 定义、Task 2/3/4 使用一致；`Idea` 字段名与 Task 5 的 `_idea_line`/`_idea_sort_key` 访问一致；`IDEA_RULE_NAMES` 在 Task 1 定义、Task 4 测试与 Task 7 门禁使用一致；`PlanningGraph` 仅在 `cmd_ideas` 使用（cli 新增 import）。

## 执行记录（2026-08-28，subagent-driven 执行后追加）

**计划内修正（计划文本自身矛盾，实现时以测试契约为准）：**

1. **测试 flag 顺序**（Task 5–7 测试）：全局 `-p` 必须位于子命令之前（argparse 约束，与既有 test_cli.py 全部 60+ 调用一致）；计划片段中的 `cli("ideas", ..., "-p", root)` 顺序不可执行。
2. **论据标记单空格**（Task 5）：计划钉死的行格式测试（`benchmark:Y methodology:N`）优先于代码片段的双空格 join——两个标记合并为一个展示列。
3. **行布局 vs spec D51 字面**（Task 5）：状态取自分组头、`last_updated` 移至第 2 列（优于逐行重复状态）；由计划的钉死测试固定。

**评审驱动的增量（超出计划文本、经双阶段评审批准）：**

4. `_read_idea_yaml` 捕获 `UnicodeDecodeError`——非 UTF-8 想法文件降级为 `invalid-idea-file` 而非崩溃（IDEA-D58 的"不可读"语义；Critical 修复）。
5. 非字符串 `ref`/`note` 发 WARNING（`invalid-idea-source`/`invalid-idea-outcome`）后丢弃，镜像 `_as_decisions` 的非字符串 `source` 先例——"不静默丢失"。
6. `pcp ideas` 末尾的 `note: N idea record(s) not shown ...; run 'pcp validate'`——无效状态/坏文件不再无声消失（有效状态过滤不触发）。
7. `_check_ideas` 根路径 normpath 对齐节点侧；`../` 逃逸分支钉死测试；GBK 文件、`.yml` 扫描、多目标 `via`、hint 缺席等若干钉死测试。
8. model/cli/validator 模块 docstring 补记想法层条目。

**环境备注：** 系统无 ensurepip，venv 由 `uv venv` 创建（CPython 3.14.3 + pytest 9.1.1 + PyYAML 6.0.3）。

**验收：** Task 8 全部通过——297 passed（229 基线 + 68 新增）；不变量 1/2 物理验证零 diff；不变量 4 以 dist 清单字节级一致验证；失败域用例（坏 YAML 下 status/context/build 全 exit 0）通过。

