"""Graph operations over the planning node set (spec §7).

The planning graph is a set of nodes plus typed edges: ``parent`` (single,
tree-forming) and ``depends_on`` / ``blocks`` / ``related_to`` / ``supersedes``
(cross links). The UI may render a tree, but this module — and validation —
treats the data as a general graph, with explicit cycle detection for both
the parent chain and dependency edges.
"""

from __future__ import annotations

from planning_control_plane.model import Node, NodeStatus, Project


class PlanningGraph:
    """Read-only graph view over a loaded :class:`Project`."""

    def __init__(self, project: Project):
        self.project = project
        self.nodes = project.nodes
        self._children: dict[str, list[str]] = {}
        for node_id in sorted(self.nodes):
            self._children[node_id] = []
        for node_id, node in self.nodes.items():
            parent = node.parent
            if parent is not None and parent in self._children:
                self._children[parent].append(node_id)
        for child_ids in self._children.values():
            child_ids.sort()

    # ------------------------------------------------------------------ tree

    @property
    def roots(self) -> list[str]:
        """Root nodes (no parent, or parent not in the node set), sorted."""
        return [
            node_id
            for node_id, node in sorted(self.nodes.items())
            if node.parent is None or node.parent not in self.nodes
        ]

    def children(self, node_id: str) -> list[str]:
        """Sorted child ids of *node_id* (empty when unknown)."""
        return list(self._children.get(node_id, ()))

    def ancestors(self, node_id: str) -> list[str]:
        """Ancestor ids ordered nearest parent first (spec §14).

        Parent-chain cycles are guarded: once a node repeats, the walk stops.
        Cycle reporting itself is :meth:`find_parent_cycles`.
        """
        result: list[str] = []
        seen = {node_id}
        current = self.nodes.get(node_id)
        while current is not None and current.parent is not None:
            parent_id = current.parent
            if parent_id in seen or parent_id not in self.nodes:
                break
            result.append(parent_id)
            seen.add(parent_id)
            current = self.nodes[parent_id]
        return result

    def descendants(self, node_id: str) -> list[str]:
        """All transitive child ids, depth-first, deterministic order."""
        result: list[str] = []
        seen: set[str] = set()

        def walk(nid: str) -> None:
            for child in self.children(nid):
                if child in seen:
                    continue
                seen.add(child)
                result.append(child)
                walk(child)

        walk(node_id)
        return result

    def parent_path(self, node_id: str) -> list[str]:
        """Root-first breadcrumb path including *node_id* itself."""
        return list(reversed(self.ancestors(node_id))) + [node_id]

    def find_parent_cycles(self) -> list[list[str]]:
        """Detect cycles in parent links. Returns each cycle as a node-id
        path where the first element repeats at the end, e.g.
        ``[A, B, C, A]``.
        """
        cycles: list[list[str]] = []
        reported: set[str] = set()
        for start in sorted(self.nodes):
            if start in reported:
                continue
            path: list[str] = []
            index: dict[str, int] = {}
            current: str | None = start
            while current is not None and current in self.nodes and current not in index:
                index[current] = len(path)
                path.append(current)
                current = self.nodes[current].parent
            if current is not None and current in index:
                cycle = path[index[current]:] + [current]
                if not set(cycle) & reported:
                    cycles.append(cycle)
                reported.update(cycle)
        return cycles

    # ---------------------------------------------------------- cross edges

    def find_dependency_cycles(self) -> list[list[str]]:
        """Detect cycles over ``depends_on`` edges (iterative DFS, colors)."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {node_id: WHITE for node_id in self.nodes}
        cycles: list[list[str]] = []
        stack: dict[str, list[str]] = {}

        for start in sorted(self.nodes):
            if color[start] != WHITE:
                continue
            color[start] = GRAY
            stack[start] = list(self.nodes[start].depends_on)
            walk = [start]
            while walk:
                node_id = walk[-1]
                pending = stack[node_id]
                advanced = False
                while pending:
                    target = pending.pop(0)
                    if target not in self.nodes:
                        continue  # missing target is a validation issue, not a cycle
                    if color[target] == GRAY:
                        cycle = walk[walk.index(target):] + [target]
                        cycles.append(cycle)
                    elif color[target] == WHITE:
                        color[target] = GRAY
                        stack[target] = list(self.nodes[target].depends_on)
                        walk.append(target)
                        advanced = True
                        break
                if not advanced:
                    color[node_id] = BLACK
                    walk.pop()
        return cycles

    def dependency_state(self, node: Node) -> dict[str, list[str]]:
        """Classify *node*'s ``depends_on`` targets."""
        missing: list[str] = []
        deferred: list[str] = []
        pending: list[str] = []
        for target in node.depends_on:
            target_node = self.nodes.get(target)
            if target_node is None:
                missing.append(target)
            elif target_node.status == NodeStatus.DEFERRED.value:
                deferred.append(target)
            elif target_node.status != NodeStatus.DONE.value:
                pending.append(target)
        return {"missing": sorted(missing), "deferred": sorted(deferred), "pending": sorted(pending)}

    def is_ready(self, node: Node) -> bool:
        """True when a NOT_STARTED node has every dependency DONE (spec §24,
        "Next Queue": dependency satisfied but not yet started)."""
        if node.status != NodeStatus.NOT_STARTED.value:
            return False
        state = self.dependency_state(node)
        return not (state["missing"] or state["deferred"] or state["pending"])

    def ready_queue(self) -> list[str]:
        return [nid for nid in sorted(self.nodes) if self.is_ready(self.nodes[nid])]

    def blocked_by(self, node: Node) -> list[str]:
        """Ids of dependencies that are not DONE (missing/deferred/pending)."""
        state = self.dependency_state(node)
        return sorted({*state["missing"], *state["deferred"], *state["pending"]})

    def related_nodes(self, node_id: str) -> list[str]:
        """``related_to`` targets plus nodes pointing back at *node_id*."""
        related = set(self.nodes[node_id].related_to)
        for other_id, other in self.nodes.items():
            if node_id in other.related_to:
                related.add(other_id)
        return sorted(related & set(self.nodes))

    def superseding_nodes(self, node_id: str) -> list[str]:
        """Nodes whose ``supersedes`` list contains *node_id*."""
        return sorted(
            other_id for other_id, other in self.nodes.items() if node_id in other.supersedes and other_id != node_id
        )

    # ------------------------------------------------------------- ordering

    def topological_order(self) -> list[str]:
        """Deterministic order where children follow parents (Kahn).

        Nodes involved in parent cycles are appended in id order at the end
        so the result always contains every node exactly once.
        """
        ordered: list[str] = []
        emitted: set[str] = set()
        pending = set(self.nodes)

        def available() -> list[str]:
            return sorted(
                nid
                for nid in pending
                if self.nodes[nid].parent is None
                or self.nodes[nid].parent not in self.nodes
                or self.nodes[nid].parent in emitted
            )

        while pending:
            ready = available()
            if not ready:  # parent cycle: emit the rest deterministically
                ordered.extend(sorted(pending))
                break
            for nid in ready:
                ordered.append(nid)
                emitted.add(nid)
                pending.discard(nid)
        return ordered

    def subtree_ids(self, node_id: str) -> list[str]:
        """*node_id* plus all descendants, in topological-then-id order."""
        desc = set(self.descendants(node_id))
        desc.add(node_id)
        return [nid for nid in self.topological_order() if nid in desc]
