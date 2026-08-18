"""Context capsule: ancestor decision/scope/canonical inheritance (spec §14),
compact vs full rendering (spec §20/§21) and track display (spec §11).
"""

from __future__ import annotations

import pytest

from planning_control_plane.context import (
    InheritedGroup,
    build_capsule,
    render_capsule,
    track_display,
)
from planning_control_plane.loader import load_project

#: Every section heading of the compact capsule (spec §20).
COMPACT_HEADERS = [
    "=== PCP CONTEXT CAPSULE ===",
    "Project:",
    "Node:",
    "Parent Path:",
    "Mode: compact",
    "Objective:",
    "Inherited Frozen Decisions:",
    "Frozen Decisions (this node):",
    "In Scope:",
    "Out of Scope:",
    "Open Decisions:",
    "Blocking Decisions:",
    "Canonical Sources:",
    "Evidence Sources:",
    "Next Action:",
    "=== END CAPSULE ===",
]

#: Sections that only the full capsule discloses (spec §21).
FULL_ONLY_HEADERS = [
    "Ancestor Summaries:",
    "Related Nodes:",
    "Dependencies:",
    "Blocks / Waited By:",
    "Deferred Decisions:",
]


@pytest.fixture
def three_level_project(make_project, tmp_path):
    """TOP -> MID -> LEAF tree exercising every inheritance rule.

    * FD-1 exists on TOP and LEAF (own decision shadows the inherited one);
    * FD-2 exists on TOP and MID (the nearer ancestor wins);
    * "shared scope item" appears on TOP and MID (nearest attribution wins);
    * docs/shared.md is canonical on TOP and MID, docs/mid.md on MID and LEAF.
    """
    nodes = [
        {
            "id": "TOP",
            "title": "Top",
            "type": "PROGRAM",
            "status": "DONE",
            "scope": ["shared scope item", "top-only scope"],
            "frozen_decisions": [
                {"id": "FD-1", "summary": "top decision one"},
                {"id": "FD-2", "summary": "top decision two"},
            ],
            "canonical_sources": ["docs/top.md", "docs/shared.md"],
        },
        {
            "id": "MID",
            "title": "Mid",
            "parent": "TOP",
            "status": "IMPLEMENTING",
            "scope": ["shared scope item", "mid-only scope"],
            "frozen_decisions": [
                {"id": "FD-2", "summary": "mid overrides fd2"},
                {"id": "FD-3", "summary": "mid decision three"},
            ],
            "canonical_sources": ["docs/shared.md", "docs/mid.md"],
        },
        {
            "id": "LEAF",
            "title": "Leaf",
            "parent": "MID",
            "type": "IMPLEMENTATION",
            "status": "NOT_STARTED",
            "scope": ["leaf scope"],
            "frozen_decisions": [{"id": "FD-1", "summary": "leaf own fd1 shadows inherited"}],
            "open_decisions": [{"id": "OD-1", "summary": "leaf question"}],
            "blocking_decisions": [{"id": "BD-1", "summary": "leaf blocker"}],
            "deferred_decisions": [{"id": "ZZ-DEFERRED-1", "summary": "park it"}],
            "depends_on": ["TOP"],
            "canonical_sources": ["docs/mid.md"],
            "evidence_sources": ["docs/evidence.md"],
            "discussion_status": "DONE",
            "writeback_status": "N/A",
            "implementation_status": "IN_PROGRESS",
            "next_action": "Start implementing the leaf.",
        },
    ]
    project, _root = make_project(
        tmp_path,
        config_dict={
            "project": {"id": "inh", "name": "Inheritance Project"},
            "planning": {"current_focus": "LEAF"},
        },
        node_dicts=nodes,
        repo_files={
            "docs/top.md": "top",
            "docs/shared.md": "shared",
            "docs/mid.md": "mid",
            "docs/evidence.md": "evidence",
        },
    )
    return project


# ------------------------------------------------- inherited frozen decisions


def test_inherited_frozen_grouped_nearest_first(three_level_project):
    capsule = build_capsule(three_level_project, "LEAF")

    # MID (nearest) contributes FD-2 — its summary wins over TOP's — and FD-3.
    # FD-1 is shadowed by LEAF's own frozen decision, so TOP contributes
    # nothing and gets no group at all.
    assert [(g.ancestor_id, [d.id for d in g.decisions]) for g in capsule.inherited_frozen] == [
        ("MID", ["FD-2", "FD-3"])
    ]
    mid_group = capsule.inherited_frozen[0]
    assert isinstance(mid_group, InheritedGroup)
    assert mid_group.ancestor_title == "Mid"
    fd2 = next(d for d in mid_group.decisions if d.id == "FD-2")
    assert fd2.summary == "mid overrides fd2"


def test_own_frozen_decisions_shadow_inherited(three_level_project):
    capsule = build_capsule(three_level_project, "LEAF")
    # FD-1 belongs to the node itself, not to the inherited groups
    assert [d.id for d in capsule.current_frozen] == ["FD-1"]
    assert [d.id for d in capsule.inherited_frozen[0].decisions] == ["FD-2", "FD-3"]
    inherited_ids = {d.id for group in capsule.inherited_frozen for d in group.decisions}
    assert "FD-1" not in inherited_ids


def test_parent_path_root_first_with_titles(three_level_project):
    capsule = build_capsule(three_level_project, "LEAF")
    assert capsule.parent_path == [("TOP", "Top"), ("MID", "Mid")]
    assert capsule.project_id == "inh"
    assert capsule.project_name == "Inheritance Project"
    assert capsule.node_id == "LEAF"
    assert capsule.node_title == "Leaf"


