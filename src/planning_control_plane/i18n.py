"""Presentation-only localization for the generated HTML (UI V0.1.1).

Scope, deliberately narrow:

* This module localizes **human-facing UI presentation only**. It never
  touches planning data. Node ids, decision ids, stored enum values, YAML
  values, ``pcp context`` capsule text and the machine-facing enums printed
  by the CLI keep their original values everywhere (Owner Decision UI-D2).
* The locale is an explicit **UI projection configuration** read from
  ``.planning/project.yaml`` under ``ui.locale`` (Owner Decision UI-D1). It
  is never inferred from the project name, from CJK characters in the data,
  from the OS locale or from environment variables, so the same planning
  source plus the same config always renders byte-identical output.

Only two locales exist in V0.1.1: ``en`` (default) and ``zh-CN``. There is
no gettext, no Babel, no external locale files and no third-party i18n
framework — just the two dictionaries below, which are required to carry
exactly the same key set (enforced by the test suite).

Status handling follows UI-D2:

* compact places (sidebar, tables, queues) show the localized label only;
* the node header and the three-track panel show ``<localized> <RAW_ENUM>``
  so the machine-facing value stays visible and greppable;
* for ``en`` the localized label *is* the raw enum, so English pages keep
  the V0.1 wording and never print a value twice.
"""

from __future__ import annotations

from typing import Callable

from planning_control_plane.model import NodeStatus, TrackStatus

__all__ = [
    "DEFAULT_LOCALE",
    "SUPPORTED_LOCALES",
    "TRANSLATIONS",
    "html_lang",
    "is_supported",
    "resolve_locale",
    "status_label",
    "status_shape",
    "track_label",
    "track_shape",
    "translator",
]

#: Locale used when ``ui.locale`` is absent or unusable.
DEFAULT_LOCALE = "en"

#: Locales V0.1.1 ships. Order is stable for error messages.
SUPPORTED_LOCALES = ("en", "zh-CN")

#: Shape glyph per overall status, so status is never colour-only
#: (text + shape + colour, spec §13).
_STATUS_SHAPES = {
    NodeStatus.NOT_STARTED.value: "○",
    NodeStatus.DISCUSSING.value: "◐",
    NodeStatus.INVESTIGATING.value: "◐",
    NodeStatus.DECIDED.value: "◐",
    NodeStatus.WRITEBACK_PENDING.value: "◐",
    NodeStatus.WRITEBACK_DONE.value: "◐",
    NodeStatus.READY.value: "◐",
    NodeStatus.IMPLEMENTING.value: "◐",
    NodeStatus.BLOCKED.value: "▲",
    NodeStatus.DONE.value: "●",
    NodeStatus.DEFERRED.value: "◇",
}

#: Shape glyph per track status (spec §34).
_TRACK_SHAPES = {
    TrackStatus.NOT_STARTED.value: "○",
    TrackStatus.IN_PROGRESS.value: "◐",
    TrackStatus.DONE.value: "●",
    TrackStatus.NOT_APPLICABLE.value: "–",
}

#: Fallback shape for values outside the controlled enums (the loader keeps
#: such values so ``pcp validate`` can report them).
_UNKNOWN_SHAPE = "?"


