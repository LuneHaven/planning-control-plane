"""Regression tests for defects found by the V0.1 adversarial review.

Each test pins one confirmed review finding so the same class of bug cannot
silently return: unsafe build output directories (data loss), the
authority-classify prefix bug, empty enum values bypassing validation,
duplicate YAML keys collapsing silently, ignored node files disappearing,
unsafe ``pcp focus`` rewrites (stray/duplicate keys, CRLF loss, failed-edit
rollback), missing out-of-scope inheritance, and the dangling-focus status
display.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest
import yaml

from planning_control_plane import context, generator
from planning_control_plane.loader import LoadError, load_project
from planning_control_plane.model import AuthorityConfig, PCPError, Severity
from planning_control_plane.validator import validate_project

from conftest import write_planning

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2


def _build(make_project, tmp_path, *, output_directory: str, nodes: list):
    config = {
        "project": {"id": "t", "name": "T"},
        "planning": {"current_focus": "N1"},
    }
    if output_directory is not None:
        config["output"] = {"directory": output_directory}
    return make_project(tmp_path, config_dict=config, node_dicts=nodes)


# --------------------------------------------------------------- build safety


def test_unsafe_output_directory_is_a_validation_error(make_project, tmp_path, node_dict, by_rule):
    """output.directory that would delete .planning on rebuild → ERROR."""
    project, _root = _build(make_project, tmp_path, output_directory=".planning", nodes=[node_dict("N1")])
    issues = by_rule(validate_project(project), "unsafe-output-directory")
    assert issues and issues[0].severity == Severity.ERROR


def test_repository_root_as_output_directory_is_rejected(make_project, tmp_path, node_dict, by_rule):
    project, _root = _build(make_project, tmp_path, output_directory=".", nodes=[node_dict("N1")])
    assert by_rule(validate_project(project), "unsafe-output-directory")


def test_normal_output_directory_passes(make_project, tmp_path, node_dict, by_rule):
    project, _root = _build(
        make_project, tmp_path, output_directory=".planning/dist", nodes=[node_dict("N1")]
    )
    assert not by_rule(validate_project(project), "unsafe-output-directory")


def test_build_refuses_unsafe_output_directory_and_keeps_data(demo_copy, cli):
    """The end-to-end guard: pcp build must refuse and leave data intact."""
    config_path = demo_copy / ".planning" / "project.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["output"]["directory"] = ".planning"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    code, out, _err = cli("-p", str(demo_copy), "build")
    assert code == EXIT_FAILURE
    assert "unsafe-output-directory" in out
    assert "fix validation errors before build" in out
    # Planning data survived untouched.
    assert (demo_copy / ".planning" / "project.yaml").is_file()
    assert (demo_copy / ".planning" / "nodes" / "P2-A4.yaml").is_file()
    assert not (demo_copy / ".planning" / "index.html").exists()


def test_generator_api_also_refuses_unsafe_output_directory(make_project, tmp_path, node_dict):
    """Defense in depth: generator.build_site raises even without the CLI."""
    project, root = _build(make_project, tmp_path, output_directory=".", nodes=[node_dict("N1")])
    with pytest.raises(PCPError):
        generator.build_site(project, root)  # repository root contains .planning
    assert (root / ".planning" / "project.yaml").is_file()


# ------------------------------------------------------- authority classify


def test_classify_matches_dot_directories_and_prefixes():
    """str.lstrip('./') bug regression: dot-directory roots must classify."""
    authority = AuthorityConfig(
        canonical_roots=["docs/rollout"],
        current_state_roots=["docs/notes"],
        planning_roots=[".planning"],
    )
    assert authority.classify(".planning/roadmap.yaml") == "planning"
    assert authority.classify("./docs/rollout/a.md") == "canonical"
    assert authority.classify("docs/notes/n.md") == "current-state"
    assert authority.classify("docs/other.md") == ""
    # A same-stem sibling must not match a directory root (docs/x vs docs/x.md).
    assert AuthorityConfig(canonical_roots=["docs/x"]).classify("docs/x.md") == ""


# --------------------------------------------------- loader / validator holes


def test_empty_type_and_status_are_rejected(make_project, tmp_path, node_dict, by_rule):
    """"type: ''" must not silently become DISCUSSING."""
    project, _root = make_project(
        tmp_path, node_dicts=[node_dict("N1", type="", status="")]
    )
    issues = validate_project(project)
    assert by_rule(issues, "invalid-type") and by_rule(issues, "invalid-status")
    assert project.nodes["N1"].type == ""
    assert project.nodes["N1"].status == ""


def test_null_type_still_falls_back_to_default(make_project, tmp_path, node_dict, by_rule):
    """`type:` (null) behaves like an absent key — default, no error."""
    project, _root = make_project(tmp_path, node_dicts=[node_dict("N1", type=None)])
    assert project.nodes["N1"].type == "DISCUSSION"
    assert not by_rule(validate_project(project), "invalid-type")


def test_duplicate_yaml_keys_fail_the_load(tmp_path):
    """Two `nodes:` blocks must not quietly drop the first block."""
    root = tmp_path / "repo"
    raw = "nodes:\n- id: A\n  title: A\nnodes:\n- id: B\n  title: B\n"
    write_planning(root, raw_files={"roadmap.yaml": raw})
    with pytest.raises(LoadError, match="(?i)duplicate"):
        load_project(root)


def test_ignored_node_files_produce_a_warning(tmp_path, node_dict, by_rule):
    """.yml files and nested node files must not vanish silently."""
    root = tmp_path / "repo"
    write_planning(root, node_dicts=[node_dict("N1")])
    nodes = root / ".planning" / "nodes"
    (nodes / "extra.yml").write_text("id: X\n", encoding="utf-8")
    (nodes / "sub").mkdir()
    (nodes / "sub" / "nested.yaml").write_text("id: Y\n", encoding="utf-8")

    warnings = by_rule(validate_project(load_project(root)), "ignored-node-file")
    assert {w.message.split("'")[1] for w in warnings} == {
        ".planning/nodes/extra.yml",
        ".planning/nodes/sub/nested.yaml",
    }


# ------------------------------------------------------------ pcp focus safety


def _focus_project(tmp_path, node_dicts, project_yaml: str) -> Path:
    root = tmp_path / "repo"
    write_planning(root, node_dicts=node_dicts, raw_files={"project.yaml": project_yaml})
    return root


_STRAY_FOCUS_YAML = (
    "# top comment\n"
    "project:\n"
    "  id: t\n"
    "  name: T\n"
    "  current_focus: WRONG-PLACE\n"
    "planning:\n"
    "  # focus lives here\n"
    "  current_focus: P1\n"
    "authority: {}\n"
)


def test_focus_rewrites_only_the_planning_section(tmp_path, cli, node_dict):
    root = _focus_project(
        tmp_path,
        [node_dict("P1", title="One"), node_dict("P2", title="Two")],
        _STRAY_FOCUS_YAML,
    )
    code, out, _err = cli("-p", str(root), "focus", "P2")
    assert code == EXIT_OK
    assert "New focus: P2 — Two" in out

    text = (root / ".planning" / "project.yaml").read_text(encoding="utf-8")
    assert re.search(r"^  current_focus: P2$", text, re.MULTILINE)
    assert "current_focus: WRONG-PLACE" in text  # the stray key under project: untouched
    reparsed = yaml.safe_load(text)
    assert reparsed["planning"]["current_focus"] == "P2"
    assert reparsed["project"]["current_focus"] == "WRONG-PLACE"


def test_duplicate_current_focus_keys_are_rejected_at_load(tmp_path, cli, node_dict):
    """A project.yaml with duplicate current_focus keys is ambiguous YAML:
    loading fails loudly (LoadError, exit 2) instead of letting `pcp focus`
    edit a file whose effective value depends on parser tie-breaking."""
    raw = (
        "project:\n  id: t\n  name: T\n"
        "planning:\n"
        "  current_focus: P1\n"
        "  current_focus: P1\n"
    )
    root = _focus_project(tmp_path, [node_dict("P1")], raw)
    code, _out, err = cli("-p", str(root), "focus", "P1")
    assert code == EXIT_USAGE
    assert "duplicate" in err.lower()


def test_focus_preserves_crlf_line_endings(tmp_path, cli, node_dict):
    raw_crlf = (
        "# comment\r\n"
        "project:\r\n"
        "  id: t\r\n"
        "  name: T\r\n"
        "planning:\r\n"
        "  current_focus: P1\r\n"
    )
    root = _focus_project(
        tmp_path, [node_dict("P1"), node_dict("P2", title="Two")], raw_crlf
    )
    code, _out, _err = cli("-p", str(root), "focus", "P2")
    assert code == EXIT_OK
    # Byte-level check: read_text would mask CRLF via universal newlines.
    data = (root / ".planning" / "project.yaml").read_bytes().decode("utf-8")
    assert "\n" not in data.replace("\r\n", "")  # every line ending stayed CRLF
    assert "current_focus: P2\r\n" in data


def test_focus_rolls_back_when_edit_would_not_take_effect(tmp_path, cli, node_dict, monkeypatch):
    """If the post-write verification fails, the original file is restored."""
    root = _focus_project(
        tmp_path,
        [node_dict("P1")],
        "project:\n  id: t\n  name: T\nplanning:\n  current_focus: null\n",
    )
    config_path = root / ".planning" / "project.yaml"
    original = config_path.read_text(encoding="utf-8")

    import planning_control_plane.cli as cli_module

    real_writer = cli_module._set_current_focus

    def sabotaging_writer(text: str, node_id: str) -> str:
        # Simulate an edit that does not take effect (stale value on disk).
        return real_writer(text, node_id).replace(f"current_focus: {node_id}", "current_focus: STALE")

    monkeypatch.setattr(cli_module, "_set_current_focus", sabotaging_writer)
    code, _out, err = cli("-p", str(root), "focus", "P1")
    assert code == EXIT_FAILURE
    assert "left unchanged" in err
    assert config_path.read_text(encoding="utf-8") == original  # rolled back


# ------------------------------------------------------ context inheritance


def test_capsule_inherits_out_of_scope_and_shadows_own(make_project, tmp_path, node_dict):
    project, _root = make_project(
        tmp_path,
        node_dicts=[
            node_dict(
                "P1",
                type="PROGRAM",
                status="DONE",
                scope=["program scope item"],
                out_of_scope=["program out item", "shared item"],
            ),
            node_dict(
                "C1",
                parent="P1",
                scope=["child scope"],
                out_of_scope=["shared item"],  # declared by the child itself
            ),
        ],
    )
    capsule = context.build_capsule(project, "C1")
    assert ("P1", "program out item") in capsule.inherited_out_of_scope
    assert ("P1", "shared item") not in capsule.inherited_out_of_scope  # own shadow
    assert ("P1", "program scope item") in capsule.inherited_scope

    rendered = context.render_capsule(capsule)
    assert "Inherited Out-of-Scope Guardrails:" in rendered
    assert "[P1] program out item" in rendered


def test_capsule_inherited_scope_shadows_own_items(make_project, tmp_path, node_dict):
    project, _root = make_project(
        tmp_path,
        node_dicts=[
            node_dict("P1", type="PROGRAM", scope=["same scope text"]),
            node_dict("C1", parent="P1", scope=["same scope text"]),
        ],
    )
    capsule = context.build_capsule(project, "C1")
    assert capsule.inherited_scope == []  # already in the node's own In Scope


def test_capsule_squeezes_multiline_decision_source(make_project, tmp_path, node_dict):
    project, _root = make_project(
        tmp_path,
        node_dicts=[
            node_dict(
                "P1",
                type="PROGRAM",
                frozen_decisions=[{"id": "FD-1", "summary": "s", "source": "docs/a.md\nsecond line"}],
            ),
            node_dict("C1", parent="P1"),
        ],
    )
    rendered = context.render_capsule(context.build_capsule(project, "C1"))
    line = next(line for line in rendered.splitlines() if "FD-1" in line)
    assert line.strip().endswith("(source: docs/a.md second line)")


# ---------------------------------------------------------------- CLI display


def test_status_shows_dangling_focus_id(cli, node_dict):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        write_planning(
            root,
            config_dict={"project": {"id": "t", "name": "T"}, "planning": {"current_focus": "GHOST"}},
            node_dicts=[node_dict("N1")],
        )
        code, out, _err = cli("-p", str(root), "status")
        assert code == EXIT_OK
        assert "Current Focus: GHOST (missing)" in out
        assert "(not set)" not in out


# ------------------------------------------------------------- filename safety


def test_safe_id_collision_produces_distinct_pages(make_project, tmp_path, node_dict):
    """Ids sanitizing to the same stem must not overwrite each other."""
    project, _root = make_project(tmp_path, node_dicts=[node_dict("A B"), node_dict("A_B")])
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "dist"
        generator.build_site(project, out)
        stems = sorted(path.stem for path in (out / "nodes").glob("*.html"))
        assert stems == ["A_B", "A_B-2"]
        texts = {path.name: path.read_text(encoding="utf-8") for path in (out / "nodes").glob("*.html")}
        assert "A B" in texts["A_B.html"]
        assert "A_B" in texts["A_B-2.html"]


# ------------------------------------------------------------- track aliases


def test_track_alias_period_spelling_normalizes(make_project, tmp_path, node_dict):
    project, _root = make_project(
        tmp_path, node_dicts=[node_dict("N1", implementation_status="N.A.")]
    )
    assert project.nodes["N1"].implementation_status == "NOT_APPLICABLE"
