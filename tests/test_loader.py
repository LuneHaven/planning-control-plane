"""Loader: valid project loading, fatal errors, tolerant schema parsing and
duplicate node id detection (spec §5–§8, §16).
"""

from __future__ import annotations

import pytest

from planning_control_plane.loader import LoadError, load_project
from planning_control_plane.model import Severity


# --------------------------------------------------------------- happy path


def test_load_demo_project(demo_root):
    project = load_project(demo_root)

    assert project.root == demo_root.resolve()
    assert project.sorted_node_ids() == [
        "P1",
        "P2",
        "P2-A",
        "P2-A1",
        "P2-A2",
        "P2-A3",
        "P2-A4",
    ]
    assert project.load_issues == []

    config = project.config
    assert config.id == "demo-project"
    assert config.name == "Demo Project"
    assert config.current_focus == "P2-A4"
    assert config.output_directory == ".planning/dist"
    assert project.output_dir() == demo_root.resolve() / ".planning" / "dist"
    assert config.authority.canonical_roots == ["docs/rollout"]
    assert config.authority.current_state_roots == ["docs/notes"]
    assert config.authority.planning_roots == [".planning"]


def test_load_demo_project_node_details(demo_root):
    project = load_project(demo_root)

    focus = project.nodes["P2-A4"]
    assert focus.type == "DISCUSSION"
    assert focus.parent == "P2-A"
    assert focus.status == "NOT_STARTED"
    assert [d.id for d in focus.blocking_decisions] == ["BD-401"]
    assert [d.id for d in focus.open_decisions] == ["OD-401"]
    assert focus.depends_on == ["P2-A3"]
    assert focus.canonical_sources == ["docs/rollout/readiness-criteria.md", "docs/rollout/sequencing.md"]

    strategy = project.nodes["P2-A"]
    assert [d.id for d in strategy.frozen_decisions] == ["FD-201"]
    assert strategy.frozen_decisions[0].source == "docs/rollout/readiness-criteria.md"

    decision = project.nodes["P2-A3"]
    assert decision.status == "DONE"
    assert decision.blocks == ["P2-A4"]
    assert decision.evidence_sources == ["docs/notes/2026-08-15-sequencing-review.md"]

    # the three tracks are stored independently (spec §11): discussion and
    # writeback are DONE while implementation never applies
    assert strategy.discussion_status == "IN_PROGRESS"
    assert strategy.writeback_status == "DONE"
    assert strategy.implementation_status == "NOT_APPLICABLE"

    assert project.nodes["P1"].status == "DONE"
    assert project.nodes["P1"].parent is None


def test_load_searches_upward_from_nested_directory(demo_root):
    project = load_project(demo_root / "docs" / "rollout")
    assert project.root == demo_root.resolve()
    assert "P1" in project.nodes


def test_load_missing_planning_dir_raises(tmp_path):
    with pytest.raises(LoadError, match="pcp init"):
        load_project(tmp_path)


def test_load_missing_project_yaml_raises(tmp_path):
    (tmp_path / ".planning").mkdir()
    with pytest.raises(LoadError, match="project.yaml"):
        load_project(tmp_path)


# ------------------------------------------------------------ invalid YAML


@pytest.mark.parametrize(
    "relative_path, content",
    [
        ("project.yaml", "project: [unclosed\n"),
        ("roadmap.yaml", "nodes: [unclosed\n"),
        ("nodes/Broken.yaml", "id: Broken\ntitle: [unclosed\n"),
    ],
)
def test_invalid_yaml_raises_load_error(tmp_path, make_project, relative_path, content):
    with pytest.raises(LoadError, match="invalid YAML"):
        make_project(tmp_path, raw_files={relative_path: content})


# ------------------------------------------------------- tolerant schema errors


def test_node_missing_id_is_dropped(make_project, tmp_path):
    project, _root = make_project(
        tmp_path,
        roadmap_nodes=[{"title": "No id provided"}],
    )
    assert project.nodes == {}
    invalid = [i for i in project.load_issues if i.rule == "invalid-node"]
    assert len(invalid) == 1
    assert invalid[0].severity == Severity.ERROR
    assert "id" in invalid[0].message


def test_node_missing_title_falls_back_to_id(make_project, tmp_path, node_dict):
    project, _root = make_project(tmp_path, node_dicts=[{"id": "A"}])
    node = project.nodes["A"]
    assert node.title == "A"  # usable fallback, but the problem is recorded
    missing = [i for i in project.load_issues if i.rule == "missing-title"]
    assert len(missing) == 1
    assert missing[0].severity == Severity.ERROR
    assert missing[0].node_id == "A"


def test_non_mapping_node_entry_records_error(make_project, tmp_path):
    project, _root = make_project(tmp_path, roadmap_nodes=["just a string"])
    assert project.nodes == {}
    assert any(i.rule == "invalid-node" and i.severity == Severity.ERROR for i in project.load_issues)


