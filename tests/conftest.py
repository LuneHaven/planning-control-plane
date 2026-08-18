"""Shared fixtures and project-building helpers for the PCP test suite.

* :func:`make_project` materializes a synthetic ``.planning`` tree under a
  temporary repository root and returns the project as loaded by the real
  loader (so every test exercises the on-disk contract, not in-memory data).
* :func:`demo_root` exposes the read-only demo target repository shipped in
  ``examples/demo-project``; tests must never write into it.
* :func:`demo_zh_root` does the same for the Chinese demo repository in
  ``examples/demo-project-zh`` (the one the Chinese screenshots use).
* :func:`demo_copy` provides a writable copy of the demo repository for
  commands that write (``build``, ``focus``).
* :func:`cli` runs ``planning_control_plane.cli.main`` in-process and returns
  ``(exit_code, stdout, stderr)`` — no subprocess, no PATH dependency.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable

import pytest
import yaml

from planning_control_plane import cli as cli_module
from planning_control_plane.loader import load_project
from planning_control_plane.model import Project, ValidationIssue

#: Repository root of the PCP tool itself.
REPO_ROOT = Path(__file__).resolve().parent.parent

#: Read-only demo target repository shipped with the tool.
DEMO_PROJECT_ROOT = REPO_ROOT / "examples" / "demo-project"

#: Read-only Chinese demo target repository. Separate planning data, not a
#: translation: PCP localizes its UI, never the planning content.
DEMO_ZH_PROJECT_ROOT = REPO_ROOT / "examples" / "demo-project-zh"

#: Minimal valid ``project.yaml`` content used when a test provides none.
DEFAULT_CONFIG: dict[str, Any] = {
    "project": {"id": "test-project", "name": "Test Project"},
    "planning": {"current_focus": None},
}

#: Node ids of the demo project (spec §31 tree), in sorted order.
DEMO_NODE_IDS = ["P1", "P2", "P2-A", "P2-A1", "P2-A2", "P2-A3", "P2-A4"]


def write_planning(
    root: Path,
    config_dict: dict[str, Any] | None = None,
    node_dicts: list | None = None,
    roadmap_nodes: list | None = None,
    raw_files: dict[str, str] | None = None,
    repo_files: dict[str, str] | None = None,
) -> Path:
    """Write a ``.planning`` tree (and optional repo files) under *root*.

    ``node_dicts`` entries are either a node mapping (written to
    ``nodes/<id>.yaml``) or a ``(filename, body)`` tuple where *body* may be a
    mapping or raw YAML text. ``raw_files`` maps paths relative to
    ``.planning`` to raw file content (written last, so they can override the
    generated ``project.yaml`` / node files). ``repo_files`` maps
    repository-relative paths to content, for canonical/evidence targets.
    """
    planning = root / ".planning"
    (planning / "nodes").mkdir(parents=True, exist_ok=True)

    config = DEFAULT_CONFIG if config_dict is None else config_dict
    (planning / "project.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    (planning / "roadmap.yaml").write_text(
        yaml.safe_dump({"nodes": list(roadmap_nodes or [])}, sort_keys=False), encoding="utf-8"
    )

    for index, entry in enumerate(node_dicts or []):
        if isinstance(entry, tuple):
            filename, body = entry
        else:
            body = entry
            filename = f"{body.get('id', f'node-{index}')}.yaml"
        text = body if isinstance(body, str) else yaml.safe_dump(body, sort_keys=False)
        (planning / "nodes" / filename).write_text(text, encoding="utf-8")

    for rel, text in (raw_files or {}).items():
        target = planning / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    for rel, text in (repo_files or {}).items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    return planning


@pytest.fixture
def make_project() -> Callable[..., tuple[Project, Path]]:
    """Build a synthetic project on disk and load it through the real loader.

    Returns ``(project, repo_root)``.
    """

    def _make(
        tmp_path: Path,
        config_dict: dict[str, Any] | None = None,
        node_dicts: list | None = None,
        roadmap_nodes: list | None = None,
        raw_files: dict[str, str] | None = None,
        repo_files: dict[str, str] | None = None,
    ) -> tuple[Project, Path]:
        root = Path(tmp_path) / "repo"
        root.mkdir(exist_ok=True)
        write_planning(root, config_dict, node_dicts, roadmap_nodes, raw_files, repo_files)
        return load_project(root), root

    return _make


@pytest.fixture
def node_dict() -> Callable[..., dict[str, Any]]:
    """Build a minimal valid node mapping, plus any keyword overrides."""

    def _node(node_id: str, title: str | None = None, **overrides: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "id": node_id,
            "title": title if title is not None else node_id,
            "type": "DISCUSSION",
            "status": "NOT_STARTED",
        }
        base.update(overrides)
        return base

    return _node


@pytest.fixture
def by_rule() -> Callable[..., list[ValidationIssue]]:
    """Filter a validation issue list down to one rule name."""

    def _by_rule(issues: list[ValidationIssue], rule: str) -> list[ValidationIssue]:
        return [issue for issue in issues if issue.rule == rule]

    return _by_rule


@pytest.fixture
def demo_root() -> Path:
    """Read-only demo target repository; tests must not write into it."""
    return DEMO_PROJECT_ROOT


@pytest.fixture
def demo_zh_root() -> Path:
    """Read-only Chinese demo target repository; tests must not write into it."""
    return DEMO_ZH_PROJECT_ROOT


@pytest.fixture
def demo_copy(tmp_path: Path) -> Path:
    """Writable copy of the demo repository, for commands that write."""
    destination = tmp_path / "demo-project"
    shutil.copytree(DEMO_PROJECT_ROOT, destination)
    return destination


@pytest.fixture
def cli(capsys) -> Callable[..., tuple[int, str, str]]:
    """Run ``pcp`` in-process; returns ``(exit_code, stdout, stderr)``."""

    def _run(*argv: str) -> tuple[int, str, str]:
        code = cli_module.main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run
