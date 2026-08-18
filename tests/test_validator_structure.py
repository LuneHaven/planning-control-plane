"""Validator — structural rules: parents, cycles, edge targets, current focus
and controlled enums (spec §9, §10, §16).
"""

from __future__ import annotations

from planning_control_plane.loader import load_project
from planning_control_plane.validator import validate_project
from planning_control_plane.model import Severity


def build_issues(make_project, tmp_path, node_dicts, focus="A", roadmap_nodes=None):
    config = {
        "project": {"id": "t", "name": "T"},
        "planning": {"current_focus": focus},
    }
    project, _root = make_project(tmp_path, config_dict=config, node_dicts=node_dicts, roadmap_nodes=roadmap_nodes)
    return validate_project(project)


def test_baseline_project_validates_clean(make_project, tmp_path, node_dict, demo_root):
    # the shipped demo project is issue-free end to end
    assert validate_project(load_project(demo_root)) == []

    # ... and so is a minimal synthetic project (controls for every test below)
    issues = build_issues(
        make_project,
        tmp_path,
        [node_dict("A", status="DISCUSSING"), node_dict("B", parent="A")],
    )
    assert issues == []


# ------------------------------------------------------------ parent structure


def test_missing_parent_reports_error(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(make_project, tmp_path, [node_dict("A", parent="GHOST")])
    found = by_rule(issues, "missing-parent")
    assert len(found) == 1
    assert found[0].severity == Severity.ERROR
    assert found[0].node_id == "A"
    assert "GHOST" in found[0].message
    assert not by_rule(issues, "self-parent")


def test_self_parent_reports_error(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(make_project, tmp_path, [node_dict("A", parent="A")])
    found = by_rule(issues, "self-parent")
    assert len(found) == 1
    assert found[0].severity == Severity.ERROR
    assert found[0].node_id == "A"
    assert not by_rule(issues, "missing-parent")


def test_parent_cycle_reports_error(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(
        make_project,
        tmp_path,
        [node_dict("A", parent="B"), node_dict("B", parent="A")],
    )
    found = by_rule(issues, "parent-cycle")
    assert len(found) == 1
    assert found[0].severity == Severity.ERROR
    assert found[0].message == "A -> B -> A"


# ------------------------------------------------------------ dependency edges


def test_dependency_cycle_reports_error(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(
        make_project,
        tmp_path,
        [node_dict("A", depends_on=["B"]), node_dict("B", depends_on=["A"])],
    )
    found = by_rule(issues, "dependency-cycle")
    assert len(found) == 1
    assert found[0].severity == Severity.ERROR
    assert found[0].message == "A -> B -> A"


def test_missing_edge_targets_report_error(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(
        make_project,
        tmp_path,
        [
            node_dict("A", depends_on=["GHOST-DEP"], blocks=["GHOST-BLOCK"]),
            node_dict("B", related_to=["GHOST-REL"], supersedes=["GHOST-SUP"]),
        ],
        focus="A",
    )
    for rule, target in (
        ("missing-dependency-target", "GHOST-DEP"),
        ("missing-blocks-target", "GHOST-BLOCK"),
        ("missing-related-target", "GHOST-REL"),
        ("missing-supersedes-target", "GHOST-SUP"),
    ):
        found = by_rule(issues, rule)
        assert len(found) == 1, rule
        assert found[0].severity == Severity.ERROR
        assert target in found[0].message


def test_known_edge_targets_report_nothing(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(
        make_project,
        tmp_path,
        [node_dict("A", depends_on=["B"], blocks=["B"], related_to=["B"]), node_dict("B")],
    )
    assert issues == []


# ------------------------------------------------------------- current focus


def test_invalid_current_focus_reports_error(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(make_project, tmp_path, [node_dict("A")], focus="GHOST")
    found = by_rule(issues, "invalid-current-focus")
    assert len(found) == 1
    assert found[0].severity == Severity.ERROR
    assert found[0].node_id is None
    assert "GHOST" in found[0].message


def test_unset_current_focus_warns_when_nodes_exist(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(make_project, tmp_path, [node_dict("A")], focus=None)
    found = by_rule(issues, "current-focus-not-set")
    assert len(found) == 1
    assert found[0].severity == Severity.WARNING
    # a missing focus is not an error
    assert not [i for i in issues if i.severity == Severity.ERROR]


def test_unset_current_focus_is_silent_without_nodes(make_project, tmp_path):
    config = {"project": {"id": "t", "name": "T"}, "planning": {"current_focus": None}}
    project, _root = make_project(tmp_path, config_dict=config)
    assert validate_project(project) == []


def test_focus_on_done_node_warns(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(make_project, tmp_path, [node_dict("A", status="DONE")], focus="A")
    found = by_rule(issues, "focus-on-done")
    assert len(found) == 1
    assert found[0].severity == Severity.WARNING
    assert found[0].node_id == "A"


# ------------------------------------------------------------ controlled enums


def test_invalid_status_reports_error(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(make_project, tmp_path, [node_dict("A", status="DOING")])
    found = by_rule(issues, "invalid-status")
    assert len(found) == 1
    assert found[0].severity == Severity.ERROR
    assert found[0].node_id == "A"
    assert "DOING" in found[0].message


def test_invalid_type_reports_error(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(make_project, tmp_path, [node_dict("A", type="EPIC")])
    found = by_rule(issues, "invalid-type")
    assert len(found) == 1
    assert found[0].severity == Severity.ERROR
    assert found[0].node_id == "A"
    assert "EPIC" in found[0].message


def test_invalid_track_status_reports_error(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(make_project, tmp_path, [node_dict("A", discussion_status="SOMETIMES")])
    found = by_rule(issues, "invalid-track-status")
    assert len(found) == 1
    assert found[0].severity == Severity.ERROR
    assert found[0].node_id == "A"
    assert "'discussion_status'" in found[0].message


def test_na_track_alias_is_valid(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(
        make_project,
        tmp_path,
        [node_dict("A", writeback_status="N/A", implementation_status="NOT APPLICABLE")],
    )
    # every accepted N/A spelling normalizes to NOT_APPLICABLE and validates
    assert by_rule(issues, "invalid-track-status") == []
    assert issues == []


# ------------------------------------------------------------- decisions


def test_duplicate_decision_id_within_node_reports_error(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(
        make_project,
        tmp_path,
        [
            node_dict(
                "A",
                frozen_decisions=[{"id": "FD-1", "summary": "frozen"}],
                open_decisions=[{"id": "FD-1", "summary": "same id, other list"}],
            )
        ],
    )
    found = by_rule(issues, "duplicate-decision-id")
    assert len(found) == 1
    assert found[0].severity == Severity.ERROR
    assert found[0].node_id == "A"
    assert "FD-1" in found[0].message


def test_unknown_fields_warn(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(make_project, tmp_path, [node_dict("A", priority="high")])
    found = by_rule(issues, "unknown-field")
    assert len(found) == 1
    assert found[0].severity == Severity.WARNING
    assert "priority" in found[0].message
