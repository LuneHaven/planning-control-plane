"""Core data model for the Planning Control Plane.

This module is intentionally free of I/O. It defines:

* the controlled enums (node type, node status, per-track status, idea status),
* the in-memory representation of a planning project
  (:class:`Node`, :class:`Decision`, :class:`IdeaSource`, :class:`IdeaOutcome`,
  :class:`Idea`, :class:`ProjectConfig`, :class:`Project`),
* the shared :class:`ValidationIssue` type used by loader and validator,
  together with the idea-layer rule-name closed set (:data:`IDEA_RULE_NAMES`)
  and its issue builder (:func:`idea_issue`).

Loading lives in :mod:`planning_control_plane.loader`, graph operations in
:mod:`planning_control_plane.graph`, rules in
:mod:`planning_control_plane.validator`.

Design note (spec §10/§11): enum fields on :class:`Node` are stored as plain
strings, not enum members. The loader keeps raw values even when they are not
part of the controlled enum, so that ``pcp validate`` can report every problem
in one run instead of crashing on the first invalid value. Membership checks
against the enums below are performed by the validator.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

#: Planning directory name inside a target repository.
PLANNING_DIR = ".planning"

#: Allowed node id charset: alphanumeric first char, then alnum/./-/_
#: (keeps generated HTML filenames safe and ids grep-friendly).
NODE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

#: Layout directory name for generated HTML (relative to the planning dir
#: unless the configured output directory says otherwise).
DIST_DIR = "dist"


class PCPError(Exception):
    """Base class for errors raised by the PCP engine."""


class NodeType(str, Enum):
    """Controlled node types (spec §9)."""

    PROGRAM = "PROGRAM"
    PHASE = "PHASE"
    STRATEGY = "STRATEGY"
    DISCUSSION = "DISCUSSION"
    DECISION = "DECISION"
    INVESTIGATION = "INVESTIGATION"
    IMPLEMENTATION = "IMPLEMENTATION"
    CLOSURE = "CLOSURE"


class NodeStatus(str, Enum):
    """Controlled planning lifecycle statuses (spec §10)."""

    NOT_STARTED = "NOT_STARTED"
    DISCUSSING = "DISCUSSING"
    INVESTIGATING = "INVESTIGATING"
    DECIDED = "DECIDED"
    WRITEBACK_PENDING = "WRITEBACK_PENDING"
    WRITEBACK_DONE = "WRITEBACK_DONE"
    READY = "READY"
    IMPLEMENTING = "IMPLEMENTING"
    BLOCKED = "BLOCKED"
    DONE = "DONE"
    DEFERRED = "DEFERRED"


#: Statuses counted as "Active" in progress summaries.
ACTIVE_STATUSES = frozenset(
    {
        NodeStatus.DISCUSSING.value,
        NodeStatus.INVESTIGATING.value,
        NodeStatus.DECIDED.value,
        NodeStatus.WRITEBACK_PENDING.value,
        NodeStatus.WRITEBACK_DONE.value,
        NodeStatus.READY.value,
        NodeStatus.IMPLEMENTING.value,
    }
)


class TrackStatus(str, Enum):
    """Status of one independent track: discussion / writeback / implementation.

    Spec §11: the three tracks are stored separately and never derived from
    each other. ``NOT_APPLICABLE`` covers cases such as a pure discussion
    node that has no implementation work; it is written ``N/A`` in YAML and
    terminal output.
    """

    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class IdeaStatus(str, Enum):
    """Controlled idea-layer lifecycle statuses (spec §53.1).

    Ideas capture *uncommitted* thinking. PROMOTED is the only bridge into
    the planning graph and requires an outcome (spec §55.5); the validator,
    not the loader, checks membership.
    """

    OPEN = "OPEN"
    PARKED = "PARKED"
    PROMOTED = "PROMOTED"
    DISCARDED = "DISCARDED"


#: Accepted YAML spellings for :attr:`TrackStatus.NOT_APPLICABLE`.
TRACK_STATUS_ALIASES = {
    "N/A": TrackStatus.NOT_APPLICABLE.value,
    "NA": TrackStatus.NOT_APPLICABLE.value,
    "N.A.": TrackStatus.NOT_APPLICABLE.value,
    "NOT_APPLICABLE": TrackStatus.NOT_APPLICABLE.value,
    "NOT APPLICABLE": TrackStatus.NOT_APPLICABLE.value,
}


class Severity(str, Enum):
    """Validation issue severity."""

    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True)
class ValidationIssue:
    """A single finding produced by loader or validator (spec §16).

    Every issue carries enough context to act on: the node id (``None`` for
    project-level findings), a stable rule name, and a human-readable reason.
    """

    severity: Severity
    rule: str
    message: str
    node_id: str | None = None

    def format(self) -> str:
        """One-line rendering used by ``pcp validate``."""
        node = self.node_id if self.node_id else "-"
        return f"{self.severity.value:<7} {node:<12} {self.rule}: {self.message}"


#: Rule names of the idea layer (spec §58.1). The closed set that tells
#: idea-layer validation issues from node-layer ones: the ``pcp build``
#: gate excludes exactly these rules (spec IDEA-D59), and every issue they
#: produce carries the ``idea '<id>': `` message prefix (spec IDEA-D64).
IDEA_RULE_NAMES = frozenset(
    {
        "invalid-idea-file",
        "invalid-idea",
        "missing-idea-title",
        "invalid-idea-field",
        "invalid-idea-source",
        "invalid-idea-outcome",
        "invalid-idea-id",
        "duplicate-idea-id",
        "ignored-idea-file",
        "invalid-idea-status",
        "missing-idea-relates-target",
        "promoted-without-outcome",
        "missing-outcome-target",
        "outcome-without-promotion",
        "idea-source-escapes-repo",
        "idea-source-missing",
        "idea-id-collides-with-node",
        "idea-unknown-field",
    }
)


def idea_issue(
    severity: Severity, rule: str, detail: str, ident: str, node_id: str | None = None
) -> ValidationIssue:
    """Build one idea-layer issue with the mandatory message prefix.

    ``ValidationIssue`` has a single id column shared by nodes and ideas,
    so every idea-layer message starts with ``idea '<ident>': `` (spec
    IDEA-D64). *ident* is the idea id, or the repository-relative path for
    the file-level rules whose ``node_id`` stays ``None``.
    """
    return ValidationIssue(
        severity=severity, rule=rule, message=f"idea '{ident}': {detail}", node_id=node_id
    )


@dataclass
class Decision:
    """A decision attached to a node (frozen / open / blocking / deferred).

    PCP stores, inherits and displays decisions; it never judges whether a
    decision is *correct* (spec §12).
    """

    id: str
    summary: str
    source: str | None = None


@dataclass
class IdeaSource:
    """One justification entry on an idea (spec §52).

    ``ref`` is an optional repository-relative path (validated like an
    evidence source); ``note`` is free text and the only channel for the
    world outside the repository (benchmark targets live there). At least
    one of the two must be non-empty — enforced by the loader.
    """

    ref: str | None = None
    note: str | None = None


@dataclass
class IdeaOutcome:
    """Graduation target of a PROMOTED idea (spec §55.2)."""

    node: str
    note: str = ""


@dataclass
class Idea:
    """One captured thought in the idea layer (spec §51).

    Mirrors :class:`Node` in loading discipline (raw enum strings, unknown
    field tracking, ``source_file``) but carries no planning semantics: no
    tracks, no objective/scope, no decisions, no next_action — needing
    those is the signal to graduate, not to grow the schema.
    """

    id: str
    title: str
    status: str = IdeaStatus.OPEN.value
    detail: str = ""
    relates_to: list[str] = field(default_factory=list)
    benchmark_sources: list[IdeaSource] = field(default_factory=list)
    methodology_sources: list[IdeaSource] = field(default_factory=list)
    outcome: IdeaOutcome | None = None
    created: str = ""
    last_updated: str = ""
    #: Keys present in the source YAML but not part of the idea schema.
    unknown_fields: list[str] = field(default_factory=list)
    #: Repository-relative path of the file this idea was loaded from.
    source_file: str | None = None


def idea_sort_key(idea: Idea) -> tuple[bool, str, str]:
    """Display order inside one idea status group (spec IDEA-D61).

    ``(last_updated is empty, last_updated, id)``: dated ideas sort oldest
    first so stale thinking surfaces at the top of its group, and undated
    ideas sort last. ``last_updated`` is an unvalidated free string that
    defaults to ``""``, so a plain ascending sort would float *undated*
    ideas rather than *stale* ones — the opposite of the intent.

    The single ordering source for ``pcp ideas`` and the generated ideas
    page, so the same data never lists in two different orders. Relative
    order of non-ISO spellings is undefined (documented cost of not
    validating the format; no date parsing is introduced).
    """
    return (idea.last_updated == "", idea.last_updated, idea.id)


@dataclass
class Node:
    """One planning node in the planning graph (spec §8).

    Enum-valued fields (``type``, ``status`` and the three track statuses)
    are stored as raw strings; see the module docstring for why.
    """

    id: str
    title: str
    type: str = NodeType.DISCUSSION.value
    parent: str | None = None
    status: str = NodeStatus.NOT_STARTED.value
    objective: str = ""
    scope: list[str] = field(default_factory=list)
    out_of_scope: list[str] = field(default_factory=list)
    frozen_decisions: list[Decision] = field(default_factory=list)
    open_decisions: list[Decision] = field(default_factory=list)
    blocking_decisions: list[Decision] = field(default_factory=list)
    deferred_decisions: list[Decision] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    related_to: list[str] = field(default_factory=list)
    supersedes: list[str] = field(default_factory=list)
    canonical_sources: list[str] = field(default_factory=list)
    evidence_sources: list[str] = field(default_factory=list)
    next_action: str = ""
    discussion_status: str = TrackStatus.NOT_STARTED.value
    writeback_status: str = TrackStatus.NOT_STARTED.value
    implementation_status: str = TrackStatus.NOT_STARTED.value
    last_updated: str = ""
    #: Keys present in the source YAML but not part of the schema.
    unknown_fields: list[str] = field(default_factory=list)
    #: Repository-relative path of the file this node was loaded from.
    source_file: str | None = None

    @property
    def all_decisions(self) -> list[tuple[str, Decision]]:
        """All decisions on this node tagged with their category."""
        return (
            [("frozen", d) for d in self.frozen_decisions]
            + [("open", d) for d in self.open_decisions]
            + [("blocking", d) for d in self.blocking_decisions]
            + [("deferred", d) for d in self.deferred_decisions]
        )


@dataclass
class AuthorityConfig:
    """Roots used to classify linked sources (spec §6).

    These roots only help PCP label links; PCP never assumes any of them
    exist in a target repository.
    """

    canonical_roots: list[str] = field(default_factory=list)
    current_state_roots: list[str] = field(default_factory=list)
    planning_roots: list[str] = field(default_factory=list)
    unknown_keys: list[str] = field(default_factory=list)

    def classify(self, path: str) -> str:
        """Classify a repository-relative path.

        Returns one of ``canonical`` / ``current-state`` / ``planning``, or
        ``""`` when no configured root matches. Longer (more specific) roots
        win so that nested configurations behave intuitively.
        """
        normalized = self._normalize(path)
        best = ""
        best_len = -1
        for label, roots in (
            ("canonical", self.canonical_roots),
            ("current-state", self.current_state_roots),
            ("planning", self.planning_roots),
        ):
            for root in roots:
                root_norm = self._normalize(root)
                if not root_norm:
                    continue
                if normalized == root_norm or normalized.startswith(root_norm + "/"):
                    if len(root_norm) > best_len:
                        best, best_len = label, len(root_norm)
        return best

    @staticmethod
    def _normalize(path: str) -> str:
        """Normalize a path for prefix comparison: forward slashes, no
        leading ``./``, no trailing ``/``. Unlike ``str.lstrip`` (whose
        argument is a character *set*), only a true leading ``./`` prefix is
        stripped, so dot-directories such as ``.planning`` survive intact.
        """
        normalized = path.replace("\\", "/")
        while normalized.startswith("./"):
            normalized = normalized[2:]
        return normalized.rstrip("/")


@dataclass
class UIConfig:
    """Parsed ``ui:`` section of ``project.yaml`` (UI V0.1.1, Owner UI-D1).

    This is a **UI projection configuration**, not planning-node semantics:
    it selects the **default** locale of the generated human-facing HTML.
    Since V0.1.2 the page also lets the reader switch locale at runtime in
    the browser (a presentation-only ``localStorage`` preference that never
    reaches this file or the generated output). Node ids, decision ids,
    stored enum values, ``pcp context`` capsules and the machine-facing CLI
    output are unaffected either way (Owner UI-D2 / LANG-D3).

    ``locale`` is always a supported locale (the loader falls back to the
    default and records a WARNING for anything else); ``raw_locale`` keeps
    what the file actually said, for that warning message.
    """

    #: Resolved, always-supported locale used to render the site.
    locale: str = "en"
    #: The value as written in project.yaml (``None`` when the key is absent).
    raw_locale: str | None = None
    unknown_keys: list[str] = field(default_factory=list)


@dataclass
class ProjectConfig:
    """Parsed ``.planning/project.yaml``."""

    id: str = "unnamed-project"
    name: str = "Unnamed Project"
    current_focus: str | None = None
    authority: AuthorityConfig = field(default_factory=AuthorityConfig)
    output_directory: str = ".planning/dist"
    ui: UIConfig = field(default_factory=UIConfig)
    unknown_keys: list[str] = field(default_factory=list)


@dataclass
class Project:
    """A loaded planning project: configuration plus the full node set."""

    #: Repository root (the directory that contains ``.planning``).
    root: Path
    config: ProjectConfig = field(default_factory=ProjectConfig)
    #: All nodes keyed by node id. Insertion order follows load order;
    #: consumers that need determinism should sort by id.
    nodes: dict[str, Node] = field(default_factory=dict)
    #: All ideas keyed by idea id (spec §51). Insertion order follows load
    #: order; consumers that need determinism should sort by id.
    ideas: dict[str, Idea] = field(default_factory=dict)
    #: Schema-level problems collected during loading (already fatal enough
    #: to matter, but not fatal enough to abort the load).
    load_issues: list[ValidationIssue] = field(default_factory=list)

    def planning_dir(self) -> Path:
        return self.root / PLANNING_DIR

    def output_dir(self) -> Path:
        out = Path(self.config.output_directory)
        return out if out.is_absolute() else self.root / out

    def sorted_node_ids(self) -> list[str]:
        return sorted(self.nodes)

    def counts_by_status(self) -> dict[str, int]:
        """Progress counts used by ``pcp status`` and the dashboard.

        This is planning-node progress only. It says nothing about product
        or engineering completion (spec §24).
        """
        counts = {"total": 0, "done": 0, "active": 0, "blocked": 0, "pending": 0, "deferred": 0}
        for node in self.nodes.values():
            counts["total"] += 1
            if node.status == NodeStatus.DONE.value:
                counts["done"] += 1
            elif node.status == NodeStatus.BLOCKED.value:
                counts["blocked"] += 1
            elif node.status == NodeStatus.DEFERRED.value:
                counts["deferred"] += 1
            elif node.status == NodeStatus.NOT_STARTED.value:
                counts["pending"] += 1
            elif node.status in ACTIVE_STATUSES:
                counts["active"] += 1
        return counts
