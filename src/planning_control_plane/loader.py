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

from planning_control_plane import i18n
from planning_control_plane.model import (
    NODE_ID_RE,
    PLANNING_DIR,
    PCPError,
    Decision,
    Idea,
    IdeaOutcome,
    IdeaSource,
    idea_issue,
    Node,
    Project,
    ProjectConfig,
    AuthorityConfig,
    Severity,
    TrackStatus,
    TRACK_STATUS_ALIASES,
    UIConfig,
    ValidationIssue,
)

PROJECT_FILE = "project.yaml"
ROADMAP_FILE = "roadmap.yaml"
NODES_DIR = "nodes"
IDEAS_DIR = "ideas"

#: Keys of the idea schema (spec §51.2).
IDEA_FIELDS = frozenset(
    {
        "id",
        "title",
        "status",
        "detail",
        "relates_to",
        "benchmark_sources",
        "methodology_sources",
        "outcome",
        "created",
        "last_updated",
    }
)

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


def _read_idea_yaml(path: Path, rel: str, issues: list) -> tuple[bool, object]:
    """Read one idea file tolerantly (spec §51.3.1 / IDEA-D58).

    Unlike :func:`_read_yaml`, any read or parse failure — YAML syntax
    errors, duplicate keys (``_UniqueKeyLoader`` raises on those), an
    unreadable file — becomes an ``invalid-idea-file`` ERROR issue and the
    file is skipped: an uncommitted thought must never brick the planning
    data it decorates, so ideas never raise :class:`LoadError`. Returns
    ``(False, None)`` when the file is skipped, ``(True, data)``
    otherwise — *data* may still be ``None`` for an empty-but-valid file,
    which :func:`parse_idea` reports as ``invalid-idea``.
    """
    try:
        with path.open("r", encoding="utf-8") as handle:
            return True, yaml.load(handle, Loader=_UniqueKeyLoader)
    except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
        issues.append(idea_issue(Severity.ERROR, "invalid-idea-file", f"cannot read or parse ({exc})", rel))
        return False, None


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


def _as_idea_string_list(value, idea_id: str, key: str, issues: list) -> list[str]:
    """Idea-layer twin of :func:`_as_string_list`: same tolerance, but
    reports ``invalid-idea-field`` with the ``idea '<id>': `` prefix so the
    issue stays identifiable as idea-layer (spec §58.1 / IDEA-D64)."""
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append(
            idea_issue(Severity.ERROR, "invalid-idea-field", f"'{key}' must be a list, got {type(value).__name__}", idea_id, idea_id)
        )
        return []
    result = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item)
        else:
            issues.append(idea_issue(Severity.ERROR, "invalid-idea-field", f"'{key}' entries must be non-empty strings", idea_id, idea_id))
    return result


def _as_idea_sources(value, idea_id: str, key: str, issues: list) -> list[IdeaSource]:
    """Parse one justification list (spec §52.2): entries are mappings
    carrying a repository-relative ``ref`` and/or a free-text ``note``;
    an entry with neither is meaningless and reported."""
    if value is None:
        return []
    if not isinstance(value, list):
        issues.append(
            idea_issue(Severity.ERROR, "invalid-idea-field", f"'{key}' must be a list, got {type(value).__name__}", idea_id, idea_id)
        )
        return []
    result: list[IdeaSource] = []
    for item in value:
        if not isinstance(item, dict):
            issues.append(idea_issue(Severity.ERROR, "invalid-idea-source", f"'{key}' entries must be mappings with 'ref' and/or 'note'", idea_id, idea_id))
            continue
        ref = item.get("ref")
        note = item.get("note")
        if ref is not None and not isinstance(ref, str):
            issues.append(idea_issue(Severity.WARNING, "invalid-idea-source", f"'{key}' entry has a non-string 'ref'; ignored", idea_id, idea_id))
            ref = None
        if note is not None and not isinstance(note, str):
            issues.append(idea_issue(Severity.WARNING, "invalid-idea-source", f"'{key}' entry has a non-string 'note'; ignored", idea_id, idea_id))
            note = None
        ref_ok = isinstance(ref, str) and ref.strip()
        note_ok = isinstance(note, str) and note.strip()
        if not ref_ok and not note_ok:
            issues.append(idea_issue(Severity.ERROR, "invalid-idea-source", f"'{key}' entry needs a non-empty 'ref' or 'note'", idea_id, idea_id))
            continue
        result.append(IdeaSource(ref=ref.strip() if ref_ok else None, note=note.strip() if note_ok else None))
    return result


