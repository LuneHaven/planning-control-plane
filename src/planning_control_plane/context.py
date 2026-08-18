"""Session Resume Capsule: build and render one node's context (spec §12,
§14, §15, §20, §21).

The capsule is the V0.1 centerpiece: a compact, deterministic plain-text
snapshot of one planning node plus everything it inherits from its
ancestors (frozen decisions, scope guardrails and canonical references),
sized to be pasted directly into a fresh LLM session so parent constraints
and frozen decisions survive context loss. PCP stores, inherits and
displays decisions; it never judges whether they are correct (spec §12).

Two sizes (spec §21): ``compact`` (default) carries the resume essentials;
``full`` additionally discloses ancestor summaries, related nodes,
dependency details, nodes waiting on this one, and deferred decisions.

Determinism: no timestamps, no random input, no dict-order dependence.
Nodes and decisions are emitted in node-id / decision-id order; inherited
content is grouped nearest parent first, then higher ancestors (spec §14).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from planning_control_plane.graph import PlanningGraph
from planning_control_plane.model import Decision, Project, TrackStatus

#: Dependency states reported in full mode, in classification order.
_DEPENDENCY_STATES = ("missing", "deferred", "pending")


def track_display(value: str) -> str:
    """Normalize one track status for terminal/capsule display.

    ``NOT_APPLICABLE`` renders as ``N/A``; every other value is returned
    unchanged (spec §11).
    """
    if value == TrackStatus.NOT_APPLICABLE.value:
        return "N/A"
    return value


# --------------------------------------------------------------------------
# Capsule payload types
# --------------------------------------------------------------------------


@dataclass
class InheritedGroup:
    """Frozen decisions inherited from a single ancestor (spec §14)."""

    ancestor_id: str
    ancestor_title: str
    decisions: list[Decision] = field(default_factory=list)


@dataclass
class AncestorSummary:
    """Identity card of one ancestor node (full mode only)."""

    id: str
    title: str
    type: str
    status: str
    objective: str = ""


@dataclass
class RelatedNodeRef:
    """A node linked through ``related_to`` in either direction."""

    id: str
    title: str
    status: str


@dataclass
class DependencyDetail:
    """One ``depends_on`` target with its satisfaction state.

    ``state`` is ``missing`` (target not in the node set), ``deferred``,
    ``pending``, or ``done`` (target status DONE).
    """

    id: str
    title: str
    status: str
    state: str


@dataclass
class BlocksMeRef:
    """A node waiting on this node (its ``depends_on`` or ``blocks`` points
    at the capsule's node)."""

    id: str
    title: str
    status: str


@dataclass
class ContextCapsule:
    """Everything ``pcp context`` needs to resume work on one node.

    Fields cover every section of spec §20 plus the full-mode additions of
    spec §21. Node-owned lists keep their declaration order; inherited
    content is ordered nearest ancestor first.
    """

    # --- identity -----------------------------------------------------------
    project_id: str = ""
    project_name: str = ""
    node_id: str = ""
    node_title: str = ""
    node_type: str = ""
    node_status: str = ""
    #: Ancestors of the node, root first, as ``(id, title)`` pairs. The
    #: node itself is not included.
    parent_path: list[tuple[str, str]] = field(default_factory=list)

    # --- narrative ----------------------------------------------------------
    objective: str = ""
    next_action: str = ""

    # --- frozen decisions (spec §12/§14) -------------------------------------
    #: One group per ancestor that contributed at least one non-shadowed
    #: frozen decision, nearest parent first.
    inherited_frozen: list[InheritedGroup] = field(default_factory=list)
    current_frozen: list[Decision] = field(default_factory=list)

    # --- scope guard (spec §15) ----------------------------------------------
    scope: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)
    #: Ancestor scope entries as ``(ancestor_id, item)``, nearest ancestor
    #: first; duplicate item texts keep the nearest ancestor's attribution,
    #: and items the node declares itself are shadowed (they already appear
    #: in its own In Scope section).
    inherited_scope: list[tuple[str, str]] = field(default_factory=list)
    #: Ancestor out-of-scope entries, same ordering/shadowing rules. Scope
    #: guardrails have two halves (spec §15); the out-of-scope half guards
    #: against scope creep just as much and must stay visible in child work.
    inherited_out_of_scope: list[tuple[str, str]] = field(default_factory=list)

    # --- open decision classes (spec §13) -------------------------------------
    open_decisions: list[Decision] = field(default_factory=list)
    blocking_decisions: list[Decision] = field(default_factory=list)
    #: Only populated in full mode; always an empty list in compact mode.
    deferred_decisions: list[Decision] = field(default_factory=list)

    # --- references (spec §17) ------------------------------------------------
    canonical_sources: list[str] = field(default_factory=list)
    evidence_sources: list[str] = field(default_factory=list)
    #: Ancestor canonical sources as ``(ancestor_id, path)``, nearest
    #: ancestor first; duplicate paths and paths the node links itself are
    #: shadowed (spec §14, "important canonical references").
    inherited_canonical: list[tuple[str, str]] = field(default_factory=list)

    # --- independent tracks (spec §11) ----------------------------------------
    discussion_status: str = ""
    writeback_status: str = ""
    implementation_status: str = ""

    full: bool = False

    # --- full-mode additions (spec §21) ---------------------------------------
    ancestor_summaries: list[AncestorSummary] = field(default_factory=list)
    related_nodes: list[RelatedNodeRef] = field(default_factory=list)
    dependency_details: list[DependencyDetail] = field(default_factory=list)
    blocks_me: list[BlocksMeRef] = field(default_factory=list)


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------


