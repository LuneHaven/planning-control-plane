"""Command-line interface for the Planning Control Plane (``pcp``).

Thin layer over the engine modules: every command loads the project through
the frozen loader API, delegates to validator / context / generator, and
formats plain terminal output (no colors).

Implemented commands (spec §4): ``init`` (§5), ``agents`` (INT-D1), ``validate``
(§16/§17), ``status`` (§18), ``context`` (§20/§21), ``focus`` (§19), ``ideas``
(§60), ``graduate`` (spec IDEA §55/§62.3) and ``build`` / ``build --check``
(§22/§23).

Exit codes:

* ``0`` — success;
* ``1`` — business failure (validation errors, unknown node, drift, ...);
* ``2`` — usage or load errors (bad arguments, ``LoadError``).

The global ``-p/--project-root`` option is the target repository root for
``init`` and the start directory for the upward ``.planning`` search used by
every other command (see :func:`planning_control_plane.loader.find_planning_dir`).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

from planning_control_plane import context
from planning_control_plane import generator
from planning_control_plane import loader
from planning_control_plane import validator
from planning_control_plane.graph import PlanningGraph
from planning_control_plane.model import (
    IDEA_RULE_NAMES,
    Idea,
    IdeaStatus,
    PCPError,
    PLANNING_DIR,
    Project,
    Severity,
    idea_sort_key,
)

#: Exit code: command succeeded.
EXIT_OK = 0
#: Exit code: business failure (validation errors, unknown node, drift).
EXIT_FAILURE = 1
#: Exit code: usage or load error (bad arguments, LoadError).
EXIT_USAGE = 2

#: Fallback project id when the directory name yields no usable slug.
_DEFAULT_PROJECT_ID = "unnamed-project"

#: Content written for a fresh ``roadmap.yaml`` (spec §5).
_ROADMAP_TEMPLATE = "nodes: []\n"

#: Content written for a fresh ``.planning/.gitignore``: generated output is
#: disposable and reproducible, so it is never committed.
_GITIGNORE_TEMPLATE = "dist/\n"

#: Template for a fresh ``project.yaml`` (spec §6). Comments explain the
#: purpose of each section; deliberately contains no backticks.
_PROJECT_TEMPLATE = """\
# Planning Control Plane — project configuration
project:
  id: {project_id}
  name: {project_name}
planning:
  # 当前讨论焦点节点 id；用 'pcp focus <node-id>' 切换
  current_focus: null
authority:
  # 可选：用于把链接分类为 canonical / current-state / planning
  canonical_roots: []
  current_state_roots: []
  planning_roots: []
output:
  directory: .planning/dist