# ------------------------------------------------------ scope and canonicals


def test_inherited_scope_deduplicates_nearest_first(three_level_project):
    capsule = build_capsule(three_level_project, "LEAF")
    # "shared scope item" is attributed to MID only (nearest declaration),
    # each ancestor contributes its unique entries nearest ancestor first
    assert capsule.inherited_scope == [
        ("MID", "shared scope item"),
        ("MID", "mid-only scope"),
        ("TOP", "top-only scope"),
    ]
    # the node's own scope stays separate
    assert capsule.scope == ["leaf scope"]


def test_inherited_canonical_deduplicates_and_own_shadows(three_level_project):
    capsule = build_capsule(three_level_project, "LEAF")
    # docs/shared.md is attributed to MID (nearest); docs/mid.md is linked by
    # LEAF itself and therefore never inherited
    assert capsule.inherited_canonical == [("MID", "docs/shared.md"), ("TOP", "docs/top.md")]
    assert capsule.canonical_sources == ["docs/mid.md"]
    assert capsule.evidence_sources == ["docs/evidence.md"]


# --------------------------------------------------------- rendering (§20/§21)


def test_compact_render_contains_all_spec20_sections(three_level_project):
    text = render_capsule(build_capsule(three_level_project, "LEAF"))
    for header in COMPACT_HEADERS:
        assert header in text, header
    # the three track statuses render on one line, N/A included
    assert "Discussion: DONE | Writeback: N/A | Implementation: IN_PROGRESS" in text
    # raw enum value never leaks into the capsule
    assert "NOT_APPLICABLE" not in text


def test_compact_render_excludes_full_only_sections(three_level_project):
    text = render_capsule(build_capsule(three_level_project, "LEAF"))
    for header in FULL_ONLY_HEADERS:
        assert header not in text, header
    # deferred decisions are compact-mode invisible, in data and in text
    compact = build_capsule(three_level_project, "LEAF", full=False)
    assert compact.deferred_decisions == []
    assert "ZZ-DEFERRED-1" not in text


def test_full_render_adds_disclosure_sections(three_level_project):
    capsule = build_capsule(three_level_project, "LEAF", full=True)
    text = render_capsule(capsule)

    assert "Mode: full" in text
    for header in FULL_ONLY_HEADERS:
        assert header in text, header
    # full keeps every compact section too
    for header in COMPACT_HEADERS:
        if header != "Mode: compact":
            assert header in text, header

    # ancestor summaries list every ancestor root first with type/status
    assert [(s.id, s.type, s.status) for s in capsule.ancestor_summaries] == [
        ("TOP", "PROGRAM", "DONE"),
        ("MID", "DISCUSSION", "IMPLEMENTING"),
    ]

    # deferred decisions become visible in full mode
    assert [d.id for d in capsule.deferred_decisions] == ["ZZ-DEFERRED-1"]
    assert "ZZ-DEFERRED-1" in text

    # dependencies detail carries the satisfaction state (TOP is DONE)
    assert [detail.id for detail in capsule.dependency_details] == ["TOP"]
    assert capsule.dependency_details[0].state == "done"
    assert "Dependencies:" in text


def test_full_render_related_and_blocks_me(three_level_project, make_project, tmp_path, node_dict):
    project, _root = make_project(
        tmp_path,
        config_dict={"project": {"id": "r", "name": "R"}, "planning": {"current_focus": "A"}},
        node_dicts=[
            node_dict("A", related_to=["B"], depends_on=[]),
            node_dict("B", related_to=["A"], depends_on=["A"]),
            node_dict("C", blocks=["A"]),
            node_dict("D", related_to=["A"]),
        ],
    )
    capsule = build_capsule(project, "A", full=True)

    # related nodes include both directions (A<->B) plus one-way links to A
    assert [ref.id for ref in capsule.related_nodes] == ["B", "D"]
    # nodes waiting on A: depends_on A (B) and blocks A (C)
    assert [ref.id for ref in capsule.blocks_me] == ["B", "C"]


def test_compact_capsule_still_lists_open_and_blocking(three_level_project):
    text = render_capsule(build_capsule(three_level_project, "LEAF"))
    assert "OD-1: leaf question" in text
    assert "BD-1: leaf blocker" in text
    assert "Start implementing the leaf." in text


# ----------------------------------------------------------- failure contract


def test_unknown_node_raises_valueerror(three_level_project):
    with pytest.raises(ValueError, match="unknown node id 'GHOST'"):
        build_capsule(three_level_project, "GHOST")


def test_track_display_normalizes_not_applicable():
    assert track_display("NOT_APPLICABLE") == "N/A"
    assert track_display("NOT_STARTED") == "NOT_STARTED"
    assert track_display("DONE") == "DONE"


def test_capsule_content_matches_cli_context(demo_root, capsys):
    """The programmatic capsule equals what ``pcp context`` prints (spec §27)."""
    from planning_control_plane import cli

    assert cli.main(["-p", str(demo_root), "context", "P2-A4"]) == 0
    printed = capsys.readouterr().out

    project = load_project(demo_root)
    expected = render_capsule(build_capsule(project, "P2-A4"))
    assert printed == expected

    # the demo focus node carries its blocking decision into the capsule
    assert "BD-401" in printed
    assert "P2-A3" in printed  # dependency target