def build_capsule(project: Project, node_id: str, full: bool = False) -> ContextCapsule:
    """Assemble the capsule for *node_id*.

    Raises :class:`ValueError` when *node_id* is not part of the project's
    node set.
    """
    node = project.nodes.get(node_id)
    if node is None:
        raise ValueError(f"unknown node id '{node_id}'")

    graph = PlanningGraph(project)
    ancestors = graph.ancestors(node_id)  # nearest parent first (spec §14)

    # Parent path is the ancestor chain root first; the node itself is not
    # part of the path.
    parent_path = [(aid, project.nodes[aid].title) for aid in reversed(ancestors)]

    # Inherited frozen decisions: walk nearest ancestor first, deduplicate
    # globally by decision id (nearest declaration wins). Ids the current
    # node declares itself shadow inherited ones: they belong to the
    # "Frozen Decisions (this node)" section instead. Within one group the
    # decisions are sorted by id.
    shadowed = {decision.id for decision in node.frozen_decisions}
    inherited_frozen: list[InheritedGroup] = []
    for ancestor_id in ancestors:
        ancestor = project.nodes[ancestor_id]
        kept: list[Decision] = []
        for decision in ancestor.frozen_decisions:
            if decision.id in shadowed:
                continue
            shadowed.add(decision.id)
            kept.append(decision)
        if kept:
            kept.sort(key=lambda decision: decision.id)
            inherited_frozen.append(
                InheritedGroup(ancestor_id=ancestor_id, ancestor_title=ancestor.title, decisions=kept)
            )

    # Inherited scope guardrails: ancestor scope and out_of_scope entries,
    # nearest ancestor first, deduplicated by item text to avoid bloat
    # (spec §14). Items the node declares in its own lists are shadowed —
    # they are already shown in its In Scope / Out of Scope sections.
    inherited_scope: list[tuple[str, str]] = []
    inherited_out_of_scope: list[tuple[str, str]] = []
    seen_scope: set[str] = set(node.scope)
    seen_out_of_scope: set[str] = set(node.out_of_scope)
    for ancestor_id in ancestors:
        ancestor_node = project.nodes[ancestor_id]
        for item in ancestor_node.scope:
            if item in seen_scope:
                continue
            seen_scope.add(item)
            inherited_scope.append((ancestor_id, item))
        for item in ancestor_node.out_of_scope:
            if item in seen_out_of_scope:
                continue
            seen_out_of_scope.add(item)
            inherited_out_of_scope.append((ancestor_id, item))

    # Inherited canonical references (spec §14): ancestor canonical paths,
    # nearest ancestor first, deduplicated by path. Paths this node links
    # itself stay in its own "Canonical Sources" section only.
    own_canonical = set(node.canonical_sources)
    inherited_canonical: list[tuple[str, str]] = []
    seen_canonical: set[str] = set()
    for ancestor_id in ancestors:
        for path in project.nodes[ancestor_id].canonical_sources:
            if path in seen_canonical or path in own_canonical:
                continue
            seen_canonical.add(path)
            inherited_canonical.append((ancestor_id, path))

    capsule = ContextCapsule(
        project_id=project.config.id,
        project_name=project.config.name,
        node_id=node.id,
        node_title=node.title,
        node_type=node.type,
        node_status=node.status,
        parent_path=parent_path,
        objective=node.objective,
        next_action=node.next_action,
        inherited_frozen=inherited_frozen,
        current_frozen=list(node.frozen_decisions),
        scope=list(node.scope),
        out_of_scope=list(node.out_of_scope),
        inherited_scope=inherited_scope,
        inherited_out_of_scope=inherited_out_of_scope,
        open_decisions=list(node.open_decisions),
        blocking_decisions=list(node.blocking_decisions),
        deferred_decisions=list(node.deferred_decisions) if full else [],
        canonical_sources=list(node.canonical_sources),
        evidence_sources=list(node.evidence_sources),
        inherited_canonical=inherited_canonical,
        discussion_status=node.discussion_status,
        writeback_status=node.writeback_status,
        implementation_status=node.implementation_status,
        full=full,
    )

    if not full:
        return capsule

    # --- full-mode progressive disclosure (spec §21) -------------------------
    capsule.ancestor_summaries = [
        AncestorSummary(
            id=aid,
            title=project.nodes[aid].title,
            type=project.nodes[aid].type,
            status=project.nodes[aid].status,
            objective=project.nodes[aid].objective,
        )
        for aid, _title in parent_path  # root first, like the path itself
    ]

    capsule.related_nodes = [
        RelatedNodeRef(
            id=related_id,
            title=project.nodes[related_id].title,
            status=project.nodes[related_id].status,
        )
        for related_id in graph.related_nodes(node_id)  # includes reverse links, sorted
    ]

    # One entry per depends_on target, sorted by id. States come from the
    # graph classification; a target in none of the problem categories is
    # satisfied, i.e. done.
    dep_state = graph.dependency_state(node)
    state_by_target: dict[str, str] = {}
    for category in _DEPENDENCY_STATES:
        for target_id in dep_state[category]:
            state_by_target[target_id] = category
    capsule.dependency_details = []
    for target_id in sorted(set(node.depends_on)):
        target = project.nodes.get(target_id)
        capsule.dependency_details.append(
            DependencyDetail(
                id=target_id,
                title=target.title if target is not None else "",
                status=target.status if target is not None else "",
                state=state_by_target.get(target_id, "done"),
            )
        )

    capsule.blocks_me = [
        BlocksMeRef(id=other_id, title=project.nodes[other_id].title, status=project.nodes[other_id].status)
        for other_id in sorted(
            other_id
            for other_id, other in project.nodes.items()
            if other_id != node_id and (node_id in other.depends_on or node_id in other.blocks)
        )
    ]

    return capsule


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _squeeze(value: str) -> str:
    """Collapse internal whitespace (incl. newlines) to single spaces."""
    return " ".join((value or "").split())


