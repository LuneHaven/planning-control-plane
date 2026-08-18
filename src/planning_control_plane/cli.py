"""Command-line interface for the Planning Control Plane (``pcp``).

Thin layer over the engine modules: every command loads the project through
the frozen loader API, delegates to validator / context / generator, and
formats plain terminal output (no colors).

Implemented commands (spec §4): ``init`` (§5), ``validate`` (§16/§17),
``status`` (§18), ``context`` (§20/§21), ``focus`` (§19) and ``build`` /
``build --check`` (§22/§23).

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
from planning_control_plane.model import PCPError, PLANNING_DIR, Project, Severity

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


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------


def _slugify(name: str) -> str:
    """Derive a project id from a directory name: lowercase, every character
    outside ``[a-z0-9-]`` becomes ``-``, leading/trailing ``-`` stripped."""
    slug = re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")
    return slug or _DEFAULT_PROJECT_ID


def _yaml_scalar(value: str) -> str:
    """Render *value* for the generated ``project.yaml``, quoting it when a
    plain rendering would not round-trip through the YAML parser."""
    if (
        value
        and value == value.strip()
        and value.lower() not in _YAML_KEYWORDS
        and not any(ch in _UNSAFE_PLAIN_YAML_CHARS for ch in value)
    ):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _oneline(text: str) -> str:
    """Collapse whitespace so multi-line YAML block scalars fit one line."""
    return " ".join(text.split())


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
        print(f"error: unknown node '{node_id}'", file=sys.stderr)
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
        print(f"error: unknown node '{node_id}'", file=sys.stderr)
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


def cmd_build(args: argparse.Namespace) -> int:
    """``pcp build [--check]`` — generate or verify the static site (spec §22/§23)."""
    project = _load_project(args)
    if project is None:
        return EXIT_USAGE

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
    print(
        f"Built {len(paths)} files into {out_display} "
        f"(index + {len(project.nodes)} node pages + assets)"
    )
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


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``pcp`` console script."""
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