"""

#: Matches one ``current_focus: ...`` line inside the planning section,
#: capturing indentation and the original line ending. Used by ``pcp focus``
#: for a line-oriented edit that preserves comments, layout and CRLF endings.
_FOCUS_LINE_RE = re.compile(r"^([ \t]*)current_focus:[ \t]*.*?(\r?\n?)$")

#: Matches the top-level ``planning:`` key (a trailing comment is allowed).
_PLANNING_KEY_RE = re.compile(r"^planning:")

#: Characters that make a plain (unquoted) YAML scalar ambiguous.
_UNSAFE_PLAIN_YAML_CHARS = frozenset(':#{}[]&*!|>' + "'\"%@`,")

#: Plain words YAML 1.1 would parse as booleans or null instead of strings.
_YAML_KEYWORDS = {"true", "false", "null", "yes", "no", "on", "off", "~"}

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

Fill `relates_to` with the node ids this thought touches: an idea with no entry
there hangs off no node, and `pcp ideas --for <node>` will never surface it.

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


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def _slugify(name: str) -> str:
    """Derive a project id from a directory name: lowercase, every character
    outside ``[a-z0-9-]`` becomes ``-``, leading/trailing ``-`` stripped."""
    slug = re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")
    return slug or _DEFAULT_PROJECT_ID


def _plain_scalar_round_trips(value: str) -> bool:
    """Whether a plain (unquoted) rendering of *value* parses back to the
    same string — refuses number/date/sequence look-alikes (``42``,
    ``2026-08-28``, ``- item``) that YAML would load as another type."""
    try:
        return yaml.safe_load(value) == value
    except yaml.YAMLError:
        return False


def _yaml_scalar(value: str) -> str:
    """Render *value* for the generated ``project.yaml``, quoting it when a
    plain rendering would not round-trip through the YAML parser."""
    if (
        value
        and value == value.strip()
        and value.lower() not in _YAML_KEYWORDS
        and not any(ch in _UNSAFE_PLAIN_YAML_CHARS for ch in value)
        and _plain_scalar_round_trips(value)
    ):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _oneline(text: str) -> str:
    """Collapse whitespace so multi-line YAML block scalars fit one line."""
    return " ".join(text.split())


def _idea_hint(project: Project, node_id: str) -> str:
    """IDEA-D52 suffix for unknown-node errors: an IDEA id is a natural
    mistake, and the thing the user needs to hear is that capsules and
    focus never carry ideas — 'pcp ideas' owns them."""
    if node_id in project.ideas:
        return f"; '{node_id}' is an IDEA record, see 'pcp ideas'"
    return ""


def _load_project(args: argparse.Namespace) -> Project | None:
    """Load the planning project for *args*.

    Returns ``None`` (after printing the error) when loading fails; callers
    turn that into ``EXIT_USAGE``.
    """
    try:
        return loader.load_project(Path(args.project_root))
    except loader.LoadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return None


def _set_current_focus(text: str, node_id: str) -> str:
    """Rewrite ``planning.current_focus`` in the raw ``project.yaml`` text.

    Line-oriented edit (never a full YAML rewrite) so comments, layout and
    line endings survive. The edit is scoped to the top-level ``planning:``
    section so a stray ``current_focus:`` key elsewhere (e.g. under
    ``project:``) is never touched, and duplicate ``current_focus`` lines
    inside the section are all rewritten to the same value so the file
    keeps a single effective key. If the section has no such line, one is
    inserted directly under ``planning:``; if there is no ``planning:``
    section at all, a minimal one is appended.
    """
    rendered = _yaml_scalar(node_id)
    default_eol = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)

    planning_start = None
    for index, line in enumerate(lines):
        if _PLANNING_KEY_RE.match(line):
            planning_start = index
            break

    if planning_start is None:
        if text and not text.endswith(("\n", "\r\n")):
            text += default_eol
        return f"{text}planning:{default_eol}  current_focus: {rendered}{default_eol}"

    # The section body runs until the next top-level key (a non-indented,
    # non-comment line).
    section_end = len(lines)
    for index in range(planning_start + 1, len(lines)):
        stripped = lines[index].rstrip("\r\n")
        if stripped and not stripped[0].isspace() and not stripped.startswith("#"):
            section_end = index
            break

    replaced = 0
    for index in range(planning_start + 1, section_end):
        raw = lines[index]
        body = raw.rstrip("\r\n")
        eol = raw[len(body) :] or default_eol
        match = _FOCUS_LINE_RE.match(body)
        if match:
            indent = match.group(1) or "  "
            lines[index] = f"{indent}current_focus: {rendered}{eol}"
            replaced += 1
    if replaced:
        return "".join(lines)

    # No current_focus line inside the section: insert right under the key,
    # adopting that line's own ending.
    anchor = lines[planning_start]
    anchor_eol = "\r\n" if anchor.endswith("\r\n") else ("\n" if anchor.endswith("\n") else default_eol)
    if not anchor.endswith(("\n", "\r\n")):
        lines[planning_start] = anchor + anchor_eol
    lines.insert(planning_start + 1, f"  current_focus: {rendered}{anchor_eol}")
    return "".join(lines)


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
    key when absent. The existing value must be a block list (an empty
    value counts); a flow list (``key: [a, b]``) or an explicit ``null``
    raises :class:`ValueError` so the caller can refuse before touching
    the file — appending to either cannot be done as a line edit without
    guessing the author's formatting.

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


# --------------------------------------------------------------------------
# command handlers (one per subcommand, each returns an exit code)
# --------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    """``pcp init [--force]`` — create the ``.planning`` skeleton (spec §5).

    Never overwrites an existing file, with or without ``--force``; ``--force``
    only allows filling in missing files when the project is already
    initialized.
    """
    root = Path(args.project_root)
    dir_name = root.resolve().name
    project_id = _slugify(dir_name)
    project_name = dir_name or _DEFAULT_PROJECT_ID

    planning_dir = root / PLANNING_DIR
    project_file = planning_dir / loader.PROJECT_FILE
    roadmap_file = planning_dir / loader.ROADMAP_FILE
    nodes_dir = planning_dir / loader.NODES_DIR
    gitignore_file = planning_dir / ".gitignore"

    if planning_dir.exists() and not planning_dir.is_dir():
        # A file where the planning directory should be can never be fixed
        # by --force (which only creates missing files, never overwrites).
        print(
            f"error: {planning_dir} exists and is not a directory; "
            "remove or rename it and run 'pcp init' again",
            file=sys.stderr,
        )
        return EXIT_FAILURE

    if planning_dir.exists() and not args.force:
        print(
            f"error: {planning_dir} already exists; refusing to touch an existing "
            "planning directory (--force only creates missing files, never overwrites)",
            file=sys.stderr,
        )
        return EXIT_FAILURE

    project_content = _PROJECT_TEMPLATE.format(
        project_id=_yaml_scalar(project_id),
        project_name=_yaml_scalar(project_name),
    )
    for directory in (planning_dir, nodes_dir):
        if directory.is_dir():
            print(f"kept existing: {directory}")
        else:
            directory.mkdir(parents=True, exist_ok=True)
            print(f"created: {directory}")
    for path, content in (
        (project_file, project_content),
        (roadmap_file, _ROADMAP_TEMPLATE),
        (gitignore_file, _GITIGNORE_TEMPLATE),
    ):
        if path.exists():
            print(f"kept existing: {path}")
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


def cmd_validate(args: argparse.Namespace) -> int:
    """``pcp validate`` — structural and consistency checks (spec §16/§17)."""
    project = _load_project(args)
    if project is None:
        return EXIT_USAGE

    issues = validator.validate_project(project)
    if not issues:
        print("OK: no issues found.")
        return EXIT_OK

    for issue in issues:
        print(issue.format())
    error_count = sum(1 for issue in issues if issue.severity == Severity.ERROR)
    warning_count = len(issues) - error_count
    print()
    print(f"{error_count} error(s), {warning_count} warning(s)")
    return EXIT_FAILURE if error_count else EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    """``pcp status`` — compact project overview (spec §18)."""
    project = _load_project(args)
    if project is None:
        return EXIT_USAGE

    print(f"Project: {project.config.name}")
    print()

    focus_id = project.config.current_focus
    focus = project.nodes.get(focus_id) if focus_id else None
    if focus is None:
        if focus_id:
            print(f"Current Focus: {focus_id} (missing)")
            print("note: configured current_focus does not match any node; run pcp validate")
        else:
            print("Current Focus: (not set)")
    else:
        print("Current Focus:")
        print(f"{focus.id} — {_oneline(focus.title)}")
        print(f"Status: {focus.status}")
        if focus.parent is None:
            print("Parent: (none)")
        else:
            parent = project.nodes.get(focus.parent)
            if parent is None:
                print(f"Parent: {focus.parent} (missing)")
            else:
                print(f"Parent: {parent.id} — {_oneline(parent.title)}")
        print(f"Blocking Decisions: {len(focus.blocking_decisions)}")
        print(f"Open Decisions: {len(focus.open_decisions)}")
        print(f"Next Action: {_oneline(focus.next_action) or '(none)'}")

    print()
    print("Progress:")
    counts = project.counts_by_status()
    for label, key in (
        ("Done", "done"),
        ("Active", "active"),
        ("Blocked", "blocked"),
        ("Pending", "pending"),
        ("Deferred", "deferred"),
    ):
        print(f"{label:<10}{counts[key]}")
    return EXIT_OK


def cmd_context(args: argparse.Namespace) -> int:
    """``pcp context [node_id] [--full]`` — session resume capsule (spec §20/§21)."""
    project = _load_project(args)
    if project is None:
        return EXIT_USAGE

    node_id = args.node_id or project.config.current_focus
    if not node_id:
        print(
            "error: no node id given and no current focus is configured; "
            "pass a node id or run 'pcp focus <node-id>'",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    if node_id not in project.nodes:
        print(f"error: unknown node '{node_id}'{_idea_hint(project, node_id)}", file=sys.stderr)
        return EXIT_FAILURE

    try:
        capsule = context.build_capsule(project, node_id, full=args.full)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    text = context.render_capsule(capsule)
    print(text, end="" if text.endswith("\n") else "\n")
    return EXIT_OK


def cmd_focus(args: argparse.Namespace) -> int:
    """``pcp focus [node_id]`` — show or switch the current focus (spec §19)."""
    project = _load_project(args)
    if project is None:
        return EXIT_USAGE

    current = project.config.current_focus
    if args.node_id is None:
        node = project.nodes.get(current) if current else None
        if current is None:
            print("(not set)")
        elif node is None:
            print(f"{current} (missing)")
        else:
            print(f"{current} — {_oneline(node.title)}")
        return EXIT_OK

    node_id = args.node_id
    node = project.nodes.get(node_id)
    if node is None:
        print(f"error: unknown node '{node_id}'{_idea_hint(project, node_id)}", file=sys.stderr)
        return EXIT_FAILURE

    config_path = project.planning_dir() / loader.PROJECT_FILE
    try:
        # newline="" on both ends: the edit must be line-oriented at the byte
        # level too, so CRLF files keep their original endings throughout.
        with config_path.open("r", encoding="utf-8", newline="") as handle:
            config_text = handle.read()
        new_text = _set_current_focus(config_text, node_id)
        config_path.write_text(new_text, encoding="utf-8", newline="")
    except OSError as exc:
        print(f"error: cannot update {config_path}: {exc}", file=sys.stderr)
        return EXIT_FAILURE

    # Verify the edit by re-parsing the written file: the effective
    # planning.current_focus must be exactly the requested node. If it is
    # not (unexpected project.yaml shape), roll back to the original text
    # rather than leave the config silently unchanged or corrupted.
    try:
        with config_path.open("r", encoding="utf-8", newline="") as handle:
            reparsed = yaml.safe_load(handle) or {}
        focus_now = (reparsed.get("planning") or {}).get("current_focus")
    except yaml.YAMLError:
        focus_now = None
    if focus_now != node_id:
        try:
            config_path.write_text(config_text, encoding="utf-8", newline="")
        except OSError:
            pass  # best-effort rollback; the verification error below still reports
        print(
            f"error: could not update planning.current_focus in {config_path} "
            "(unexpected file shape); the file was left unchanged — "
            "edit planning.current_focus manually",
            file=sys.stderr,
        )
        return EXIT_FAILURE

    print(f"Previous focus: {current if current else '(none)'}")
    print(f"New focus: {node.id} — {_oneline(node.title)}")
    return EXIT_OK


#: Display order of idea statuses in `pcp ideas` output (spec §60/IDEA-D51).
_IDEA_STATUS_ORDER = (
    IdeaStatus.OPEN.value,
    IdeaStatus.PARKED.value,
    IdeaStatus.PROMOTED.value,
    IdeaStatus.DISCARDED.value,
)

#: Idea-layer load rules whose records never reach the listing (cli note).
_HIDDEN_IDEA_RULES = frozenset({"invalid-idea-file", "invalid-idea", "duplicate-idea-id"})


def _idea_line(idea: Idea, via: list[str] | None) -> str:
    """One deterministic listing line (spec §60/IDEA-D51): id, date, title,
    relations, justification presence markers (IDEA-D22 — display, never
    validation), and — in query mode — which node matched.

    Columns are joined with two spaces; the two justification markers form
    a single tighter column (``benchmark:Y methodology:N``), as pinned by
    the line-format test."""
    justification = (
        "benchmark:" + ("Y" if idea.benchmark_sources else "N")
        + " methodology:" + ("Y" if idea.methodology_sources else "N")
    )
    parts = [
        idea.id,
        idea.last_updated or "-",
        _oneline(idea.title) or "-",
        "relates: " + (", ".join(dict.fromkeys(idea.relates_to)) if idea.relates_to else "-"),
        justification,
    ]
    if via is not None:
        parts.append("via: " + (", ".join(dict.fromkeys(via)) if via else "-"))
    return "  ".join(parts)


#: Ordering inside one status group — shared with the generated ideas page
#: so the two never disagree (spec IDEA-D61, defined in model.py).
_idea_sort_key = idea_sort_key

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

    # Records that this listing would have shown but cannot: files that never
    # parsed, entries dropped as unusable or duplicate, and loaded ideas whose
    # status falls outside the fixed group order. Ordinary status filtering
    # never counts — that is a display choice, not a data problem. Neither
    # does a record outside the --for scope: it was never part of this
    # listing, so reporting it here sends the reader after a phantom. Under
    # --for, file-level failures (unreadable/duplicate/unusable) carry no
    # relates_to to test against the scope, so they cannot be attributed to
    # this listing and are reported by the global listing / pcp validate only;
    # a loaded idea CAN be tested, and only counts when it hits the scope.
    hidden = 0
    if args.node is None:
        hidden += sum(1 for i in project.load_issues if i.rule in _HIDDEN_IDEA_RULES)
        hidden += sum(1 for idea in project.ideas.values() if idea.status not in _IDEA_STATUS_ORDER)
    else:
        hidden += sum(1 for idea, _via in selected if idea.status not in _IDEA_STATUS_ORDER)

    if shown == 0:
        if args.node is not None and any(groups[status] for status in _IDEA_STATUS_ORDER):
            print(f"no ideas match the requested status filter for node '{args.node}'" + (" (subtree)" if args.subtree else ""))
        elif args.node is not None:
            print(f"no matching ideas for node '{args.node}'" + (" (subtree)" if args.subtree else ""))
        elif project.ideas:
            print("no ideas match the requested status filter")
        elif hidden:
            print("idea files exist but could not be loaded; run 'pcp validate'")
        else:
            print("no ideas yet; add .planning/ideas/<id>.yaml")

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

    def _restore() -> bool:
        """Best-effort rollback. Returns True when both files match their
        original content afterwards — whether by write-back or because a
        file was never modified."""
        for path, text in ((idea_path, idea_text), (node_path, node_text)):
            try:
                if path.read_bytes() != text.encode("utf-8"):
                    path.write_text(text, encoding="utf-8", newline="")
            except OSError:
                return False  # best-effort rollback; the error below still reports
        return True

    try:
        idea_path.write_text(new_idea_text, encoding="utf-8", newline="")
        node_path.write_text(new_node_text, encoding="utf-8", newline="")
    except OSError as exc:
        if _restore():
            print(
                f"error: cannot write the graduation edits ({exc}); "
                "both files were restored to their previous content",
                file=sys.stderr,
            )
        else:
            print(
                f"error: cannot write the graduation edits ({exc}); "
                "the original files could not be fully restored — "
                "check them (git diff) before retrying",
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
            and (not args.note or check_idea.outcome.note == args.note.strip())
        )
    except loader.LoadError:
        ok = False
    if not ok:
        if _restore():
            print(
                f"error: graduation verification failed for idea '{idea.id}'; "
                "both files were restored to their previous content — "
                "edit them manually",
                file=sys.stderr,
            )
        else:
            print(
                f"error: graduation verification failed for idea '{idea.id}'; "
                "the original files could not be fully restored — "
                "check them (git diff) and edit manually",
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


def cmd_build(args: argparse.Namespace) -> int:
    """``pcp build [--check]`` — generate or verify the static site (spec §22/§23)."""
    project = _load_project(args)
    if project is None:
        return EXIT_USAGE

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

    if args.check:
        ok, messages = generator.check_build(project, project.output_dir())
        if ok:
            file_count = sum(1 for p in project.output_dir().rglob("*") if p.is_file())
            print(f"dist is up to date ({file_count} files)")
            return EXIT_OK
        for message in messages:
            print(message)
        print("drift detected; run pcp build")
        return EXIT_FAILURE

    paths = generator.build_site(project, project.output_dir())
    try:
        out_display = str(project.output_dir().relative_to(project.root))
    except ValueError:  # output directory configured outside the project root
        out_display = str(project.output_dir())
    ideas_part = " + ideas page" if project.ideas else ""
    print(
        f"Built {len(paths)} files into {out_display} "
        f"(index + {len(project.nodes)} node pages{ideas_part} + assets)"
    )
    return EXIT_OK


def cmd_agents(args: argparse.Namespace) -> int:
    """``pcp agents`` — print the AGENTS.md advisory snippet (spec INT-D1).

    Read-only by construction: no project is loaded and no file is written,
    AGENTS.md included. That file is a repository-level file owned by the
    user and sits outside the ``.planning`` data plane, so PCP prints and
    the user pastes (``pcp agents >> AGENTS.md`` is the one-liner).
    """
    print(_AGENTS_SNIPPET, end="")
    return EXIT_OK


# --------------------------------------------------------------------------
# parser wiring
# --------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build the ``pcp`` argument parser (help output is argparse's own)."""
    parser = argparse.ArgumentParser(
        prog="pcp",
        description=(
            "Planning Control Plane: repository-native planning context and "
            "progress control tool."
        ),
    )
    parser.add_argument(
        "-p",
        "--project-root",
        type=Path,
        default=Path("."),
        help="target repository root containing (or receiving) .planning; "
        "other commands search upward from it (default: current directory)",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="create the .planning skeleton in the target repository",
        description=(
            "Create .planning/{project.yaml, roadmap.yaml, nodes/, .gitignore}. "
            "Existing files are never overwritten; --force only fills in "
            "missing files in an already initialized project."
        ),
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="create missing files even when .planning/project.yaml already exists",
    )
    init_parser.set_defaults(func=cmd_init)

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

    validate_parser = subparsers.add_parser(
        "validate",
        help="validate the planning graph, nodes and configuration",
        description=(
            "Run structural checks (duplicate ids, cycles, missing parents or "
            "dependencies, invalid enums) and planning-consistency checks, "
            "then print every issue with its severity."
        ),
    )
    validate_parser.set_defaults(func=cmd_validate)

    status_parser = subparsers.add_parser(
        "status",
        help="show a compact overview of the project and current focus",
        description=(
            "Print project name, current focus node with status, parent, "
            "decision counts, next action and progress counts."
        ),
    )
    status_parser.set_defaults(func=cmd_status)

    context_parser = subparsers.add_parser(
        "context",
        help="print the session resume capsule for a node",
        description=(
            "Render the compact context capsule of a node (default: the "
            "configured current focus), suitable for pasting into a new "
            "chat or agent session."
        ),
    )
    context_parser.add_argument(
        "node_id",
        nargs="?",
        default=None,
        help="node id to render (default: the configured current focus)",
    )
    context_parser.add_argument(
        "--full",
        action="store_true",
        help="also include ancestor summaries, related nodes, dependency "
        "details, blocks/waited-by and deferred decisions",
    )
    context_parser.set_defaults(func=cmd_context)

    focus_parser = subparsers.add_parser(
        "focus",
        help="show or switch the current focus node",
        description=(
            "Without an argument, print the current focus. With a node id, "
            "update planning.current_focus in .planning/project.yaml "
            "(comments and layout are preserved)."
        ),
    )
    focus_parser.add_argument(
        "node_id",
        nargs="?",
        default=None,
        help="node id to focus on (omit to show the current focus)",
    )
    focus_parser.set_defaults(func=cmd_focus)

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

    build_parser = subparsers.add_parser(
        "build",
        help="generate the static HTML site under the output directory",
        description=(
            "Validate first, then rebuild the deterministic offline HTML "
            "projection under output.directory (default .planning/dist)."
        ),
    )
    build_parser.add_argument(
        "--check",
        action="store_true",
        help="verify the generated site is up to date without writing (for CI)",
    )
    build_parser.set_defaults(func=cmd_build)

    return parser


def _force_utf8_streams() -> None:
    """Pin ``stdout``/``stderr`` to UTF-8 on every platform.

    Windows encodes a **redirected** stdout with the ANSI code page (a
    console gets UTF-8), so without this the em dash in the ``pcp agents``
    snippet lands in AGENTS.md as a single non-UTF-8 byte — silently, exit
    0 — and ``pcp context`` on a Chinese project dies with
    ``UnicodeEncodeError`` under a Western code page. Everything this tool
    reads and writes as a file is UTF-8; its stream output is too.

    Streams that cannot be reconfigured (already replaced, or detached) are
    left alone: this is a best-effort hardening, never a reason to fail.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``pcp`` console script."""
    _force_utf8_streams()
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (PCPError, OSError) as exc:
        # Engine or filesystem failures degrade to a clean message instead
        # of a traceback; LoadError is already handled per command.
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
