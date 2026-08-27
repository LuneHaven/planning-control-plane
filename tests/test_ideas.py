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