def test_wrong_list_type_records_error(make_project, tmp_path, node_dict):
    project, _root = make_project(
        tmp_path,
        node_dicts=[node_dict("A", scope="a plain string", depends_on=42)],
    )
    node = project.nodes["A"]
    assert node.scope == []
    assert node.depends_on == []
    invalid = [i for i in project.load_issues if i.rule == "invalid-field"]
    assert {i.message.split("'")[1] for i in invalid} == {"scope", "depends_on"}
    assert all(i.severity == Severity.ERROR and i.node_id == "A" for i in invalid)


def test_bad_decision_entries_are_reported_and_skipped(make_project, tmp_path, node_dict):
    project, _root = make_project(
        tmp_path,
        node_dicts=[
            node_dict(
                "A",
                frozen_decisions=[
                    "a plain string",
                    {"id": "FD-OK", "summary": "valid entry"},
                    {"summary": "missing the id"},
                    {"id": "FD-NO-SUMMARY"},
                ],
                blocking_decisions={"id": "not-a-list"},
            )
        ],
    )
    node = project.nodes["A"]
    # only the valid entry survives, everything else became an issue
    assert [d.id for d in node.frozen_decisions] == ["FD-OK"]
    assert node.blocking_decisions == []
    bad = [i for i in project.load_issues if i.rule == "invalid-decision"]
    assert len(bad) == 3  # non-mapping, missing id, missing summary
    assert all(i.severity == Severity.ERROR and i.node_id == "A" for i in bad)
    non_list = [i for i in project.load_issues if i.rule == "invalid-field" and "'blocking_decisions'" in i.message]
    assert len(non_list) == 1 and non_list[0].severity == Severity.ERROR


def test_invalid_node_id_charset_is_kept_and_reported(make_project, tmp_path):
    project, _root = make_project(tmp_path, node_dicts=[("Weird.yaml", {"id": "has space!", "title": "Weird"})])
    # the node stays in the graph so the validator can report on it
    assert "has space!" in project.nodes
    invalid = [i for i in project.load_issues if i.rule == "invalid-node-id"]
    assert len(invalid) == 1
    assert invalid[0].severity == Severity.ERROR
    assert invalid[0].node_id == "has space!"


def test_unknown_fields_are_recorded(make_project, tmp_path, node_dict):
    project, _root = make_project(tmp_path, node_dicts=[node_dict("A", priority="high")])
    assert project.nodes["A"].unknown_fields == ["priority"]


# ---------------------------------------------------------- duplicate node ids


def test_duplicate_id_between_roadmap_and_node_file(make_project, tmp_path, node_dict):
    project, _root = make_project(
        tmp_path,
        roadmap_nodes=[node_dict("A", title="Roadmap A")],
        node_dicts=[node_dict("A", title="File A")],
    )
    duplicates = [i for i in project.load_issues if i.rule == "duplicate-node-id"]
    assert len(duplicates) == 1
    assert duplicates[0].severity == Severity.ERROR
    assert duplicates[0].node_id == "A"
    # the first definition (roadmap.yaml is merged before nodes/) wins
    assert project.nodes["A"].title == "Roadmap A"
    assert len(project.nodes) == 1


def test_duplicate_id_across_two_node_files(make_project, tmp_path, node_dict):
    project, _root = make_project(
        tmp_path,
        node_dicts=[
            ("First.yaml", node_dict("A", title="First")),
            ("Second.yaml", node_dict("A", title="Second")),
        ],
    )
    duplicates = [i for i in project.load_issues if i.rule == "duplicate-node-id"]
    assert len(duplicates) == 1
    assert duplicates[0].severity == Severity.ERROR
    # files load in sorted filename order, so the first file wins
    assert project.nodes["A"].title == "First"


def test_roadmap_and_node_files_merge(make_project, tmp_path, node_dict):
    project, _root = make_project(
        tmp_path,
        roadmap_nodes=[node_dict("R1")],
        node_dicts=[node_dict("F1"), node_dict("F2")],
    )
    assert project.sorted_node_ids() == ["F1", "F2", "R1"]
    assert project.load_issues == []


# ------------------------------------------------------------- track aliases


def test_track_status_aliases_normalize_to_not_applicable(make_project, tmp_path, node_dict):
    project, _root = make_project(
        tmp_path,
        node_dicts=[node_dict("A", writeback_status="N/A", implementation_status="NA")],
    )
    node = project.nodes["A"]
    assert node.writeback_status == "NOT_APPLICABLE"
    assert node.implementation_status == "NOT_APPLICABLE"
    assert node.discussion_status == "NOT_STARTED"  # omitted in YAML -> default
