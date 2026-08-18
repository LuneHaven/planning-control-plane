"""Load a ``.planning`` directory into a :class:`Project`.

Loading is deliberately tolerant: structural problems (invalid enum values,
malformed decision entries, unknown keys) are recorded as
:class:`ValidationIssue` objects on the project instead of raising, so that
``pcp validate`` can report every problem in one pass. Only conditions that
make loading meaningless (missing ``.planning``, unreadable YAML, missing
``project.yaml``) raise :class:`LoadError`.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from planning_control_plane.model import (
    NODE_ID_RE,
    PLANNING_DIR,
    PCPError,
    Decision,
    Node,
    Project,
    ProjectConfig,
    AuthorityConfig,
    Severity,
    TrackStatus,
    TRACK_STATUS_ALIASES,
    ValidationIssue,
)

PROJECT_FILE = "project.yaml"
ROADMAP_FILE = "roadmap.yaml"
NODES_DIR = "nodes"

#: Keys of the node schema (spec §8).
NODE_FIELDS = frozenset(
    {
        "id",
        "title",
        "type",
        "parent",
        "status",
        "objective",
        "scope",
        "out_of_scope",
        "frozen_decisions",
        "open_decisions",
        "blocking_decisions",
        "deferred_decisions",
        "depends_on",
        "blocks",
        "related_to",
        "supersedes",
        "canonical_sources",
        "evidence_sources",
        "next_action",
        "discussion_status",
        "writeback_status",
        "implementation_status",
        "last_updated",
    }
)

_DECISION_LISTS = (
    "frozen_decisions",
    "open_decisions",
    "blocking_decisions",
    "deferred_decisions",
)

_STRING_LISTS = (
    "scope",
    "out_of_scope",
    "depends_on",
    "blocks",
    "related_to",
    "supersedes",
    "canonical_sources",
    "evidence_sources",
)


class LoadError(PCPError):
    """Raised when a planning directory cannot be loaded at all."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader variant that refuses duplicate mapping keys.

    ``yaml.safe_load`` silently collapses duplicate keys (last one wins),
    which can hide planning data — e.g. two ``nodes:`` blocks in
    roadmap.yaml would quietly drop the first block's nodes. Duplicate
    keys make a YAML file ambiguous, so loading fails loudly instead.
    """


def _construct_mapping_without_duplicates(loader, node, deep=False):
    keys = []
    try:
        for key_node, _value_node in node.value:
            keys.append(loader.construct_object(key_node, deep=deep))
        if len(keys) != len(set(keys)):
            seen: list = []
            duplicates: list = []
            for key in keys:
                if key in seen and key not in duplicates:
                    duplicates.append(key)
                seen.append(key)
            raise yaml.YAMLError(
                f"duplicate YAML key(s) near line {node.start_mark.line + 1}: "
                + ", ".join(str(key) for key in duplicates)
            )
    except TypeError:  # unhashable keys (exotic YAML) — skip the check
        pass
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping_without_duplicates
)


def find_planning_dir(start: Path) -> Path:
    """Locate ``.planning`` starting at *start*, walking up to the filesystem
    root (mirrors how git finds ``.git``). Raises :class:`LoadError` when not
    found — with a hint to run ``pcp init``.
    """
    start = Path(start).resolve()
    for candidate in (start, *start.parents):
        planning = candidate / PLANNING_DIR
        if planning.is_dir():
            return planning
    raise LoadError(
        f"no '{PLANNING_DIR}' directory found in '{start}' or any parent; "
        "run 'pcp init' in the target repository first"
    )


def find_project_root(start: Path) -> Path:
    """Repository root = parent of the located ``.planning`` directory."""
    return find_planning_dir(start).parent


def _read_yaml(path: Path) -> object:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return yaml.load(handle, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise LoadError(f"invalid YAML in {path}: {exc}") from exc
    except OSError as exc:
        raise LoadError(f"cannot read {path}: {exc}") from exc


def _issue(severity: Severity, rule: str, message: str, node_id: str | None = None):
    return ValidationIssue(severity=severity, rule=rule, message=message, node_id=node_id)


def _as_string_list(value, node_id: str, key: str, issues: list) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append(
            _issue(Severity.ERROR, "invalid-field", f"'{key}' must be a list, got {type(value).__name__}", node_id)
        )
        return []
    result = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item)
        else:
            issues.append(
                _issue(Severity.ERROR, "invalid-field", f"'{key}' entries must be non-empty strings", node_id)
            )
    return result


def _as_decisions(value, node_id: str, key: str, issues: list) -> list[Decision]:
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append(
            _issue(Severity.ERROR, "invalid-field", f"'{key}' must be a list, got {type(value).__name__}", node_id)
        )
        return []
    result = []
    for item in value:
        if not isinstance(item, dict):
            issues.append(
                _issue(Severity.ERROR, "invalid-decision", f"'{key}' entries must be mappings with id and summary", node_id)
            )
            continue
        dec_id = item.get("id")
        summary = item.get("summary")
        source = item.get("source")
        if not isinstance(dec_id, str) or not dec_id.strip():
            issues.append(
                _issue(Severity.ERROR, "invalid-decision", f"'{key}' entry is missing a non-empty 'id'", node_id)
            )
            continue
        if not isinstance(summary, str) or not summary.strip():
            issues.append(
                _issue(Severity.ERROR, "invalid-decision", f"decision '{dec_id}' in '{key}' is missing a non-empty 'summary'", node_id)
            )
            continue
        if source is not None and not isinstance(source, str):
            issues.append(
                _issue(Severity.WARNING, "invalid-decision", f"decision '{dec_id}' has a non-string 'source'; ignored", node_id)
            )
            source = None
        result.append(Decision(id=dec_id.strip(), summary=summary.strip(), source=(source or None) or None))
    return result


def _as_track(value, node_id: str, key: str, issues: list) -> str:
    """Parse a track status, accepting ``N/A`` spellings (spec §11)."""
    if value is None:
        return TrackStatus.NOT_STARTED.value
    if not isinstance(value, str):
        issues.append(
            _issue(Severity.ERROR, "invalid-track-status", f"'{key}' must be a string, got {type(value).__name__}", node_id)
        )
        return TrackStatus.NOT_STARTED.value
    stripped = value.strip()
    if stripped.upper() in TRACK_STATUS_ALIASES:
        return TRACK_STATUS_ALIASES[stripped.upper()]
    return stripped  # membership checked by the validator


def _as_text(value) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        return str(value)
    return value.strip()


def parse_node(data: object, source_file: str | None, issues: list) -> Node | None:
    """Parse one node mapping. Returns ``None`` when the entry is unusable
    (not a mapping, or missing/empty ``id``). Softer problems become issues.
    """
    if not isinstance(data, dict):
        issues.append(_issue(Severity.ERROR, "invalid-node", f"node entry in {source_file or 'roadmap.yaml'} is not a mapping"))
        return None
    node_id = data.get("id")
    if not isinstance(node_id, str) or not node_id.strip():
        issues.append(
            _issue(Severity.ERROR, "invalid-node", f"node entry in {source_file or 'roadmap.yaml'} is missing a non-empty 'id'")
        )
        return None
    node_id = node_id.strip()

    title = _as_text(data.get("title"))
    if not title:
        issues.append(_issue(Severity.ERROR, "missing-title", "node is missing a non-empty 'title'", node_id))
        title = node_id

    node = Node(id=node_id, title=title, source_file=source_file)
    # A present-but-empty value (e.g. `type: ""`) is kept verbatim so the
    # validator reports it as invalid; only an absent (or null) key falls
    # back to the schema default. Silently defaulting would hide typos.
    if data.get("type") is not None:
        node.type = _as_text(data.get("type"))
    if data.get("status") is not None:
        node.status = _as_text(data.get("status"))
    node.objective = _as_text(data.get("objective"))
    node.next_action = _as_text(data.get("next_action"))
    node.last_updated = _as_text(data.get("last_updated"))

    parent = data.get("parent")
    if parent is not None and isinstance(parent, str) and parent.strip():
        node.parent = parent.strip()
    elif parent is not None:
        issues.append(_issue(Severity.ERROR, "invalid-field", "'parent' must be a string or null", node_id))

    for key in _STRING_LISTS:
        node.__dict__[key] = _as_string_list(data.get(key), node_id, key, issues)
    for key in _DECISION_LISTS:
        node.__dict__[key] = _as_decisions(data.get(key), node_id, key, issues)

    node.discussion_status = _as_track(data.get("discussion_status"), node_id, "discussion_status", issues)
    node.writeback_status = _as_track(data.get("writeback_status"), node_id, "writeback_status", issues)
    node.implementation_status = _as_track(data.get("implementation_status"), node_id, "implementation_status", issues)

    node.unknown_fields = sorted(str(k) for k in data.keys() if k not in NODE_FIELDS)
    return node


def _parse_config(data: object, issues: list) -> ProjectConfig:
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise LoadError(f"{PROJECT_FILE}: top level must be a mapping")

    config = ProjectConfig()
    project = data.get("project")
    if project is None:
        issues.append(_issue(Severity.ERROR, "missing-project-section", f"{PROJECT_FILE}: missing 'project' section"))
    elif not isinstance(project, dict):
        issues.append(_issue(Severity.ERROR, "invalid-project-section", f"{PROJECT_FILE}: 'project' must be a mapping"))
    else:
        config.id = _as_text(project.get("id")) or config.id
        config.name = _as_text(project.get("name")) or config.name

    planning = data.get("planning")
    if planning is not None:
        if not isinstance(planning, dict):
            issues.append(_issue(Severity.ERROR, "invalid-planning-section", f"{PROJECT_FILE}: 'planning' must be a mapping"))
        else:
            focus = planning.get("current_focus")
            if focus is not None:
                if isinstance(focus, str) and focus.strip():
                    config.current_focus = focus.strip()
                else:
                    issues.append(
                        _issue(Severity.ERROR, "invalid-current-focus", f"{PROJECT_FILE}: 'current_focus' must be a non-empty string or null")
                    )

    authority = data.get("authority")
    if authority is not None:
        if not isinstance(authority, dict):
            issues.append(_issue(Severity.ERROR, "invalid-authority-section", f"{PROJECT_FILE}: 'authority' must be a mapping"))
        else:
            known = {"canonical_roots", "current_state_roots", "planning_roots"}
            config.authority = AuthorityConfig(
                canonical_roots=_as_string_list(authority.get("canonical_roots"), None, "authority.canonical_roots", issues),
                current_state_roots=_as_string_list(authority.get("current_state_roots"), None, "authority.current_state_roots", issues),
                planning_roots=_as_string_list(authority.get("planning_roots"), None, "authority.planning_roots", issues),
                unknown_keys=sorted(str(k) for k in authority.keys() if k not in known),
            )

    output = data.get("output")
    if output is not None:
        if not isinstance(output, dict):
            issues.append(_issue(Severity.ERROR, "invalid-output-section", f"{PROJECT_FILE}: 'output' must be a mapping"))
        else:
            directory = output.get("directory")
            if directory is not None:
                if isinstance(directory, str) and directory.strip():
                    config.output_directory = directory.strip()
                else:
                    issues.append(
                        _issue(Severity.ERROR, "invalid-output-directory", f"{PROJECT_FILE}: 'output.directory' must be a non-empty string")
                    )

    known_top = {"project", "planning", "authority", "output"}
    config.unknown_keys = sorted(str(k) for k in data.keys() if k not in known_top)
    return config


def load_project(root: Path) -> Project:
    """Load the planning project rooted at the repository containing
    ``<root>/.planning``. *root* may be the repository root or any directory
    inside it.
    """
    root = Path(root)
    planning_dir = find_planning_dir(root)
    repo_root = planning_dir.parent

    project_path = planning_dir / PROJECT_FILE
    if not project_path.is_file():
        raise LoadError(f"missing {project_path}; run 'pcp init' first")

    issues: list[ValidationIssue] = []
    config = _parse_config(_read_yaml(project_path), issues)

    project = Project(root=repo_root, config=config, load_issues=issues)

    # roadmap.yaml may declare nodes inline; node files under nodes/ are
    # merged afterwards (sorted by filename for deterministic load order).
    roadmap_path = planning_dir / ROADMAP_FILE
    raw_nodes: list[tuple[object, str | None]] = []
    if roadmap_path.is_file():
        roadmap = _read_yaml(roadmap_path)
        if roadmap is None:
            roadmap = {}
        if not isinstance(roadmap, dict):
            issues.append(_issue(Severity.ERROR, "invalid-roadmap", f"{ROADMAP_FILE}: top level must be a mapping"))
        else:
            known = {"nodes"}
            for key in sorted(str(k) for k in roadmap.keys() if k not in known):
                issues.append(_issue(Severity.WARNING, "unknown-field", f"{ROADMAP_FILE}: unknown key '{key}'"))
            entries = roadmap.get("nodes")
            if entries is None:
                entries = []
            if isinstance(entries, list):
                rel = f"{PLANNING_DIR}/{ROADMAP_FILE}"
                raw_nodes.extend((entry, rel) for entry in entries)
            else:
                issues.append(_issue(Severity.ERROR, "invalid-roadmap", f"{ROADMAP_FILE}: 'nodes' must be a list"))

    nodes_dir = planning_dir / NODES_DIR
    if nodes_dir.is_dir():
        loaded: set[Path] = set()
        for node_file in sorted(nodes_dir.glob("*.yaml")):
            loaded.add(node_file)
            raw_nodes.append((_read_yaml(node_file), f"{PLANNING_DIR}/{NODES_DIR}/{node_file.name}"))
        # Planning data is source (spec §37.1): a YAML-ish file under nodes/
        # that is NOT read (wrong suffix, or nested in a subdirectory) must
        # never disappear silently — surface it so `pcp validate` can say so.
        for candidate in sorted(nodes_dir.rglob("*")):
            if not candidate.is_file() or candidate in loaded:
                continue
            if candidate.suffix not in (".yaml", ".yml"):
                continue
            rel = f"{PLANNING_DIR}/{NODES_DIR}/{candidate.relative_to(nodes_dir).as_posix()}"
            issues.append(
                _issue(
                    Severity.WARNING,
                    "ignored-node-file",
                    f"'{rel}' is not loaded (only top-level *.yaml files are read); "
                    "move it to the top level with a .yaml suffix so it joins the planning graph",
                )
            )

    for raw, source_file in raw_nodes:
        node = parse_node(raw, source_file, issues)
        if node is None:
            continue
        if not NODE_ID_RE.match(node.id):
            issues.append(
                _issue(
                    Severity.ERROR,
                    "invalid-node-id",
                    f"node id '{node.id}' must match {NODE_ID_RE.pattern}",
                    node.id,
                )
            )
        if node.id in project.nodes:
            existing = project.nodes[node.id].source_file or "unknown"
            issues.append(
                _issue(
                    Severity.ERROR,
                    "duplicate-node-id",
                    f"duplicate node id '{node.id}' (first defined in {existing}); keeping the first definition",
                    node.id,
                )
            )
            continue
        project.nodes[node.id] = node

    return project
