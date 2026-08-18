"""Graph operations: ancestor order, ready queue, blocked-by, parent path,
related nodes (both directions) and cycle detection (spec §7, §24).
"""

from __future__ import annotations

from planning_control_plane.graph import PlanningGraph
from planning_control_plane.loader import load_project
from planning_control_plane.validator import validate_project


def graph_for(make_project, tmp_path, node_dicts):
    project, _root = make_project(
        tmp_path,
        config_dict={
            "project": {"id": "t", "name": "T"},
            "planning": {"current_focus": "A"},
        },
        node_dicts=node_dicts,
    )
    return PlanningGraph(project), project


# ----------------------------------------------------------- demo project graph


def test_demo_ancestors_nearest_parent_first(demo_root):
    graph = PlanningGraph(load_project(demo_root))
    assert graph.ancestors("P2-A2") == ["P2-A", "P2", "P1"]  # nearest parent first
    assert graph.ancestors("P2") == ["P1"]
    assert graph.ancestors("P1") == []


def test_demo_parent_path_root_first(demo_root):
    graph = PlanningGraph(load_project(demo_root))
    assert graph.parent_path("P2-A2") == ["P1", "P2", "P2-A", "P2-A2"]
    assert graph.parent_path("P1") == ["P1"]


def test_demo_children_and_descendants(demo_root):
    graph = PlanningGraph(load_project(demo_root))
    assert graph.children("P2-A") == ["P2-A1", "P2-A2", "P2-A3", "P2-A4"]
    assert graph.children("P2") == ["P2-A"]
    assert graph.children("P2-A4") == []
    assert graph.descendants("P2") == ["P2-A", "P2-A1", "P2-A2", "P2-A3", "P2-A4"]
    assert graph.descendants("P2-A4") == []
    assert graph.roots == ["P1"]


def test_demo_ready_queue(demo_root):
    project = load_project(demo_root)
    graph = PlanningGraph(project)
    # every dependency of P2-A4 is DONE and it has not started yet
    assert graph.ready_queue() == ["P2-A4"]
    assert graph.blocked_by(project.nodes["P2-A4"]) == []


def test_demo_related_nodes_bidirectional(demo_root):
    graph = PlanningGraph(load_project(demo_root))
    # P2-A2 declares related_to P2-A1 (forward) and P2-A4 points back at it
    assert graph.related_nodes("P2-A2") == ["P2-A1", "P2-A4"]
    # P2-A1 declares nothing itself; the link is found in reverse
    assert graph.related_nodes("P2-A1") == ["P2-A2"]


def test_demo_has_no_cycles(demo_root):
    graph = PlanningGraph(load_project(demo_root))
    assert graph.find_parent_cycles() == []
    assert graph.find_dependency_cycles() == []
    assert validate_project(load_project(demo_root)) == []


# ------------------------------------------------------------- synthetic graph


def test_ready_queue_classifies_dependency_states(make_project, tmp_path, node_dict):
    graph, _project = graph_for(
        make_project,
        tmp_path,
        [
            node_dict("READY", depends_on=["DONE-DEP"]),  # deps satisfied, not started
            node_dict("NO-DEP"),  # no dependencies at all
            node_dict("WAITING", depends_on=["OPEN-DEP"]),  # dependency not DONE
            node_dict("ORPHAN", depends_on=["GHOST"]),  # missing target disqualifies
            node_dict("ALREADY-DONE", status="DONE", depends_on=["DONE-DEP"]),  # not NOT_STARTED
            node_dict("DEFERRING", depends_on=["DEF-DEP"]),  # deferred dependency
            node_dict("DONE-DEP", status="DONE"),
            node_dict("OPEN-DEP", status="IMPLEMENTING"),
            node_dict("DEF-DEP", status="DEFERRED"),
        ],
    )
    assert graph.ready_queue() == ["NO-DEP", "READY"]


def test_blocked_by_lists_not_done_dependencies(make_project, tmp_path, node_dict):
    graph, project = graph_for(
        make_project,
        tmp_path,
        [
            node_dict(
                "A",
                depends_on=["DONE-DEP", "OPEN-DEP", "GHOST", "DEF-DEP"],
            ),
            node_dict("DONE-DEP", status="DONE"),
            node_dict("OPEN-DEP", status="NOT_STARTED"),
            node_dict("DEF-DEP", status="DEFERRED"),
        ],
    )
    # DONE dependencies drop out; everything else blocks, sorted
    assert graph.blocked_by(project.nodes["A"]) == ["DEF-DEP", "GHOST", "OPEN-DEP"]


def test_related_nodes_forward_reverse_and_filtered(make_project, tmp_path, node_dict):
    graph, _project = graph_for(
        make_project,
        tmp_path,
        [
            node_dict("A", related_to=["B", "GHOST"]),
            node_dict("B"),
            node_dict("C", related_to=["A"]),
        ],
    )
    # own forward links plus reverse links; unknown targets are dropped
    assert graph.related_nodes("A") == ["B", "C"]
    assert graph.related_nodes("B") == ["A"]


def test_dependency_cycle_detection(make_project, tmp_path, node_dict):
    graph, _project = graph_for(
        make_project,
        tmp_path,
        [
            node_dict("A", depends_on=["B"]),
            node_dict("B", depends_on=["C"]),
            node_dict("C", depends_on=["A"]),
            node_dict("D", depends_on=["A"]),
        ],
    )
    cycles = graph.find_dependency_cycles()
    assert len(cycles) == 1
    assert cycles[0] == ["A", "B", "C", "A"]


def test_parent_cycle_detection_and_guarded_ancestors(make_project, tmp_path, node_dict):
    graph, _project = graph_for(
        make_project,
        tmp_path,
        [node_dict("A", parent="B"), node_dict("B", parent="A")],
    )
    cycles = graph.find_parent_cycles()
    assert len(cycles) == 1
    assert cycles[0] == ["A", "B", "A"]
    # the ancestor walk is guarded: it terminates instead of looping forever
    assert graph.ancestors("A") == ["B"]
    assert graph.ancestors("B") == ["A"]


def test_topological_order_puts_parents_before_children(make_project, tmp_path, node_dict):
    graph, _project = graph_for(
        make_project,
        tmp_path,
        [
            node_dict("LEAF", parent="MID"),
            node_dict("MID", parent="TOP"),
            node_dict("TOP"),
            node_dict("OTHER"),
        ],
    )
    order = graph.topological_order()
    assert order.index("TOP") < order.index("MID") < order.index("LEAF")
    assert sorted(order) == ["LEAF", "MID", "OTHER", "TOP"]
    assert graph.subtree_ids("TOP") == ["TOP", "MID", "LEAF"]
