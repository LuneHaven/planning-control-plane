"""Validation rules over a loaded :class:`Project` (spec §9, §10, §13, §16, §17).

:func:`validate_project` merges the schema-level issues the loader already
collected (``project.load_issues``) with the rule checks implemented here,
then returns everything in a deterministic order: severity (ERROR first),
then node id (``None`` sorts as ``""``), then rule, then message.

Rule groups:

* structure — enum membership, parent and cross-edge target existence,
  dependency/parent cycles, current focus, duplicate decision ids, unknown
  fields (spec §16);
* planning consistency — DONE/BLOCKED/writeback/focus/deferred-dependency
  combinations (spec §13, §16);
* references — repository-relative path checks for canonical and evidence
  sources, checked and reported as two distinct kinds (spec §17).

The validator never mutates the project and never raises on bad data:
invalid enum values were deliberately kept by the loader so that every
problem can be reported in a single pass.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePath

from planning_control_plane.graph import PlanningGraph
from planning_control_plane.model import (
    NodeStatus,
    NodeType,
    Project,
    Severity,
    TrackStatus,
    ValidationIssue,
)

#: Controlled enum values as plain strings, for membership checks on the
#: raw string fields of :class:`planning_control_plane.model.Node`.
_NODE_TYPE_VALUES = frozenset(member.value for member in NodeType)
_NODE_STATUS_VALUES = frozenset(member.value for member in NodeStatus)
_TRACK_STATUS_VALUES = frozenset(member.value for member in TrackStatus)

#: ERROR sorts before WARNING by explicit rank, not by alphabetical accident.
_SEVERITY_ORDER = {Severity.ERROR: 0, Severity.WARNING: 1}

#: The three independent tracks (spec §11), each validated separately.
_TRACK_FIELDS = ("discussion_status", "writeback_status", "implementation_status")

#: Cross-edge node fields and the rule reported when a target is unknown.
_EDGE_RULES = (
    ("depends_on", "missing-dependency-target"),
    ("blocks", "missing-blocks-target"),
    ("related_to", "missing-related-target"),
    ("supersedes", "missing-supersedes-target"),
)


def _issue(severity: Severity, rule: str, message: str, node_id: str | None = None) -> ValidationIssue:
    return ValidationIssue(severity=severity, rule=rule, message=message, node_id=node_id)


def _issue_sort_key(issue: ValidationIssue) -> tuple[int, str, str, str]:
    """ERROR first, then node id (None as ""), then rule, then message."""
    return (_SEVERITY_ORDER[issue.severity], issue.node_id or "", issue.rule, issue.message)


def validate_project(project: Project) -> list[ValidationIssue]:
    """Run all validation rules over *project* and return sorted issues.

    Loader-collected schema issues come first in construction order, rule
    results are appended, and the combined list is sorted deterministically
    (severity, node id, rule, message). The input project is not modified.
    """
    issues: list[ValidationIssue] = list(project.load_issues)
    graph = PlanningGraph(project)
    _check_structure(project, graph, issues)
    _check_current_focus(project, issues)
    _check_decisions(project, issues)
    _check_consistency(project, graph, issues)
    _check_references(project, issues)
    _check_output_directory(project, issues)
    issues.sort(key=_issue_sort_key)
    return issues


# ---------------------------------------------------------------- structure


def _check_structure(project: Project, graph: PlanningGraph, issues: list[ValidationIssue]) -> None:
    """Structural rules: enums, parents, edge targets, cycles, unknown fields."""
    known = set(project.nodes)
    for node_id in project.sorted_node_ids():
        node = project.nodes[node_id]

        if node.type not in _NODE_TYPE_VALUES:
            issues.append(_issue(Severity.ERROR, "invalid-type", f"type '{node.type}' is not a valid node type", node_id))
        if node.status not in _NODE_STATUS_VALUES:
            issues.append(_issue(Severity.ERROR, "invalid-status", f"status '{node.status}' is not a valid node status", node_id))
        for field_name in _TRACK_FIELDS:
            value = getattr(node, field_name)
            if value not in _TRACK_STATUS_VALUES:
                issues.append(
                    _issue(Severity.ERROR, "invalid-track-status", f"'{field_name}' value '{value}' is not a valid track status", node_id)
                )

        parent = node.parent
        if parent is not None:
            if parent == node_id:
                issues.append(_issue(Severity.ERROR, "self-parent", "node declares itself as its own parent", node_id))
            elif parent not in known:
                issues.append(_issue(Severity.ERROR, "missing-parent", f"parent '{parent}' is not a known node", node_id))

        for edge_field, rule in _EDGE_RULES:
            for target in sorted(set(getattr(node, edge_field))):
                if target not in known:
                    issues.append(_issue(Severity.ERROR, rule, f"{edge_field} target '{target}' is not a known node", node_id))

        if node.unknown_fields:
            issues.append(_issue(Severity.WARNING, "unknown-field", f"unknown node fields: {', '.join(node.unknown_fields)}", node_id))

    for cycle in graph.find_dependency_cycles():
        issues.append(_issue(Severity.ERROR, "dependency-cycle", " -> ".join(cycle), node_id=cycle[0]))
    for cycle in graph.find_parent_cycles():
        issues.append(_issue(Severity.ERROR, "parent-cycle", " -> ".join(cycle), node_id=cycle[0]))

    if project.config.unknown_keys:
        issues.append(
            _issue(
                Severity.WARNING,
                "unknown-field",
                f"project.yaml has unknown top-level keys: {', '.join(project.config.unknown_keys)}",
            )
        )
    if project.config.authority.unknown_keys:
        issues.append(
            _issue(
                Severity.WARNING,
                "unknown-field",
                f"project.yaml has unknown authority keys: {', '.join(project.config.authority.unknown_keys)}",
            )
        )


# ------------------------------------------------------------ current focus


def _check_current_focus(project: Project, issues: list[ValidationIssue]) -> None:
    """Focus rules: not set, pointing nowhere, or pointing at DONE work."""
    focus = project.config.current_focus
    if not focus:
        if project.nodes:
            issues.append(
                _issue(Severity.WARNING, "current-focus-not-set", "planning nodes exist but project.yaml sets no current_focus")
            )
        return
    if focus not in project.nodes:
        issues.append(_issue(Severity.ERROR, "invalid-current-focus", f"current_focus '{focus}' is not a known node"))
        return
    if project.nodes[focus].status == NodeStatus.DONE.value:
        issues.append(
            _issue(Severity.WARNING, "focus-on-done", f"current_focus node '{focus}' is DONE; move focus to active work", focus)
        )


# ---------------------------------------------------------------- decisions


def _check_decisions(project: Project, issues: list[ValidationIssue]) -> None:
    """Duplicate decision ids within one node, across all four lists."""
    for node_id in project.sorted_node_ids():
        node = project.nodes[node_id]
        categories_by_id: dict[str, list[str]] = {}
        for category, decision in node.all_decisions:
            categories_by_id.setdefault(decision.id, []).append(category)
        duplicated = sorted(dec_id for dec_id, categories in categories_by_id.items() if len(categories) > 1)
        for dec_id in duplicated:
            categories = categories_by_id[dec_id]
            distinct: list[str] = []
            for category in categories:
                if category not in distinct:
                    distinct.append(category)
            issues.append(
                _issue(
                    Severity.ERROR,
                    "duplicate-decision-id",
                    f"decision id '{dec_id}' is declared {len(categories)} times (categories: {', '.join(distinct)})",
                    node_id,
                )
            )


# ------------------------------------------------------- planning consistency


def _check_consistency(project: Project, graph: PlanningGraph, issues: list[ValidationIssue]) -> None:
    """Cross-field planning consistency rules (spec §13, §16)."""
    for node_id in project.sorted_node_ids():
        node = project.nodes[node_id]

        if node.status == NodeStatus.DONE.value and node.blocking_decisions:
            decision_ids = ", ".join(sorted(decision.id for decision in node.blocking_decisions))
            issues.append(
                _issue(Severity.ERROR, "done-with-blocking-decision", f"status is DONE but blocking_decisions is not empty ({decision_ids})", node_id)
            )

        if node.status == NodeStatus.BLOCKED.value and not node.blocking_decisions:
            state = graph.dependency_state(node)
            if not (state["missing"] or state["deferred"] or state["pending"]):
                issues.append(
                    _issue(
                        Severity.WARNING,
                        "blocked-without-blocker",
                        "status is BLOCKED but no blocking decisions or unresolved dependencies are recorded",
                        node_id,
                    )
                )

        if node.writeback_status == TrackStatus.DONE.value and not node.canonical_sources:
            issues.append(
                _issue(Severity.WARNING, "writeback-done-without-canonical-source", "writeback_status is DONE but canonical_sources is empty", node_id)
            )

        for target in sorted(set(node.depends_on)):
            dependency = project.nodes.get(target)
            if dependency is not None and dependency.status == NodeStatus.DEFERRED.value:
                issues.append(_issue(Severity.WARNING, "depends-on-deferred", f"depends_on target '{target}' is DEFERRED", node_id))


# ---------------------------------------------------------------- output safety


def _check_output_directory(project: Project, issues: list[ValidationIssue]) -> None:
    """The build output directory must never overlap the planning data.

    ``pcp build`` rebuilds the output directory from scratch (spec §22), so
    an output directory equal to ``.planning`` — or any ancestor of it,
    including the repository root — would delete the planning source on
    build. That configuration is rejected up front (spec §37: planning data
    is source, HTML is projection).
    """
    out_dir = project.output_dir().resolve()
    planning_dir = project.planning_dir().resolve()
    if out_dir == planning_dir or planning_dir.is_relative_to(out_dir):
        issues.append(
            _issue(
                Severity.ERROR,
                "unsafe-output-directory",
                f"output.directory '{project.config.output_directory}' resolves to '{out_dir}', "
                f"which contains the planning data at '{planning_dir}'; pcp build would delete it",
            )
        )


# ---------------------------------------------------------------- references


def _check_references(project: Project, issues: list[ValidationIssue]) -> None:
    """Reference validation (spec §17): canonical and evidence are distinct.

    Every entry of both source lists is resolved against the repository
    root. Escaping entries are reported once (``reference-escapes-repo``)
    and not additionally as missing.
    """
    root = Path(os.path.normpath(project.root))
    for node_id in project.sorted_node_ids():
        node = project.nodes[node_id]
        for path in node.canonical_sources:
            _check_reference(root, node_id, "canonical", path, issues)
        for path in node.evidence_sources:
            _check_reference(root, node_id, "evidence", path, issues)


def _check_reference(root: Path, node_id: str, kind: str, path: str, issues: list[ValidationIssue]) -> None:
    """Check one repository-relative source reference.

    *kind* is ``"canonical"`` or ``"evidence"``; a missing file is an ERROR
    for canonical sources and a WARNING for evidence sources.
    """
    if PurePath(path).is_absolute():
        issues.append(
            _issue(
                Severity.ERROR,
                "reference-escapes-repo",
                f"{kind}_sources entry '{path}' is not repository-relative (absolute path or escapes the repository root)",
                node_id,
            )
        )
        return
    candidate = Path(os.path.normpath(os.path.join(root, path)))
    if not candidate.is_relative_to(root):
        issues.append(
            _issue(
                Severity.ERROR,
                "reference-escapes-repo",
                f"{kind}_sources entry '{path}' is not repository-relative (absolute path or escapes the repository root)",
                node_id,
            )
        )
        return
    if not candidate.is_file():
        if kind == "canonical":
            issues.append(_issue(Severity.ERROR, "canonical-source-missing", f"canonical source '{path}' does not exist in the repository", node_id))
        else:
            issues.append(_issue(Severity.WARNING, "evidence-source-missing", f"evidence source '{path}' does not exist in the repository", node_id))
