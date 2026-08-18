"""CLI behaviour and exit codes: validate, status, context, focus (spec §4,
§16–§21). Commands run in-process through ``cli.main``; the load-error
contract (exit 2) is covered as well.
"""

from __future__ import annotations

import re

from planning_control_plane.cli import EXIT_FAILURE, EXIT_OK, EXIT_USAGE
from planning_control_plane.loader import load_project


# ------------------------------------------------------------------ validate


def test_validate_clean_project_exit_zero(demo_root, cli):
    code, out, err = cli("-p", str(demo_root), "validate")
    assert code == EXIT_OK
    assert "OK: no issues found." in out
    assert err == ""


def test_validate_reports_errors_exit_one(make_project, tmp_path, node_dict, cli):
    project_root = tmp_path / "repo"
    project_root.mkdir()
    (project_root / ".planning" / "nodes").mkdir(parents=True)
    (project_root / ".planning" / "project.yaml").write_text(
        "project:\n  id: t\n  name: T\nplanning:\n  current_focus: A\n", encoding="utf-8"
    )
    (project_root / ".planning" / "nodes" / "A.yaml").write_text(
        "id: A\ntitle: A\nstatus: DOING\n", encoding="utf-8"
    )

    code, out, err = cli("-p", str(project_root), "validate")

    assert code == EXIT_FAILURE
    assert "invalid-status" in out
    assert "DOING" in out
    assert re.search(r"^ERROR\s+A\s+invalid-status:", out, re.MULTILINE)
    assert "1 error(s), 0 warning(s)" in out


def test_validate_warnings_only_exit_zero(make_project, tmp_path, node_dict, cli):
    project, _root = make_project(tmp_path, node_dicts=[node_dict("A")])  # focus unset
    code, out, err = cli("-p", str(_root), "validate")
    assert code == EXIT_OK
    assert "current-focus-not-set" in out
    assert "0 error(s), 1 warning(s)" in out


def test_validate_from_nested_directory_uses_upward_search(demo_root, cli):
    code, out, _err = cli("-p", str(demo_root / "docs" / "rollout"), "validate")
    assert code == EXIT_OK


# -------------------------------------------------------------------- status


def test_status_shows_focus_and_progress(demo_root, cli):
    code, out, err = cli("-p", str(demo_root), "status")
    assert code == EXIT_OK
    assert "Project: Demo Project" in out
    assert "Current Focus:" in out
    assert "P2-A4 — Rollout Readiness Preflight" in out
    assert "Status: NOT_STARTED" in out
    assert "Parent: P2-A — Rollout Strategy" in out
    assert "Blocking Decisions: 1" in out
    assert "Open Decisions: 1" in out
    assert "Resolve BD-401" in out  # next action (single line)
    # progress counts for the demo tree: 4 DONE, 2 active, 1 pending
    assert re.search(r"^Done\s+4$", out, re.MULTILINE)
    assert re.search(r"^Active\s+2$", out, re.MULTILINE)
    assert re.search(r"^Pending\s+1$", out, re.MULTILINE)
    assert re.search(r"^Blocked\s+0$", out, re.MULTILINE)
    assert re.search(r"^Deferred\s+0$", out, re.MULTILINE)


def test_status_without_focus_reports_not_set(make_project, tmp_path, node_dict, cli):
    project, root = make_project(tmp_path, node_dicts=[node_dict("A")])
    code, out, _err = cli("-p", str(root), "status")
    assert code == EXIT_OK
    assert "Current Focus: (not set)" in out


# ------------------------------------------------------------------- context


def test_context_defaults_to_current_focus_compact(demo_root, cli):
    code, out, err = cli("-p", str(demo_root), "context")
    assert code == EXIT_OK
    assert "Node: P2-A4 — Rollout Readiness Preflight (DISCUSSION / NOT_STARTED)" in out
    assert "Mode: compact" in out
    assert "Mode: full" not in out
    assert "=== END CAPSULE ===" in out


def test_context_full_flag_adds_sections(demo_root, cli):
    code, out, _err = cli("-p", str(demo_root), "context", "P2-A4", "--full")
    assert code == EXIT_OK
    assert "Mode: full" in out
    for header in ("Ancestor Summaries:", "Related Nodes:", "Dependencies:", "Blocks / Waited By:"):
        assert header in out, header


def test_context_unknown_node_exits_one(demo_root, cli):
    code, out, err = cli("-p", str(demo_root), "context", "GHOST")
    assert code == EXIT_FAILURE
    assert "unknown node 'GHOST'" in err


def test_context_without_node_and_focus_exits_one(make_project, tmp_path, node_dict, cli):
    project, root = make_project(tmp_path, node_dicts=[node_dict("A")])  # focus unset
    code, out, err = cli("-p", str(root), "context")
    assert code == EXIT_FAILURE
    assert "no node id given" in err


# --------------------------------------------------------------------- focus


def test_focus_show_prints_current(demo_root, cli):
    code, out, err = cli("-p", str(demo_root), "focus")
    assert code == EXIT_OK
    assert "P2-A4 — Rollout Readiness Preflight" in out