def _text_block(text: str) -> list[str]:
    """Indented body of a free-text field; ``(none)`` when empty. Multi-line
    values keep their line structure under a two-space indent."""
    stripped = (text or "").strip()
    if not stripped:
        return ["  (none)"]
    return [("  " + line).rstrip() for line in stripped.splitlines()]


def _bullets(items: list[str]) -> list[str]:
    """Render ``- item`` lines, or a single ``(none)`` placeholder."""
    if not items:
        return ["  (none)"]
    return [f"  - {_squeeze(item)}" for item in items]


def _decision_bullets(decisions: list[Decision]) -> list[str]:
    return _bullets([f"{decision.id}: {_squeeze(decision.summary)}" for decision in decisions])


def _frozen_lines(group: InheritedGroup) -> list[str]:
    lines = []
    for decision in group.decisions:
        line = f"  [{group.ancestor_id}] {decision.id}: {_squeeze(decision.summary)}"
        if decision.source:
            line += f" (source: {_squeeze(decision.source)})"
        lines.append(line)
    return lines


def render_capsule(capsule: ContextCapsule) -> str:
    """Render a capsule as deterministic plain text (spec §20/§21).

    Compact and full share the same skeleton; full appends the progressive
    disclosure sections. Every empty list renders as ``(none)`` — except
    "Inherited Scope Guardrails", which is omitted entirely when empty to
    keep the compact capsule small.
    """
    sections: list[list[str]] = []

    sections.append(
        [
            "=== PCP CONTEXT CAPSULE ===",
            f"Project: {_squeeze(capsule.project_name)} ({capsule.project_id})",
            f"Node: {capsule.node_id} — {_squeeze(capsule.node_title)} ({capsule.node_type} / {capsule.node_status})",
            "Parent Path: " + (" > ".join(ancestor_id for ancestor_id, _title in capsule.parent_path) or "(none)"),
            f"Mode: {'full' if capsule.full else 'compact'}",
        ]
    )

    sections.append(["Objective:"] + _text_block(capsule.objective))

    inherited_lines: list[str] = []
    for group in capsule.inherited_frozen:
        inherited_lines.extend(_frozen_lines(group))
    sections.append(["Inherited Frozen Decisions:"] + (inherited_lines or ["  (none)"]))

    sections.append(
        ["Frozen Decisions (this node):"]
        + (
            [f"  {decision.id}: {_squeeze(decision.summary)}" + (
                f" (source: {_squeeze(decision.source)})" if decision.source else ""
            ) for decision in capsule.current_frozen]
            or ["  (none)"]
        )
    )

    if capsule.inherited_scope:
        sections.append(
            ["Inherited Scope Guardrails:"]
            + [f"  [{ancestor_id}] {_squeeze(item)}" for ancestor_id, item in capsule.inherited_scope]
        )

    if capsule.inherited_out_of_scope:
        sections.append(
            ["Inherited Out-of-Scope Guardrails:"]
            + [f"  [{ancestor_id}] {_squeeze(item)}" for ancestor_id, item in capsule.inherited_out_of_scope]
        )

    sections.append(
        ["In Scope:"] + _bullets(capsule.scope) + ["Out of Scope:"] + _bullets(capsule.out_of_scope)
    )

    sections.append(
        ["Open Decisions:"]
        + _decision_bullets(capsule.open_decisions)
        + ["Blocking Decisions:"]
        + _decision_bullets(capsule.blocking_decisions)
    )

    if capsule.inherited_canonical:
        sections.append(
            ["Inherited Canonical Sources:"]
            + [f"  [{ancestor_id}] {path}" for ancestor_id, path in capsule.inherited_canonical]
        )

    sections.append(
        ["Canonical Sources:"]
        + _bullets(capsule.canonical_sources)
        + ["Evidence Sources:"]
        + _bullets(capsule.evidence_sources)
    )

    sections.append(
        [
            "Discussion: {} | Writeback: {} | Implementation: {}".format(
                track_display(capsule.discussion_status),
                track_display(capsule.writeback_status),
                track_display(capsule.implementation_status),
            )
        ]
    )

    sections.append(["Next Action:"] + _text_block(capsule.next_action))

    if capsule.full:
        sections.append(
            ["Ancestor Summaries:"]
            + (
                [
                    "  [{}] {} / {}{}".format(
                        summary.id,
                        summary.type,
                        summary.status,
                        f" — {_squeeze(summary.objective.splitlines()[0])}" if summary.objective.strip() else "",
                    )
                    for summary in capsule.ancestor_summaries
                ]
                or ["  (none)"]
            )
        )

        sections.append(
            ["Related Nodes:"]
            + (
                [f"  [{ref.id}] {ref.status} — {_squeeze(ref.title)}" for ref in capsule.related_nodes]
                or ["  (none)"]
            )
        )

        sections.append(
            ["Dependencies:"]
            + (
                [
                    f"  - {detail.id} ({_squeeze(detail.status) if detail.status else detail.state})"
                    for detail in capsule.dependency_details
                ]
                or ["  (none)"]
            )
        )

        sections.append(
            ["Blocks / Waited By:"]
            + ([f"  - {ref.id} ({ref.status}) — {_squeeze(ref.title)}" for ref in capsule.blocks_me] or ["  (none)"])
        )

        sections.append(["Deferred Decisions:"] + _decision_bullets(capsule.deferred_decisions))

    body = "\n\n".join("\n".join(section) for section in sections)
    return body + "\n\n=== END CAPSULE ===\n"