_EN: dict[str, str] = {
    # ------------------------------------------------------------- chrome
    "site.tool": "Planning Control Plane",
    "site.skip": "Skip to main content",
    "site.dashboard": "Dashboard",
    "site.tree": "Tree",
    "site.tree_label": "Planning tree",
    "site.sidebar_tree_label": "Planning tree (sidebar)",
    "site.expand_all": "Expand all",
    "site.collapse_all": "Collapse all",
    "site.no_nodes": "No planning nodes.",
    "site.footer.boundary": (
        "This view is authoritative only for planning structure and planning progress."
    ),
    "site.footer.ownership": (
        "Normative product, governance, architecture, and implementation semantics "
        "remain owned by the linked project artifacts."
    ),
    # ---------------------------------------------------------- dashboard
    "dash.title": "Planning Dashboard",
    "dash.subtitle": "Where we are, what is blocked, and what happens next.",
    "dash.focus": "Current Focus",
    "dash.focus.none": "No current focus is set.",
    "dash.focus.none_hint": "Run pcp focus <node-id> to choose the node the next session should work on.",
    "dash.focus.missing": "Current focus is set to {id}, but no node with that id exists in the planning graph.",
    "dash.focus.missing_hint": "Run pcp focus <node-id> to select an existing node.",
    "dash.parent_path": "Parent path",
    "dash.attention": "Needs Attention",
    "dash.attention.blocking": "Blocking decisions",
    "dash.attention.blocked": "Blocked nodes",
    "dash.attention.deferred_deps": "Dependencies of the focus node that are deferred or missing",
    "dash.no_blockers": "No blockers",
    "dash.branch": "Focus Branch",
    "dash.branch.hint": "Only the branch around the current focus. The full planning tree is in the sidebar.",
    "dash.branch.empty": "The current focus has no sibling or child nodes.",
    "dash.branch.children": "Child nodes",
    "dash.branch.siblings": "Sibling nodes",
    "dash.progress": "Progress",
    "dash.progress.note": "Planning node progress only — not product or engineering completion.",
    "dash.progress.total": "Total",
    "dash.progress.done": "Done",
    "dash.progress.active": "Active",
    "dash.progress.blocked": "Blocked",
    "dash.progress.pending": "Pending",
    "dash.progress.deferred": "Deferred",
    "dash.queue": "Ready Queue",
    "dash.queue.hint": "Nodes that have not started and whose dependencies are all DONE.",
    "dash.queue.empty": "No nodes are ready to start.",
    "dash.recent": "Recently Updated",
    "dash.recent.empty": "No nodes yet.",
    "dash.col.updated": "Updated",
    "dash.col.node": "Node",
    "dash.col.status": "Status",
    "dash.col.decision": "Decision",
    "dash.col.summary": "Summary",
    # --------------------------------------------------------- node page
    "node.breadcrumb": "Breadcrumb",
    "node.updated": "updated",
    "node.focus_flag": "focus",
    "node.focus_title": "Current focus",
    "node.objective": "Objective",
    "node.objective.empty": "No objective recorded.",
    "node.next_action": "Next Action",
    "node.next_action.empty": "No next action recorded.",
    "node.scope": "Scope Guard",
    "node.scope.hint": "The boundary of this round. Anything outside it belongs to another node.",
    "node.scope.in": "In scope this round",
    "node.scope.out": "Out of scope this round",
    "node.scope.in.empty": "Nothing declared in scope.",
    "node.scope.out.empty": "Nothing declared out of scope.",
    "node.decisions.blocking": "Blocking Decisions",
    "node.decisions.open": "Open Decisions",
    "node.decisions.open.empty": "No open decisions.",
    "node.decisions.frozen": "Frozen Decisions",
    "node.decisions.frozen.own": "This node",
    "node.decisions.frozen.empty": "No frozen decisions on this node.",
    "node.decisions.inherited": "Inherited from ancestors",
    "node.decisions.inherited.empty": "No frozen decisions inherited from ancestors.",
    "node.decisions.inherited.hint": "nearest ancestor expanded, higher ancestors collapsed",
    "node.decisions.deferred": "Deferred Decisions",
    "node.decisions.deferred.empty": "No deferred decisions.",
    "node.decisions.count": "{n} decisions",
    "node.decisions.source": "source",
    "node.decisions.sources_n": "sources · {n}",
    "node.tracks": "Three-track Status",
    "node.tracks.hint": "Discussion, writeback and implementation progress are tracked independently and never derived from each other.",
    "node.track.discussion": "Discussion",
    "node.track.writeback": "Writeback",
    "node.track.implementation": "Implementation",
    "node.relations": "Relations",
    "node.rel.depends": "Depends On",
    "node.rel.blocks": "Blocks",
    "node.rel.related": "Related To",
    "node.rel.supersedes": "Supersedes",
    "node.rel.superseded_by": "Superseded By",
    "node.rel.none": "None.",
    "node.rel.unknown": "(unknown node)",
    "node.sources": "Sources",
    "node.sources.canonical": "Canonical Sources",
    "node.sources.evidence": "Evidence Sources",
    "node.sources.none": "None.",
    "node.resume": "Resume This Work",
    "node.resume.hint": "Session resume capsule — the same content as {cmd}. Paste it into a new session to resume this branch.",
    "node.resume.size": "{lines} lines · {size}",
    "node.resume.show": "Show full capsule",
    # ---------------------------------------------------------- actions
    "action.copy_context": "Copy Context",
    "action.copy_context.aria": "Copy the context capsule to the clipboard",
    "action.copy_id": "Copy ID",
    "action.copy_id.aria": "Copy the node id to the clipboard",
    "action.copied": "Copied",
    "action.copy_fallback.hint": (
        "Automatic copy is not available in this browser. Select the text below and "
        "copy it manually (Ctrl/Cmd+C)."
    ),
    "action.copy_fallback.aria": "Context capsule text",
    # ----------------------------------------------------------- statuses
    "status.NOT_STARTED": "NOT_STARTED",
    "status.DISCUSSING": "DISCUSSING",
    "status.INVESTIGATING": "INVESTIGATING",
    "status.DECIDED": "DECIDED",
    "status.WRITEBACK_PENDING": "WRITEBACK_PENDING",
    "status.WRITEBACK_DONE": "WRITEBACK_DONE",
    "status.READY": "READY",
    "status.IMPLEMENTING": "IMPLEMENTING",
    "status.BLOCKED": "BLOCKED",
    "status.DONE": "DONE",
    "status.DEFERRED": "DEFERRED",
    "track.NOT_STARTED": "NOT_STARTED",
    "track.IN_PROGRESS": "IN_PROGRESS",
    "track.DONE": "DONE",
    "track.NOT_APPLICABLE": "N/A",
}