def test_focus_show_when_unset(make_project, tmp_path, node_dict, cli):
    project, root = make_project(tmp_path, node_dicts=[node_dict("A")])
    code, out, _err = cli("-p", str(root), "focus")
    assert code == EXIT_OK
    assert "(not set)" in out


def test_focus_switch_rewrites_config_and_preserves_comments(demo_copy, cli):
    config_path = demo_copy / ".planning" / "project.yaml"
    original_lines = config_path.read_text(encoding="utf-8").splitlines(keepends=True)

    code, out, err = cli("-p", str(demo_copy), "focus", "P2-A1")

    assert code == EXIT_OK
    assert "Previous focus: P2-A4" in out
    assert "New focus: P2-A1 — Survey Existing Rollout Docs" in out

    new_lines = config_path.read_text(encoding="utf-8").splitlines(keepends=True)
    # exactly one line changed: the focus line itself
    changed = [(old, new) for old, new in zip(original_lines, new_lines) if old != new]
    assert changed == [("  current_focus: P2-A4\n", "  current_focus: P2-A1\n")]
    # every comment line survived verbatim, including the one above the focus
    assert [line for line in original_lines if line.lstrip().startswith("#")] == [
        line for line in new_lines if line.lstrip().startswith("#")
    ]

    # the switch is visible to the next load
    assert load_project(demo_copy).config.current_focus == "P2-A1"


def test_focus_switch_from_null_reports_none_previous(make_project, tmp_path, node_dict, cli):
    project, root = make_project(tmp_path, node_dicts=[node_dict("A"), node_dict("B")])
    code, out, err = cli("-p", str(root), "focus", "B")
    assert code == EXIT_OK
    assert "Previous focus: (none)" in out
    assert "New focus: B" in out
    assert load_project(root).config.current_focus == "B"


def test_focus_switch_inserts_line_under_planning_section(make_project, tmp_path, node_dict, cli):
    """No current_focus line yet: the switch inserts one under planning:."""
    project, root = make_project(
        tmp_path,
        node_dicts=[node_dict("A"), node_dict("B")],
        raw_files={
            "project.yaml": (
                "# comment header\n"
                "project:\n"
                "  id: t\n"
                "  name: T\n"
                "planning:\n"
                "  # focus not yet chosen\n"
            )
        },
    )
    code, out, _err = cli("-p", str(root), "focus", "B")
    assert code == EXIT_OK

    lines = (root / ".planning" / "project.yaml").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "# comment header"
    # the new line is inserted directly under the planning: key, and every
    # pre-existing comment survives the edit
    planning_index = lines.index("planning:")
    assert lines[planning_index + 1] == "  current_focus: B"
    assert "  # focus not yet chosen" in lines
    assert lines.index("  # focus not yet chosen") > planning_index
    assert load_project(root).config.current_focus == "B"


def test_focus_switch_appends_planning_section_when_missing(make_project, tmp_path, node_dict, cli):
    """No planning section at all: one is appended with the focus."""
    project, root = make_project(
        tmp_path,
        node_dicts=[node_dict("A"), node_dict("B")],
        raw_files={"project.yaml": "project:\n  id: t\n  name: T\n"},
    )
    code, out, _err = cli("-p", str(root), "focus", "A")
    assert code == EXIT_OK
    text = (root / ".planning" / "project.yaml").read_text(encoding="utf-8")
    assert text == "project:\n  id: t\n  name: T\nplanning:\n  current_focus: A\n"
    assert load_project(root).config.current_focus == "A"


def test_focus_unknown_node_exits_one_without_writing(demo_root, cli):
    config_path = demo_root / ".planning" / "project.yaml"
    before = config_path.read_text(encoding="utf-8")

    code, out, err = cli("-p", str(demo_root), "focus", "GHOST")

    assert code == EXIT_FAILURE
    assert "unknown node 'GHOST'" in err
    assert config_path.read_text(encoding="utf-8") == before


# ---------------------------------------------------------------- load errors


def test_freshly_initialized_project_end_to_end(tmp_path, cli):
    """The documented first-run journey: init -> validate -> build -> check."""
    root = tmp_path / "fresh"
    root.mkdir()
    assert cli("-p", str(root), "init")[0] == EXIT_OK

    code, out, _err = cli("-p", str(root), "validate")
    assert code == EXIT_OK
    assert "OK: no issues found." in out

    code, out, _err = cli("-p", str(root), "status")
    assert code == EXIT_OK
    assert "Current Focus: (not set)" in out

    code, out, _err = cli("-p", str(root), "build")
    assert code == EXIT_OK
    assert "Built 3 files into .planning/dist" in out  # index + assets, no nodes yet

    code, out, _err = cli("-p", str(root), "build", "--check")
    assert code == EXIT_OK
    assert "dist is up to date (3 files)" in out

    # nothing to resume yet: context fails cleanly
    assert cli("-p", str(root), "context")[0] == EXIT_FAILURE


def test_command_on_uninitialized_repo_exits_two(tmp_path, cli):
    empty = tmp_path / "empty"
    empty.mkdir()
    code, out, err = cli("-p", str(empty), "status")
    assert code == EXIT_USAGE
    assert "error:" in err