def _as_idea_outcome(value, idea_id: str, issues: list) -> IdeaOutcome | None:
    """Parse ``outcome`` (spec §55.2): a mapping with a required non-empty
    ``node`` and an optional free-text ``note``."""
    if value is None:
        return None
    if not isinstance(value, dict):
        issues.append(idea_issue(Severity.ERROR, "invalid-idea-outcome", "'outcome' must be a mapping with 'node' and optional 'note'", idea_id, idea_id))
        return None
    node = value.get("node")
    note = value.get("note")
    if not isinstance(node, str) or not node.strip():
        issues.append(idea_issue(Severity.ERROR, "invalid-idea-outcome", "'outcome' needs a non-empty 'node'", idea_id, idea_id))
        return None
    if note is not None and not isinstance(note, str):
        issues.append(idea_issue(Severity.WARNING, "invalid-idea-outcome", "'outcome' has a non-string 'note'; ignored", idea_id, idea_id))
        note = None
    return IdeaOutcome(node=node.strip(), note=note.strip() if isinstance(note, str) else "")


def parse_idea(data: object, source_file: str | None, issues: list) -> Idea | None:
    """Parse one idea mapping. Returns ``None`` when the entry is unusable
    (not a mapping, or missing/empty ``id``) — mirrors :func:`parse_node`.
    A present-but-empty value (e.g. ``status: ""``) is kept verbatim for
    the validator to report; only absent (or null) keys fall back to the
    schema default. Silently defaulting would hide typos.
    """
    if not isinstance(data, dict):
        issues.append(idea_issue(Severity.ERROR, "invalid-idea", f"idea entry in {source_file or 'ideas'} is not a mapping", source_file or "ideas"))
        return None
    idea_id = data.get("id")
    if not isinstance(idea_id, str) or not idea_id.strip():
        issues.append(idea_issue(Severity.ERROR, "invalid-idea", f"idea entry in {source_file or 'ideas'} is missing a non-empty 'id'", source_file or "ideas"))
        return None
    idea_id = idea_id.strip()

    title = _as_text(data.get("title"))
    if not title:
        issues.append(idea_issue(Severity.ERROR, "missing-idea-title", "idea is missing a non-empty 'title'", idea_id, idea_id))
        title = idea_id

    idea = Idea(id=idea_id, title=title, source_file=source_file)
    if data.get("status") is not None:
        idea.status = _as_text(data.get("status"))
    idea.detail = _as_text(data.get("detail"))
    idea.created = _as_text(data.get("created"))
    idea.last_updated = _as_text(data.get("last_updated"))
    idea.relates_to = _as_idea_string_list(data.get("relates_to"), idea_id, "relates_to", issues)
    idea.benchmark_sources = _as_idea_sources(data.get("benchmark_sources"), idea_id, "benchmark_sources", issues)
    idea.methodology_sources = _as_idea_sources(data.get("methodology_sources"), idea_id, "methodology_sources", issues)
    idea.outcome = _as_idea_outcome(data.get("outcome"), idea_id, issues)

    idea.unknown_fields = sorted(str(k) for k in data.keys() if k not in IDEA_FIELDS)
    return idea


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

    ui = data.get("ui")
    if ui is not None:
        if not isinstance(ui, dict):
            issues.append(_issue(Severity.ERROR, "invalid-ui-section", f"{PROJECT_FILE}: 'ui' must be a mapping"))
        else:
            config.ui = _parse_ui(ui, issues)

    known_top = {"project", "planning", "authority", "output", "ui"}
    config.unknown_keys = sorted(str(k) for k in data.keys() if k not in known_top)
    return config


