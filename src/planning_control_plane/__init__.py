"""Planning Control Plane (PCP).

A repository-native planning context and progress control tool. PCP turns a
long-running planning process into a persistent planning graph, keeps parent
constraints and frozen decisions visible in child work, and produces a
disposable, reproducible static HTML projection of planning progress.
"""

from planning_control_plane.model import (
    AuthorityConfig,
    Decision,
    Node,
    NodeStatus,
    NodeType,
    PCPError,
    Project,
    ProjectConfig,
    Severity,
    TrackStatus,
    ValidationIssue,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "AuthorityConfig",
    "Decision",
    "Node",
    "NodeStatus",
    "NodeType",
    "PCPError",
    "Project",
    "ProjectConfig",
    "Severity",
    "TrackStatus",
    "ValidationIssue",
]
