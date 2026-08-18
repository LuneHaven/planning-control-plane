"""Deterministic static HTML generation (spec §22–§30).

``build_site`` renders a loaded :class:`~planning_control_plane.model.Project`
into a fresh output directory (delete-and-rebuild); ``check_build`` re-renders
into a temporary directory and compares the result byte-for-byte with an
existing dist tree for CI drift detection (spec §23).

Rules this module commits to:

* **Deterministic** — every collection is sorted before it reaches a
  template; no timestamps, no randomness. Building the same project twice
  produces byte-identical files.
* **Defensive** — dangling references in planning data (missing dependency
  targets, an unknown ``current_focus``, parent cycles) render as plain text
  without links instead of raising. Whether such data is *valid* is the
  validator's decision; the generator only projects it (spec §37).
* **Offline** — pages reference only sibling files, so the site works when
  ``index.html`` is opened directly over ``file://``.

The planning tree rendered in the sidebar and on the dashboard always
contains every node exactly once: nodes unreachable from a root (parent
cycles, orphans) are re-attached as extra roots instead of disappearing or
looping forever.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from planning_control_plane.graph import PlanningGraph
from planning_control_plane.model import (
    NODE_ID_RE,
    Decision,
    PCPError,
    Project,
    TrackStatus,
    NodeType,
)

__all__ = ["build_site", "check_build"]

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = _TEMPLATES_DIR / "static"

#: Static assets copied verbatim into ``<out>/assets/`` (sorted, so the
#: write order is deterministic too).
_STATIC_FILES = ("app.js", "style.css")

#: Characters that may never appear in a generated file name.
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")

#: How many nodes the dashboard "Recently Updated" panel shows.
_RECENT_LIMIT = 5


# --------------------------------------------------------------------------
# low-level helpers
# --------------------------------------------------------------------------


def _make_env() -> Environment:
    """Jinja2 environment over the packaged templates."""
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _write_text(path: Path, text: str) -> Path:
    """Write *text* as UTF-8 with LF newlines (platform independent)."""
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def _safe_stem(node_id: str) -> str:
    """File name stem for a node page.

    Ids matching :data:`NODE_ID_RE` are used verbatim; anything else (the
    loader keeps such ids so ``pcp validate`` can report them) has every
    unsafe character replaced with ``_``. The result can never contain a
    path separator, so generation stays inside ``nodes/``.
    """
    if NODE_ID_RE.match(node_id):
        return node_id
    return _UNSAFE_FILENAME_CHARS.sub("_", node_id)


def _safe_id_map(project: Project) -> dict[str, str]:
    """Map every node id to its page file stem (spec §22 ``nodes/<id>.html``).

    Sanitized stems can collide (``A B`` and ``A_B``); colliding pages would
    silently overwrite each other, so collisions get a ``-2``/``-3``/...
    suffix. Iteration is over sorted ids, keeping the map deterministic.
    """
    mapping: dict[str, str] = {}
    taken: set[str] = set()
    for node_id in project.sorted_node_ids():
        base = _safe_stem(node_id)
        stem = base
        counter = 2
        while stem in taken:
            stem = f"{base}-{counter}"
            counter += 1
        taken.add(stem)
        mapping[node_id] = stem
    return mapping


def _decision_view(decision: Decision) -> dict:
    return {"id": decision.id, "summary": decision.summary, "source": decision.source or ""}


def _node_ref(project: Project, node_id: str, safe: dict[str, str], prefix: str) -> dict:
    """Template-facing reference to a node; *prefix* is ``""`` on the
    dashboard and ``"../"`` on node pages.

    Unknown ids (dangling ``depends_on`` targets etc.) are kept as plain
    text with ``known=False`` — the generator never fabricates a link to a
    page it did not generate.
    """
    node = project.nodes.get(node_id)
    if node is None:
        return {"id": node_id, "known": False, "title": "", "status": "", "url": ""}
    return {
        "id": node_id,
        "known": True,
        "title": node.title,
        "status": node.status,
        "url": f"{prefix}nodes/{safe[node_id]}.html",
    }


def _sorted_refs(project: Project, node_ids: list[str], safe: dict[str, str], prefix: str) -> list[dict]:
    """Node references sorted by id (missing targets included, sorted in)."""
    refs = [_node_ref(project, node_id, safe, prefix) for node_id in node_ids]
    return sorted(refs, key=lambda ref: ref["id"])


def _source_views(project: Project, paths: list[str]) -> list[dict]:
    """Classify repository-relative source paths via the authority config.

    The label is one of ``canonical`` / ``current-state`` / ``planning`` or
    empty when no configured root matches (spec §6: PCP never assumes the
    roots exist, it only labels what is configured).
    """
    return [
        {"path": path, "label": project.config.authority.classify(path)}
        for path in paths
    ]


def _track_display(value: str) -> str:
    """Terminal-style track status (``NOT_APPLICABLE`` renders as ``N/A``).

    Imported lazily and degraded gracefully so that rendering never depends
    on import order between sibling modules.
    """
    try:
        from planning_control_plane import context

        return context.track_display(value)
    except Exception:  # noqa: BLE001 - display fallback only
        return "N/A" if value == TrackStatus.NOT_APPLICABLE.value else value


def _capsule_text(project: Project, node_id: str) -> str:
    """Session resume capsule shown on node pages (spec §27).

    The capsule must match ``pcp context <node-id>`` output, so it is always
    produced by the context module. Any failure degrades to an explicit
    note in the page instead of aborting the whole build.
    """
    try:
        from planning_control_plane import context

        return context.render_capsule(context.build_capsule(project, node_id))
    except Exception as exc:  # noqa: BLE001 - rendering must not crash the build
        return f"(context capsule unavailable: {type(exc).__name__}: {exc})"


# --------------------------------------------------------------------------
# planning tree
# --------------------------------------------------------------------------


def _build_forest(
    graph: PlanningGraph,
    seeds: list[str],
    claimed: set[str],
    focus_id: str | None,
    current_page_id: str | None,
    safe: dict[str, str],
) -> list[dict]:
    """Turn *seeds* into a nested list of tree view items, iteratively.

    Every node visited here is added to *claimed*; nodes already claimed are
    skipped, which terminates parent cycles and guarantees each node appears
    at most once per page. Children stay in sorted order (nearest-first
    siblings), matching the deterministic-output rule.
    """
    stack: list[tuple[str, str]] = [(seed, "") for seed in reversed(seeds)]
    owner: dict[str, str] = {}  # node id -> id of the item that claims it ("" = root)
    pre_order: list[str] = []

    while stack:
        node_id, pushed_by = stack.pop()
        if node_id in claimed or node_id not in graph.nodes:
            continue
        claimed.add(node_id)
        owner[node_id] = pushed_by
        pre_order.append(node_id)
        for child in reversed(graph.children(node_id)):
            stack.append((child, node_id))

    children_of: dict[str, list[str]] = {node_id: [] for node_id in pre_order}
    for node_id in pre_order:
        pushed_by = owner[node_id]
        if pushed_by:
            children_of[pushed_by].append(node_id)

    items: dict[str, dict] = {}
    for node_id in reversed(pre_order):  # children before parents
        node = graph.nodes[node_id]
        items[node_id] = {
            "id": node_id,
            "title": node.title or node_id,
            "status": node.status,
            "file": f"{safe[node_id]}.html",
            "is_focus": focus_id is not None and node_id == focus_id,
            "is_current": current_page_id is not None and node_id == current_page_id,
            "children": [items[child] for child in children_of[node_id]],
        }
    return [items[node_id] for node_id in pre_order if not owner[node_id]]


def _planning_tree(
    graph: PlanningGraph,
    focus_id: str | None,
    current_page_id: str | None,
    safe: dict[str, str],
) -> list[dict]:
    """Whole-tree view items: roots first, then any node a parent cycle or
    orphaned subtree kept unreachable from a root."""
    claimed: set[str] = set()
    forest = _build_forest(graph, graph.roots, claimed, focus_id, current_page_id, safe)
    leftovers = [node_id for node_id in sorted(graph.nodes) if node_id not in claimed]
    if leftovers:
        forest.extend(_build_forest(graph, leftovers, claimed, focus_id, current_page_id, safe))
    return forest


# --------------------------------------------------------------------------
# view models
# --------------------------------------------------------------------------


def _base_context(
    project: Project,
    graph: PlanningGraph,
    safe: dict[str, str],
    current_page_id: str | None,
    prefix: str,
) -> dict:
    """Context every page shares: project name, relative link bases and the
    sidebar planning tree (with the current focus highlighted)."""
    return {
        "project_name": project.config.name or project.config.id,
        "focus_id": project.config.current_focus,
        "tree": _planning_tree(graph, project.config.current_focus, current_page_id, safe),
        "base": {
            "index": f"{prefix}index.html",
            "nodes": f"{prefix}nodes/",
            "assets": f"{prefix}assets/",
        },
    }


def _focus_view(project: Project, graph: PlanningGraph, safe: dict[str, str]) -> dict:
    """Dashboard "Current Focus" panel data (spec §24)."""
    focus_id = project.config.current_focus
    if not focus_id:
        return {"set": False, "missing": False}
    node = project.nodes.get(focus_id)
    if node is None:
        return {"set": True, "missing": True, "id": focus_id}

    ancestors = graph.ancestors(focus_id)  # nearest parent first
    phase_id = next(
        (ancestor for ancestor in ancestors if project.nodes[ancestor].type == NodeType.PHASE.value),
        None,
    )
    if phase_id is None and ancestors:
        phase_id = ancestors[-1]  # fall back to the topmost ancestor

    return {
        "set": True,
        "missing": False,
        "id": node.id,
        "title": node.title,
        "status": node.status,
        "url": f"nodes/{safe[node.id]}.html",
        "phase": _node_ref(project, phase_id, safe, "") if phase_id is not None else None,
        "next_action": node.next_action,
        "blocked_by": [
            _node_ref(project, dep_id, safe, "") for dep_id in graph.blocked_by(node)
        ],
        "blocking_decisions": [_decision_view(d) for d in node.blocking_decisions],
    }


def _progress_view(project: Project) -> dict:
    counts = project.counts_by_status()
    return {
        "total": counts["total"],
        "done": counts["done"],
        "active": counts["active"],
        "blocked": counts["blocked"],
        "pending": counts["pending"],
        "deferred": counts["deferred"],
    }


def _blocking_rows(project: Project, safe: dict[str, str]) -> list[dict]:
    """All blocking decisions across the graph, grouped by owning node."""
    rows: list[dict] = []
    for node_id in project.sorted_node_ids():
        node = project.nodes[node_id]
        if not node.blocking_decisions:
            continue
        rows.append(
            {
                "node": _node_ref(project, node_id, safe, ""),
                "decisions": [_decision_view(d) for d in node.blocking_decisions],
            }
        )
    return rows


def _recently_updated(project: Project, safe: dict[str, str], limit: int) -> list[dict]:
    """Newest ``last_updated`` first; same date by id ascending; undated last."""
    dated = [node for node in project.nodes.values() if node.last_updated]
    undated = [node for node in project.nodes.values() if not node.last_updated]
    dated.sort(key=lambda node: node.id)
    dated.sort(key=lambda node: node.last_updated, reverse=True)  # stable: id asc within a date
    undated.sort(key=lambda node: node.id)
    ordered = dated + undated
    return [
        {"node": _node_ref(project, node.id, safe, ""), "date": node.last_updated}
        for node in ordered[:limit]
    ]


def _index_context(project: Project, graph: PlanningGraph, safe: dict[str, str]) -> dict:
    view = _base_context(project, graph, safe, current_page_id=None, prefix="")
    view.update(
        focus=_focus_view(project, graph, safe),
        progress=_progress_view(project),
        blocking_rows=_blocking_rows(project, safe),
        recently_updated=_recently_updated(project, safe, _RECENT_LIMIT),
        next_queue=[_node_ref(project, node_id, safe, "") for node_id in graph.ready_queue()],
    )
    return view


def _node_context(
    project: Project,
    graph: PlanningGraph,
    node_id: str,
    safe: dict[str, str],
) -> dict:
    node = project.nodes[node_id]
    prefix = "../"
    view = _base_context(project, graph, safe, current_page_id=node_id, prefix=prefix)

    breadcrumb: list[dict] = []
    for crumb_id in graph.parent_path(node_id):  # root-first, self last
        crumb = _node_ref(project, crumb_id, safe, prefix)
        crumb["current"] = crumb_id == node_id
        breadcrumb.append(crumb)

    # Inherited frozen decisions, grouped nearest ancestor first and
    # deduplicated by decision id so repeated inheritance cannot bloat the
    # page (spec §14). Ids the node declares itself are shadowed — they
    # belong to the "Frozen Decisions" section — matching the capsule.
    inherited: list[dict] = []
    seen_decision_ids: set[str] = {decision.id for decision in node.frozen_decisions}
    for ancestor_id in graph.ancestors(node_id):
        decisions = []
        for decision in project.nodes[ancestor_id].frozen_decisions:
            if decision.id in seen_decision_ids:
                continue
            seen_decision_ids.add(decision.id)
            decisions.append(_decision_view(decision))
        if decisions:
            inherited.append(
                {
                    "ancestor": _node_ref(project, ancestor_id, safe, prefix),
                    "decisions": decisions,
                }
            )

    view.update(
        node={
            "id": node.id,
            "title": node.title,
            "type": node.type,
            "status": node.status,
            "objective": node.objective,
            "next_action": node.next_action,
            "last_updated": node.last_updated,
            "scope": list(node.scope),
            "out_of_scope": list(node.out_of_scope),
            "frozen_decisions": [_decision_view(d) for d in node.frozen_decisions],
            "open_decisions": [_decision_view(d) for d in node.open_decisions],
            "blocking_decisions": [_decision_view(d) for d in node.blocking_decisions],
            "deferred_decisions": [_decision_view(d) for d in node.deferred_decisions],
            "canonical_sources": _source_views(project, node.canonical_sources),
            "evidence_sources": _source_views(project, node.evidence_sources),
        },
        breadcrumb=breadcrumb,
        inherited_frozen=inherited,
        dependencies=_sorted_refs(project, node.depends_on, safe, prefix),
        blocks=_sorted_refs(project, node.blocks, safe, prefix),
        related=[_node_ref(project, rel, safe, prefix) for rel in graph.related_nodes(node_id)],
        supersedes=_sorted_refs(project, node.supersedes, safe, prefix),
        superseded_by=[
            _node_ref(project, sup, safe, prefix) for sup in graph.superseding_nodes(node_id)
        ],
        tracks={
            "discussion": _track_display(node.discussion_status),
            "writeback": _track_display(node.writeback_status),
            "implementation": _track_display(node.implementation_status),
        },
        capsule=_capsule_text(project, node_id),
    )
    return view


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------


def _ensure_safe_output_dir(project: Project, out_dir: Path) -> None:
    """Refuse to build into a directory that holds the planning data.

    Defense in depth behind the validator's ``unsafe-output-directory``
    rule: ``build_site`` deletes *out_dir* before rebuilding, so an output
    directory equal to or containing ``.planning`` (including the
    repository root) would destroy the planning source. The generator
    never performs that deletion, regardless of how it was called.
    """
    resolved = out_dir.resolve()
    planning_dir = project.planning_dir().resolve()
    if resolved == planning_dir or planning_dir.is_relative_to(resolved):
        raise PCPError(
            f"refusing to build into '{out_dir}': it contains the planning data "
            f"directory '{planning_dir}', which the rebuild would delete; "
            "fix output.directory in project.yaml"
        )


def build_site(project: Project, out_dir: Path) -> list[Path]:
    """Render the whole static site into *out_dir* (spec §22).

    An existing *out_dir* is removed first (delete-and-rebuild safe), then
    the site is regenerated deterministically: ``index.html``,
    ``assets/{app.js, style.css}`` (copied verbatim from the packaged
    templates) and one ``nodes/<safe-id>.html`` per node. Returns the
    written paths, sorted.

    Raises :class:`PCPError` when *out_dir* would destroy the planning
    data (see :func:`_ensure_safe_output_dir`).
    """
    out_dir = Path(out_dir)
    _ensure_safe_output_dir(project, out_dir)
    if out_dir.is_dir():
        shutil.rmtree(out_dir)
    elif out_dir.exists():
        out_dir.unlink()

    assets_dir = out_dir / "assets"
    nodes_dir = out_dir / "nodes"
    assets_dir.mkdir(parents=True)
    nodes_dir.mkdir()

    env = _make_env()
    graph = PlanningGraph(project)
    safe = _safe_id_map(project)
    written: list[Path] = []

    for name in _STATIC_FILES:
        target = assets_dir / name
        shutil.copy(_STATIC_DIR / name, target)
        written.append(target)

    written.append(
        _write_text(out_dir / "index.html", env.get_template("index.html").render(**_index_context(project, graph, safe)))
    )

    node_template = env.get_template("node.html")
    for node_id in project.sorted_node_ids():
        html = node_template.render(**_node_context(project, graph, node_id, safe))
        written.append(_write_text(nodes_dir / f"{safe[node_id]}.html", html))

    return sorted(written)


def _file_map(root: Path) -> dict[str, bytes]:
    """Every file under *root* as ``relative posix path -> bytes``."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def check_build(project: Project, dist_dir: Path) -> tuple[bool, list[str]]:
    """Regenerate the site in a temporary directory and compare it with
    *dist_dir* (spec §23, ``pcp build --check``).

    Returns ``(ok, messages)``; *messages* lists drift as ``missing:`` /
    ``changed:`` / ``extra:`` entries (sorted within each category). A
    missing dist directory yields the single message ``dist not found``.
    """
    dist_dir = Path(dist_dir)
    if not dist_dir.is_dir():
        return False, ["dist not found"]

    with tempfile.TemporaryDirectory(prefix="pcp-check-") as tmp:
        build_site(project, Path(tmp))
        expected = _file_map(Path(tmp))
    actual = _file_map(dist_dir)

    messages: list[str] = []
    for rel in sorted(set(expected) - set(actual)):
        messages.append(f"missing: {rel}")
    for rel in sorted(set(expected) & set(actual)):
        if expected[rel] != actual[rel]:
            messages.append(f"changed: {rel}")
    for rel in sorted(set(actual) - set(expected)):
        messages.append(f"extra: {rel}")
    return not messages, messages