def _parse_ui(ui: dict, issues: list) -> UIConfig:
    """Parse the ``ui:`` section (UI V0.1.1).

    ``ui.locale`` selects the default language of the generated HTML only
    (the page itself offers a runtime switch stored in the browser). An
    unsupported value is never fatal: it falls back to the default locale
    and reports a WARNING, so an upgraded or mistyped config still builds
    (spec §5). A missing key keeps the default, which is exactly the V0.1
    English behaviour.
    """
    config = UIConfig()
    locale = ui.get("locale")
    if locale is not None:
        if not isinstance(locale, str) or not locale.strip():
            issues.append(
                _issue(
                    Severity.WARNING,
                    "unknown-ui-locale",
                    f"{PROJECT_FILE}: 'ui.locale' must be a non-empty string; "
                    f"falling back to '{i18n.DEFAULT_LOCALE}' "
                    f"(supported: {', '.join(i18n.SUPPORTED_LOCALES)})",
                )
            )
        else:
            config.raw_locale = locale.strip()
            if i18n.is_supported(config.raw_locale):
                config.locale = config.raw_locale
            else:
                issues.append(
                    _issue(
                        Severity.WARNING,
                        "unknown-ui-locale",
                        f"{PROJECT_FILE}: unknown 'ui.locale' value '{config.raw_locale}'; "
                        f"falling back to '{i18n.DEFAULT_LOCALE}' "
                        f"(supported: {', '.join(i18n.SUPPORTED_LOCALES)})",
                    )
                )

    config.unknown_keys = sorted(str(k) for k in ui.keys() if k != "locale")
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

    # Idea layer (spec §51): one file per idea under ideas/, loaded with
    # the same discipline as nodes but with failure-domain isolation — a
    # broken idea file becomes an issue instead of a LoadError (IDEA-D58).
    ideas_dir = planning_dir / IDEAS_DIR
    if ideas_dir.is_dir():
        loaded_ideas: set[Path] = set()
        for idea_file in sorted(ideas_dir.glob("*.yaml")):
            loaded_ideas.add(idea_file)
            rel = f"{PLANNING_DIR}/{IDEAS_DIR}/{idea_file.name}"
            ok, raw = _read_idea_yaml(idea_file, rel, issues)
            if not ok:
                continue
            idea = parse_idea(raw, rel, issues)
            if idea is None:
                continue
            if not NODE_ID_RE.match(idea.id):
                issues.append(
                    idea_issue(
                        Severity.ERROR,
                        "invalid-idea-id",
                        f"idea id '{idea.id}' must match {NODE_ID_RE.pattern}",
                        idea.id,
                        idea.id,
                    )
                )
            if idea.id in project.ideas:
                existing = project.ideas[idea.id].source_file or "unknown"
                issues.append(
                    idea_issue(
                        Severity.ERROR,
                        "duplicate-idea-id",
                        f"duplicate idea id '{idea.id}' (first defined in {existing}); keeping the first definition",
                        idea.id,
                        idea.id,
                    )
                )
                continue
            project.ideas[idea.id] = idea
        # Mirror the nodes/ contract (spec §37.1): a YAML-ish file under
        # ideas/ that is NOT read must never disappear silently.
        for candidate in sorted(ideas_dir.rglob("*")):
            if not candidate.is_file() or candidate in loaded_ideas:
                continue
            if candidate.suffix not in (".yaml", ".yml"):
                continue
            rel = f"{PLANNING_DIR}/{IDEAS_DIR}/{candidate.relative_to(ideas_dir).as_posix()}"
            issues.append(
                idea_issue(
                    Severity.WARNING,
                    "ignored-idea-file",
                    f"'{rel}' is not loaded (only top-level *.yaml files are read); "
                    "move it to the top level with a .yaml suffix so it joins the idea layer",
                    rel,
                )
            )

    return project
