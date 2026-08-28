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
