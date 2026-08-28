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
from planning_control_plane.validator import validate_project


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
    # Spec §58.1 + INT-D11: exactly these 19 rule names identify the idea
    # layer (IDEA-D59 build gate, IDEA-D64 message prefix). Guards drift.
    assert IDEA_RULE_NAMES == frozenset(
        {
            "invalid-idea-file", "invalid-idea", "missing-idea-title",
            "invalid-idea-field", "invalid-idea-source", "invalid-idea-outcome",
            "invalid-idea-id", "duplicate-idea-id", "ignored-idea-file",
            "invalid-idea-status", "missing-idea-relates-target",
            "promoted-without-outcome", "missing-outcome-target",
            "outcome-without-promotion", "idea-source-escapes-repo",
            "idea-source-missing", "idea-id-collides-with-node",
            "idea-unknown-field", "idea-filename-mismatch",
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


# --------------------------------------------------------------- validation


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


def test_idea_dotdot_ref_is_escape_error(make_project, tmp_path, by_rule):
    """Spec §52.3 lexical half: a ../ ref escapes the repo even though it
    is not absolute — ERROR, and never additionally reported missing."""
    project, _root = _idea_project(
        make_project, tmp_path, "id: IDEA-1\ntitle: T\nbenchmark_sources:\n  - ref: \"../outside.md\"\n"
    )
    issues = validate_project(project)
    assert [i.severity for i in by_rule(issues, "idea-source-escapes-repo")] == [Severity.ERROR]
    assert by_rule(issues, "idea-source-missing") == []


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


# ------------------------------------------------------------------ pcp ideas
#
# NOTE: the global -p/--project-root must precede the subcommand (argparse
# hands everything after COMMAND to the subparser); same convention as
# tests/test_cli.py.


def test_cli_ideas_empty_state_exit_zero(make_project, tmp_path, cli):
    _project, root = make_project(tmp_path)
    code, out, err = cli("-p", str(root), "ideas")
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
    code, out, err = cli("-p", str(root), "ideas")
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
    code, out, err = cli("-p", str(root), "ideas")
    assert code == 0
    line = out.splitlines()[1]
    assert line == "IDEA-B  2026-01-01  对标驱动的视图改造  relates: P1  benchmark:Y methodology:N"


def test_cli_ideas_dedupes_repeated_relates_targets(make_project, tmp_path, cli):
    nodes = [{"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE"}]
    raw = {"ideas/A.yaml": "id: A\ntitle: T\nstatus: OPEN\nrelates_to: [P1, P1]\n"}
    _project, root = make_project(tmp_path, node_dicts=nodes, raw_files=raw)
    code, out, err = cli("-p", str(root), "ideas", "--for", "P1")
    assert code == 0
    assert "relates: P1 " in out
    assert out.rstrip().endswith("via: P1")
    assert "P1, P1" not in out


def test_cli_ideas_status_filter_repeatable(make_project, tmp_path, cli):
    raw = {
        "ideas/IDEA-A.yaml": "id: IDEA-A\ntitle: T\nstatus: OPEN\n",
        "ideas/IDEA-D.yaml": "id: IDEA-D\ntitle: T\nstatus: PARKED\n",
    }
    _project, root = make_project(tmp_path, raw_files=raw)
    code, out, err = cli("-p", str(root), "ideas", "--status", "PARKED")
    assert code == 0
    assert "IDEA-A" not in out and "IDEA-D" in out
    code, out, err = cli("-p", str(root), "ideas", "--status", "OPEN", "--status", "PARKED")
    assert "IDEA-A" in out and "IDEA-D" in out


def test_cli_ideas_status_filter_no_match_exit_zero(make_project, tmp_path, cli):
    _project, root = make_project(tmp_path, raw_files={"ideas/A.yaml": "id: IDEA-A\ntitle: T\nstatus: OPEN\n"})
    code, out, err = cli("-p", str(root), "ideas", "--status", "DISCARDED")
    assert (code, err) == (0, "")
    assert out.strip() == "no ideas match the requested status filter"


def test_cli_ideas_notes_hidden_invalid_status(make_project, tmp_path, cli):
    raw = {
        "ideas/A.yaml": "id: A\ntitle: T\nstatus: OPEN\n",
        "ideas/B.yaml": "id: B\ntitle: T\nstatus: PAUSED\n",  # invalid: unlistable
    }
    _project, root = make_project(tmp_path, raw_files=raw)
    code, out, err = cli("-p", str(root), "ideas")
    assert code == 0
    assert "IDEA-B" not in out
    assert "note: 1 idea record(s) not shown" in out


def test_cli_ideas_notes_broken_idea_file_in_empty_state(make_project, tmp_path, cli):
    _project, root = make_project(tmp_path, raw_files={"ideas/BAD.yaml": "id: [unclosed\n"})
    code, out, err = cli("-p", str(root), "ideas")
    assert (code, err) == (0, "")
    # Phase-2 Task 1: files exist but failed to load — "no ideas yet" would
    # tell the reader to create a file they already created.
    assert out.splitlines()[0] == "idea files exist but could not be loaded; run 'pcp validate'"
    assert "note: 1 idea record(s) not shown" in out


def test_cli_ideas_no_note_for_valid_status_filtering(make_project, tmp_path, cli):
    raw = {
        "ideas/A.yaml": "id: A\ntitle: T\nstatus: OPEN\n",
        "ideas/D.yaml": "id: D\ntitle: T\nstatus: DISCARDED\n",
    }
    _project, root = make_project(tmp_path, raw_files=raw)
    code, out, err = cli("-p", str(root), "ideas", "--status", "OPEN")
    assert code == 0
    assert "note:" not in out


def test_cli_ideas_no_note_when_records_listed_despite_issues(make_project, tmp_path, cli):
    """missing-idea-title still lists (title falls back to id) — no note."""
    raw = {"ideas/A.yaml": "id: A\n"}  # missing title: listed, but load issue exists
    _project, root = make_project(tmp_path, raw_files=raw)
    code, out, err = cli("-p", str(root), "ideas")
    assert code == 0
    assert " A " in out or out.splitlines()[1].startswith("A")
    assert "note:" not in out


def test_cli_ideas_duplicate_counts_as_hidden(make_project, tmp_path, cli):
    raw = {
        "ideas/A.yaml": "id: IDEA-1\ntitle: First\nstatus: OPEN\n",
        "ideas/B.yaml": "id: IDEA-1\ntitle: Second\nstatus: OPEN\n",
    }
    _project, root = make_project(tmp_path, raw_files=raw)
    code, out, err = cli("-p", str(root), "ideas")
    assert code == 0
    assert "First" in out and "Second" not in out
    assert "note: 1 idea record(s) not shown" in out


def test_cli_ideas_full_group_order_and_discarded(make_project, tmp_path, cli):
    raw = {
        "ideas/O.yaml": "id: O\ntitle: T\nstatus: OPEN\n",
        "ideas/K.yaml": "id: K\ntitle: T\nstatus: PARKED\n",
        "ideas/M.yaml": "id: M\ntitle: T\nstatus: PROMOTED\noutcome:\n  node: P1\n",
        "ideas/X.yaml": "id: X\ntitle: T\nstatus: DISCARDED\n",
    }
    nodes = [{"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE"}]
    _project, root = make_project(tmp_path, node_dicts=nodes, raw_files=raw)
    code, out, err = cli("-p", str(root), "ideas")
    assert code == 0
    headers = [l for l in out.splitlines() if l.startswith("==")]
    assert headers == ["== OPEN (1) ==", "== PARKED (1) ==", "== PROMOTED (1) ==", "== DISCARDED (1) =="]


def test_cli_ideas_multiline_title_collapsed(make_project, tmp_path, cli):
    raw = {"ideas/A.yaml": "id: A\ntitle: |\n  first line\n  second line\nstatus: OPEN\n"}
    _project, root = make_project(tmp_path, raw_files=raw)
    code, out, err = cli("-p", str(root), "ideas")
    assert code == 0
    lines = out.splitlines()
    # _oneline joins the block-scalar lines with single spaces: the whole
    # multi-line title lands on exactly one listing line.
    assert len(lines) == 2  # group header + one idea line
    assert "first line second line" in lines[1]


def _tree_nodes():
    return [
        {"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE"},
        {"id": "P2", "title": "P2", "type": "PHASE", "parent": "P1", "status": "IMPLEMENTING"},
        {"id": "P2-A", "title": "P2-A", "type": "STRATEGY", "parent": "P2", "status": "READY"},
    ]


def test_cli_ideas_for_ancestor_match_with_via(make_project, tmp_path, cli):
    raw = {"ideas/IDEA-1.yaml": "id: IDEA-1\ntitle: 挂在 P2 上\nstatus: OPEN\nrelates_to: [P2]\n"}
    _project, root = make_project(tmp_path, node_dicts=_tree_nodes(), raw_files=raw)
    code, out, err = cli("-p", str(root), "ideas", "--for", "P2-A")
    assert code == 0
    assert "IDEA-1" in out
    assert out.rstrip().endswith("via: P2")  # matched through the ancestor, attributed


def test_cli_ideas_for_self_match(make_project, tmp_path, cli):
    raw = {"ideas/IDEA-1.yaml": "id: IDEA-1\ntitle: T\nstatus: OPEN\nrelates_to: [P2-A]\n"}
    _project, root = make_project(tmp_path, node_dicts=_tree_nodes(), raw_files=raw)
    code, out, err = cli("-p", str(root), "ideas", "--for", "P2-A")
    assert code == 0
    assert out.rstrip().endswith("via: P2-A")


def test_cli_ideas_for_multi_target_via(make_project, tmp_path, cli):
    """An idea touching several scope members attributes every match."""
    raw = {"ideas/IDEA-1.yaml": "id: IDEA-1\ntitle: T\nstatus: OPEN\nrelates_to: [P2, P2-A]\n"}
    _project, root = make_project(tmp_path, node_dicts=_tree_nodes(), raw_files=raw)
    code, out, err = cli("-p", str(root), "ideas", "--for", "P2-A")
    assert code == 0
    assert out.rstrip().endswith("via: P2, P2-A")


def test_cli_ideas_for_excludes_unrelated(make_project, tmp_path, cli):
    raw = {"ideas/IDEA-1.yaml": "id: IDEA-1\ntitle: T\nstatus: OPEN\nrelates_to: [P2]\n"}
    _project, root = make_project(tmp_path, node_dicts=_tree_nodes(), raw_files=raw)
    code, out, err = cli("-p", str(root), "ideas", "--for", "P1")  # P2 is a child, not an ancestor
    assert (code, err) == (0, "")
    assert out.strip() == "no matching ideas for node 'P1'"


def test_cli_ideas_for_subtree_direction(make_project, tmp_path, cli):
    """R1/B4: the ancestor direction cannot see ideas hung on children;
    --subtree is what makes moment B executable."""
    raw = {"ideas/IDEA-1.yaml": "id: IDEA-1\ntitle: T\nstatus: OPEN\nrelates_to: [P2-A]\n"}
    _project, root = make_project(tmp_path, node_dicts=_tree_nodes(), raw_files=raw)
    code, out, _ = cli("-p", str(root), "ideas", "--for", "P2")
    assert code == 0
    assert "IDEA-1" not in out
    code, out, _ = cli("-p", str(root), "ideas", "--for", "P2", "--subtree")
    assert code == 0
    assert "IDEA-1" in out
    assert out.rstrip().endswith("via: P2-A")
    # An idea hanging outside the subtree: exit 0 and the direction-suffixed
    # no-match message (subtree mode never falls back to the plain wording).
    (root / ".planning/ideas/IDEA-1.yaml").write_text(
        "id: IDEA-1\ntitle: T\nstatus: OPEN\nrelates_to: [P1]\n", encoding="utf-8"
    )
    code, out, _ = cli("-p", str(root), "ideas", "--for", "P2", "--subtree")
    assert (code, out.strip()) == (0, "no matching ideas for node 'P2' (subtree)")


def test_cli_ideas_for_defaults_to_open_and_parked(make_project, tmp_path, cli):
    raw = {
        "ideas/A.yaml": "id: A\ntitle: T\nstatus: OPEN\nrelates_to: [P2]\n",
        "ideas/B.yaml": "id: B\ntitle: T\nstatus: PARKED\nrelates_to: [P2]\n",
        "ideas/C.yaml": "id: C\ntitle: T\nstatus: PROMOTED\nrelates_to: [P2]\n",
        "ideas/D.yaml": "id: D\ntitle: T\nstatus: DISCARDED\nrelates_to: [P2]\n",
    }
    _project, root = make_project(tmp_path, node_dicts=_tree_nodes(), raw_files=raw)
    code, out, err = cli("-p", str(root), "ideas", "--for", "P2")
    assert code == 0
    ids = [line.split()[0] for line in out.splitlines() if not line.startswith("==")]
    assert ids == ["A", "B"]  # IDEA-D62: --for defaults to OPEN + PARKED

    code, out, err = cli("-p", str(root), "ideas", "--for", "P2", "--status", "DISCARDED")
    assert code == 0
    ids = [line.split()[0] for line in out.splitlines() if not line.startswith("==")]
    assert ids == ["D"]  # explicit --status overrides the default filter


def test_cli_ideas_subtree_requires_for(make_project, tmp_path, cli):
    _project, root = make_project(tmp_path)
    code, out, err = cli("-p", str(root), "ideas", "--subtree")
    assert code == 2
    assert "--subtree requires --for" in err


def test_cli_ideas_for_unknown_node(make_project, tmp_path, cli):
    _project, root = make_project(tmp_path)
    code, out, err = cli("-p", str(root), "ideas", "--for", "NOPE")
    assert code == 1
    assert "unknown node 'NOPE'" in err


def test_cli_context_idea_id_hint(make_project, tmp_path, cli):
    nodes = [{"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE"}]
    raw = {"ideas/IDEA-0007.yaml": "id: IDEA-0007\ntitle: T\nstatus: OPEN\n"}
    _project, root = make_project(tmp_path, node_dicts=nodes, raw_files=raw)
    code, out, err = cli("-p", str(root), "context", "IDEA-0007")
    assert code == 1
    assert "unknown node 'IDEA-0007'" in err
    assert "pcp ideas" in err


def test_cli_focus_idea_id_hint(make_project, tmp_path, cli):
    nodes = [{"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE"}]
    raw = {"ideas/IDEA-0007.yaml": "id: IDEA-0007\ntitle: T\nstatus: OPEN\n"}
    _project, root = make_project(tmp_path, node_dicts=nodes, raw_files=raw)
    code, out, err = cli("-p", str(root), "focus", "IDEA-0007")
    assert code == 1
    assert "pcp ideas" in err


def test_cli_unknown_node_error_has_no_idea_hint_for_plain_ids(make_project, tmp_path, cli):
    nodes = [{"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE"}]
    raw = {"ideas/IDEA-0007.yaml": "id: IDEA-0007\ntitle: T\nstatus: OPEN\n"}
    _project, root = make_project(tmp_path, node_dicts=nodes, raw_files=raw)
    code, out, err = cli("-p", str(root), "context", "GHOST")
    assert code == 1
    assert err.strip() == "error: unknown node 'GHOST'"


def test_cli_build_succeeds_with_idea_layer_errors(make_project, tmp_path, cli):
    """IDEA-D59: an idea-layer ERROR must not block the plan projection."""
    nodes = [{"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE"}]
    raw = {"ideas/IDEA-BAD.yaml": "id: IDEA-BAD\ntitle: T\nstatus: PROMOTED\n"}  # promoted-without-outcome ERROR
    _project, root = make_project(tmp_path, node_dicts=nodes, raw_files=raw)
    code, out, err = cli("-p", str(root), "build")
    assert code == 0
    assert "promoted-without-outcome" in out  # printed, informational
    assert "Built" in out                     # build proceeded


def test_cli_build_still_blocked_by_node_layer_errors(make_project, tmp_path, cli):
    nodes = [{"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE", "depends_on": ["MISSING"]}]
    raw = {"ideas/IDEA-BAD.yaml": "id: IDEA-BAD\ntitle: T\nstatus: PROMOTED\n"}
    _project, root = make_project(tmp_path, node_dicts=nodes, raw_files=raw)
    code, out, err = cli("-p", str(root), "build")
    assert code == 1
    assert "fix validation errors before build" in out


def test_cli_plan_commands_survive_broken_idea_file(make_project, tmp_path, cli):
    """Spec §62.1 phase-1 acceptance: with a broken idea YAML present,
    status / context / build must all still succeed (invariant §59.6)."""
    config = {"project": {"id": "t", "name": "T"}, "planning": {"current_focus": "P1"}}
    nodes = [{"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE"}]
    raw = {"ideas/IDEA-BROKEN.yaml": "id: [unclosed\n"}
    _project, root = make_project(tmp_path, config_dict=config, node_dicts=nodes, raw_files=raw)

    code, out, err = cli("-p", str(root), "status")
    assert code == 0

    code, out, err = cli("-p", str(root), "context", "P1")
    assert code == 0
    assert "PCP CONTEXT CAPSULE" in out  # capsule unaffected by idea garbage

    code, out, err = cli("-p", str(root), "build")
    assert code == 0


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


def test_cli_ideas_hidden_note_counts_a_bad_status_idea_that_hits_the_scope(make_project, tmp_path, cli):
    """The scoped count is zero only when nothing hidden hits the scope; a
    bad-status idea that DOES relate to the node was suppressible by this
    listing and must still be counted."""
    raw = {
        "ideas/IDEA-OK.yaml": "id: IDEA-OK\ntitle: ok\nstatus: OPEN\nrelates_to: [P2]\n",
        "ideas/IDEA-BADSCOPED.yaml": "id: IDEA-BADSCOPED\ntitle: bad\nstatus: WISHLIST\nrelates_to: [P2]\n",
    }
    _project, root = make_project(tmp_path, node_dicts=_three_nodes(), raw_files=raw)

    code, out, _err = cli("-p", str(root), "ideas", "--for", "P2")
    assert code == 0
    assert "IDEA-OK" in out
    assert "1 idea record(s) not shown" in out