_ZH_CN: dict[str, str] = {
    # ------------------------------------------------------------- chrome
    "site.tool": "Planning Control Plane",
    "site.skip": "跳到主内容",
    "site.dashboard": "总览",
    "site.tree": "规划树",
    "site.tree_label": "规划树",
    "site.sidebar_tree_label": "规划树（侧栏）",
    "site.expand_all": "全部展开",
    "site.collapse_all": "全部折叠",
    "site.no_nodes": "暂无规划节点。",
    "site.footer.boundary": "本视图只对规划结构与规划进度具有权威性。",
    "site.footer.ownership": (
        "产品、治理、架构与实现的规范语义仍归所链接的项目文档所有。"
    ),
    # ---------------------------------------------------------- dashboard
    "dash.title": "规划总览",
    "dash.subtitle": "当前进行到哪里、是否被阻塞、下一步做什么。",
    "dash.focus": "当前焦点",
    "dash.focus.none": "尚未设置当前焦点。",
    "dash.focus.none_hint": "执行 pcp focus <node-id> 选择下一个会话要推进的节点。",
    "dash.focus.missing": "当前焦点指向 {id}，但规划图中没有该 id 的节点。",
    "dash.focus.missing_hint": "执行 pcp focus <node-id> 选择一个已存在的节点。",
    "dash.parent_path": "父级路径",
    "dash.attention": "需要处理",
    "dash.attention.blocking": "阻塞决策",
    "dash.attention.blocked": "阻塞节点",
    "dash.attention.deferred_deps": "焦点节点中已延期或缺失的依赖",
    "dash.no_blockers": "无阻塞",
    "dash.branch": "焦点分支",
    "dash.branch.hint": "仅显示当前焦点所在分支；完整规划树见左侧。",
    "dash.branch.empty": "当前焦点没有同级或子节点。",
    "dash.branch.children": "子节点",
    "dash.branch.siblings": "同级节点",
    "dash.progress": "规划进度",
    "dash.progress.note": "只统计 Planning Node 的推进情况，不代表产品或工程完成度。",
    "dash.progress.total": "总数",
    "dash.progress.done": "已完成",
    "dash.progress.active": "进行中",
    "dash.progress.blocked": "阻塞",
    "dash.progress.pending": "未开始",
    "dash.progress.deferred": "已延期",
    "dash.queue": "就绪队列",
    "dash.queue.hint": "尚未开始、且依赖全部 DONE 的节点。",
    "dash.queue.empty": "当前没有可以开始的节点。",
    "dash.recent": "最近更新",
    "dash.recent.empty": "暂无节点。",
    "dash.col.updated": "更新日期",
    "dash.col.node": "节点",
    "dash.col.status": "状态",
    "dash.col.decision": "决策",
    "dash.col.summary": "摘要",
    # --------------------------------------------------------- node page
    "node.breadcrumb": "路径",
    "node.updated": "更新于",
    "node.focus_flag": "焦点",
    "node.focus_title": "当前焦点",
    "node.objective": "目标",
    "node.objective.empty": "未记录目标。",
    "node.next_action": "下一步动作",
    "node.next_action.empty": "未记录下一步动作。",
    "node.scope": "范围护栏",
    "node.scope.hint": "本轮的边界；边界之外的内容属于其他节点。",
    "node.scope.in": "本轮要做",
    "node.scope.out": "本轮不做",
    "node.scope.in.empty": "未声明本轮要做的内容。",
    "node.scope.out.empty": "未声明本轮不做的内容。",
    "node.decisions.blocking": "阻塞决策",
    "node.decisions.open": "未决决策",
    "node.decisions.open.empty": "没有未决决策。",
    "node.decisions.frozen": "冻结决策",
    "node.decisions.frozen.own": "本节点",
    "node.decisions.frozen.empty": "本节点没有冻结决策。",
    "node.decisions.inherited": "继承自祖先",
    "node.decisions.inherited.empty": "没有从祖先继承的冻结决策。",
    "node.decisions.inherited.hint": "最近祖先默认展开，更上层默认折叠",
    "node.decisions.deferred": "已延期决策",
    "node.decisions.deferred.empty": "没有已延期决策。",
    "node.decisions.count": "{n} 条",
    "node.decisions.source": "来源",
    "node.decisions.sources_n": "来源 · {n} 处",
    "node.tracks": "三轨状态",
    "node.tracks.hint": "讨论、回写、实施三条轨道独立记录，互不推导。",
    "node.track.discussion": "讨论",
    "node.track.writeback": "回写",
    "node.track.implementation": "实施",
    "node.relations": "关联",
    "node.rel.depends": "依赖",
    "node.rel.blocks": "阻塞",
    "node.rel.related": "相关",
    "node.rel.supersedes": "取代",
    "node.rel.superseded_by": "被取代",
    "node.rel.none": "无。",
    "node.rel.unknown": "（未知节点）",
    "node.sources": "来源文档",
    "node.sources.canonical": "规范来源",
    "node.sources.evidence": "佐证来源",
    "node.sources.none": "无。",
    "node.resume": "恢复这项工作",
    "node.resume.hint": "会话恢复 capsule，与 {cmd} 输出一致；粘贴到新会话即可继续该分支。",
    "node.resume.size": "{lines} 行 · {size}",
    "node.resume.show": "展开完整 capsule",
    # ---------------------------------------------------------- actions
    "action.copy_context": "复制上下文",
    "action.copy_context.aria": "把 context capsule 复制到剪贴板",
    "action.copy_id": "复制 ID",
    "action.copy_id.aria": "把节点 id 复制到剪贴板",
    "action.copied": "已复制",
    "action.copy_fallback.hint": "当前浏览器不支持自动复制。请选中下方文本后手动复制（Ctrl/Cmd+C）。",
    "action.copy_fallback.aria": "context capsule 文本",
    # ----------------------------------------------------------- statuses
    "status.NOT_STARTED": "未开始",
    "status.DISCUSSING": "讨论中",
    "status.INVESTIGATING": "调研中",
    "status.DECIDED": "已裁决",
    "status.WRITEBACK_PENDING": "待回写",
    "status.WRITEBACK_DONE": "已回写",
    "status.READY": "已就绪",
    "status.IMPLEMENTING": "实施中",
    "status.BLOCKED": "阻塞",
    "status.DONE": "已完成",
    "status.DEFERRED": "已延期",
    "track.NOT_STARTED": "未开始",
    "track.IN_PROGRESS": "进行中",
    "track.DONE": "已完成",
    "track.NOT_APPLICABLE": "不适用",
}


