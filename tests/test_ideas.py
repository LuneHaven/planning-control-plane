"""Idea layer tests (spec: specs/ideas-spec-draft.zh-CN.md, phase 1)."""

from planning_control_plane.loader import load_project, parse_idea
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


def test_parse_idea_non_string_ref_and_note_warn_and_are_dropped():
    issues = []
    idea = parse_idea(
        {
            "id": "IDEA-1",
            "title": "T",
            "benchmark_sources": [{"ref": "docs/a.md", "note": ["x"]}],
            "methodology_sources": [{"ref": ["docs"], "note": "kept"}],
        },
        None,
        issues,
    )
    assert idea.benchmark_sources == [IdeaSource(ref="docs/a.md", note=None)]
    assert idea.methodology_sources == [IdeaSource(ref=None, note="kept")]
    assert [(i.rule, i.severity) for i in issues] == [
        ("invalid-idea-source", Severity.WARNING),
        ("invalid-idea-source", Severity.WARNING),
    ]


def test_parse_idea_non_string_outcome_note_warns():
    issues = []
    idea = parse_idea({"id": "A", "title": "T", "outcome": {"node": "P2", "note": 7}}, None, issues)
    assert idea.outcome == IdeaOutcome(node="P2", note="")
    assert [(i.rule, i.severity) for i in issues] == [("invalid-idea-outcome", Severity.WARNING)]


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


def test_undecodable_idea_file_degrades_to_issue_not_a_crash(make_project, tmp_path):
    """IDEA-D58: an unreadable (non-UTF-8) idea file must not brick the
    load — it becomes invalid-idea-file and the other ideas still load."""
    _project, root = make_project(tmp_path, raw_files={"ideas/IDEA-0007.yaml": GOOD_IDEA})
    (root / ".planning/ideas/GBK.yaml").write_bytes("id: IDEA-GBK\ntitle: 中文\n".encode("gbk"))
    project = load_project(root)
    assert "IDEA-0007" in project.ideas
    assert [i.rule for i in project.load_issues] == ["invalid-idea-file"]
    assert project.load_issues[0].message.startswith("idea '.planning/ideas/GBK.yaml': ")


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


def test_ignored_idea_files_warn_nested_and_wrong_suffix(make_project, tmp_path):
    project, _root = make_project(
        tmp_path,
        raw_files={
            "ideas/IDEA-0007.yaml": GOOD_IDEA,
            "ideas/archive/IDEA-OLD.yaml": "id: IDEA-OLD\ntitle: Old\n",
            "ideas/extra.yml": "id: X\n",
        },
    )
    assert [i.rule for i in project.load_issues] == ["ignored-idea-file", "ignored-idea-file"]
    assert "archive/IDEA-OLD.yaml" in project.load_issues[0].message
    assert "extra.yml" in project.load_issues[1].message
