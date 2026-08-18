"""Validator — planning-consistency rules (spec §13, §16) and reference
validation (spec §17).
"""

from __future__ import annotations

from planning_control_plane.model import Severity
from planning_control_plane.validator import validate_project


def build_issues(make_project, tmp_path, node_dicts, focus="A", repo_files=None):
    config = {
        "project": {"id": "t", "name": "T"},
        "planning": {"current_focus": focus},
    }
    project, _root = make_project(
        tmp_path, config_dict=config, node_dicts=node_dicts, repo_files=repo_files
    )
    return validate_project(project)


# --------------------------------------------------- planning consistency rules


def test_done_with_blocking_decision_is_error(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(
        make_project,
        tmp_path,
        [node_dict("A", status="DONE", blocking_decisions=[{"id": "BD-1", "summary": "still open"}])],
    )
    found = by_rule(issues, "done-with-blocking-decision")
    assert len(found) == 1
    assert found[0].severity == Severity.ERROR
    assert found[0].node_id == "A"
    assert "BD-1" in found[0].message


def test_done_with_empty_blocking_decisions_is_fine(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(
        make_project,
        tmp_path,
        [node_dict("A", status="DONE", blocking_decisions=[])],
    )
    assert by_rule(issues, "done-with-blocking-decision") == []


def test_blocked_without_any_blocker_info_warns(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(make_project, tmp_path, [node_dict("A", status="BLOCKED")])
    found = by_rule(issues, "blocked-without-blocker")
    assert len(found) == 1
    assert found[0].severity == Severity.WARNING
    assert found[0].node_id == "A"


def test_blocked_with_blocking_decision_has_no_warning(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(
        make_project,
        tmp_path,
        [node_dict("A", status="BLOCKED", blocking_decisions=[{"id": "BD-1", "summary": "gate"}])],
    )
    assert by_rule(issues, "blocked-without-blocker") == []


def test_blocked_with_unfinished_dependency_has_no_warning(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(
        make_project,
        tmp_path,
        [
            node_dict("A", status="BLOCKED", depends_on=["DEP"]),
            node_dict("DEP", status="IMPLEMENTING"),
        ],
    )
    assert by_rule(issues, "blocked-without-blocker") == []


def test_blocked_with_deferred_dependency_has_no_warning(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(
        make_project,
        tmp_path,
        [
            node_dict("A", status="BLOCKED", depends_on=["DEP"]),
            node_dict("DEP", status="DEFERRED"),
        ],
    )
    assert by_rule(issues, "blocked-without-blocker") == []
    # the deferred dependency is still surfaced, as its own warning
    deferred = by_rule(issues, "depends-on-deferred")
    assert len(deferred) == 1
    assert deferred[0].severity == Severity.WARNING
    assert deferred[0].node_id == "A"


def test_writeback_done_without_canonical_source_warns(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(make_project, tmp_path, [node_dict("A", writeback_status="DONE")])
    found = by_rule(issues, "writeback-done-without-canonical-source")
    assert len(found) == 1
    assert found[0].severity == Severity.WARNING
    assert found[0].node_id == "A"


def test_writeback_done_with_canonical_source_is_fine(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(
        make_project,
        tmp_path,
        [node_dict("A", writeback_status="DONE", canonical_sources=["docs/spec.md"])],
        repo_files={"docs/spec.md": "# spec"},
    )
    assert by_rule(issues, "writeback-done-without-canonical-source") == []
    assert issues == []


def test_depends_on_deferred_node_warns(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(
        make_project,
        tmp_path,
        [node_dict("A", depends_on=["LATER"]), node_dict("LATER", status="DEFERRED")],
    )
    found = by_rule(issues, "depends-on-deferred")
    assert len(found) == 1
    assert found[0].severity == Severity.WARNING
    assert found[0].node_id == "A"
    assert "LATER" in found[0].message


# ---------------------------------------------------------- reference validation


def test_missing_canonical_source_is_error(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(
        make_project,
        tmp_path,
        [node_dict("A", canonical_sources=["docs/missing.md"])],
    )
    found = by_rule(issues, "canonical-source-missing")
    assert len(found) == 1
    assert found[0].severity == Severity.ERROR
    assert found[0].node_id == "A"
    assert "docs/missing.md" in found[0].message


def test_missing_evidence_source_is_warning(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(
        make_project,
        tmp_path,
        [node_dict("A", evidence_sources=["docs/gone.md"])],
    )
    found = by_rule(issues, "evidence-source-missing")
    assert len(found) == 1
    assert found[0].severity == Severity.WARNING
    assert found[0].node_id == "A"
    # a missing evidence file must not be reported as a canonical problem
    assert by_rule(issues, "canonical-source-missing") == []


def test_existing_sources_validate_clean(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(
        make_project,
        tmp_path,
        [
            node_dict(
                "A",
                canonical_sources=["docs/spec.md"],
                evidence_sources=["docs/notes/evidence.md"],
            )
        ],
        repo_files={"docs/spec.md": "spec", "docs/notes/evidence.md": "evidence"},
    )
    assert by_rule(issues, "canonical-source-missing") == []
    assert by_rule(issues, "evidence-source-missing") == []
    assert by_rule(issues, "reference-escapes-repo") == []


def test_absolute_canonical_path_is_error(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(
        make_project,
        tmp_path,
        [node_dict("A", canonical_sources=["/etc/passwd"])],
    )
    found = by_rule(issues, "reference-escapes-repo")
    assert len(found) == 1
    assert found[0].severity == Severity.ERROR
    assert found[0].node_id == "A"
    assert "/etc/passwd" in found[0].message
    # an escaping path is not additionally reported as missing
    assert by_rule(issues, "canonical-source-missing") == []


def test_dotdot_evidence_path_is_error(make_project, tmp_path, node_dict, by_rule):
    issues = build_issues(
        make_project,
        tmp_path,
        [node_dict("A", evidence_sources=["../outside-repo.md"])],
    )
    found = by_rule(issues, "reference-escapes-repo")
    assert len(found) == 1
    assert found[0].severity == Severity.ERROR
    assert "../outside-repo.md" in found[0].message
    assert by_rule(issues, "evidence-source-missing") == []