#: The complete translation table. ``en`` and ``zh-CN`` must carry exactly
#: the same key set; ``tests/test_i18n.py`` enforces that.
TRANSLATIONS: dict[str, dict[str, str]] = {"en": _EN, "zh-CN": _ZH_CN}


def is_supported(locale: str) -> bool:
    """True when *locale* is one of :data:`SUPPORTED_LOCALES`."""
    return locale in TRANSLATIONS


def resolve_locale(raw: str | None) -> str:
    """Map a configured ``ui.locale`` value to a usable locale.

    Unknown or empty values fall back to :data:`DEFAULT_LOCALE`; reporting
    that fallback as a build WARNING is the loader's job, so this function
    never raises and never prints.
    """
    if not raw:
        return DEFAULT_LOCALE
    return raw if raw in TRANSLATIONS else DEFAULT_LOCALE


def html_lang(locale: str) -> str:
    """Value for the ``<html lang="...">`` attribute (spec §7)."""
    return resolve_locale(locale)


def translator(locale: str) -> Callable[..., str]:
    """Return ``t(key, **kwargs)`` for *locale*.

    Missing keys fall back to the English string and finally to the key
    itself, so a template can never render an empty label. Keyword
    arguments are applied with :meth:`str.format`; a malformed placeholder
    degrades to the unformatted string instead of raising during a build.
    """
    table = TRANSLATIONS.get(resolve_locale(locale), _EN)

    def t(key: str, **kwargs: object) -> str:
        text = table.get(key, _EN.get(key, key))
        if not kwargs:
            return text
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):  # pragma: no cover - defensive
            return text

    return t


def status_label(locale: str, status: str) -> str:
    """Localized label for an overall node status.

    Values outside :class:`~planning_control_plane.model.NodeStatus` are
    returned unchanged — the generator projects planning data defensively
    and leaves the verdict to ``pcp validate``.
    """
    return translator(locale)(f"status.{status}") if f"status.{status}" in _EN else status


def track_label(locale: str, status: str) -> str:
    """Localized label for one track status (``N/A`` included)."""
    return translator(locale)(f"track.{status}") if f"track.{status}" in _EN else status


def status_shape(status: str) -> str:
    """Shape glyph for an overall status (locale independent)."""
    return _STATUS_SHAPES.get(status, _UNKNOWN_SHAPE)


def track_shape(status: str) -> str:
    """Shape glyph for a track status (locale independent)."""
    return _TRACK_SHAPES.get(status, _UNKNOWN_SHAPE)
