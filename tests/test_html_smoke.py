"""HTML smoke tests over a built demo site (spec §22, §24–§30): page set,
authority-boundary footer, breadcrumb, accessibility hooks, embedded capsule
and offline self-containment (no external URLs).

The demo repository is read-only here: the site is generated with the engine
API into a temporary directory.
"""

from __future__ import annotations

import html as html_module
import re
from pathlib import Path

import pytest

from planning_control_plane import generator
from planning_control_plane.loader import load_project

#: Footer authority boundary (spec §28).
FOOTER_BOUNDARY = "This view is authoritative only for planning structure and planning progress."
FOOTER_OWNERSHIP = (
    "Normative product, governance, architecture, and implementation semantics remain owned by "
    "the linked project artifacts."
)

DEMO_NODE_IDS = ["P1", "P2", "P2-A", "P2-A1", "P2-A2", "P2-A3", "P2-A4"]


@pytest.fixture(scope="module")
def built_site(tmp_path_factory):
    demo_root = Path(__file__).resolve().parent.parent / "examples" / "demo-project"
    project = load_project(demo_root)
    dist = tmp_path_factory.mktemp("site") / "dist"
    generator.build_site(project, dist)
    return project, dist


# ------------------------------------------------------------------- page set


def test_expected_pages_and_assets_exist(built_site):
    _project, dist = built_site
    assert (dist / "index.html").is_file()
    for node_id in DEMO_NODE_IDS:
        assert (dist / "nodes" / f"{node_id}.html").is_file(), node_id
    assert (dist / "assets" / "style.css").is_file()
    assert (dist / "assets" / "app.js").is_file()
    # nothing beyond index, node pages and the two assets
    assert sorted(p.relative_to(dist).as_posix() for p in dist.rglob("*") if p.is_file()) == sorted(
        ["index.html", "assets/style.css", "assets/app.js", *[f"nodes/{n}.html" for n in DEMO_NODE_IDS]]
    )


# -------------------------------------------------------- every-page contracts


@pytest.mark.parametrize("page_name", ["index.html"] + [f"nodes/{n}.html" for n in DEMO_NODE_IDS])
def test_every_page_has_authority_footer_and_tree(built_site, page_name):
    _project, dist = built_site
    text = (dist / page_name).read_text(encoding="utf-8")

    # footer states the authority boundary on every page
    assert FOOTER_BOUNDARY in text
    assert FOOTER_OWNERSHIP in text
    assert "Planning Control Plane" in text

    # the planning navigation is an ARIA tree
    assert 'role="tree"' in text
    # every node id appears in the sidebar tree
    for node_id in DEMO_NODE_IDS:
        assert node_id in text


@pytest.mark.parametrize(
    "relative",
    ["index.html", "assets/style.css", "assets/app.js", *[f"nodes/{n}.html" for n in DEMO_NODE_IDS]],
)
def test_no_external_http_links_anywhere(built_site, relative):
    """The site is offline: no http(s):// URLs in any generated file."""
    _project, dist = built_site
    content = (dist / relative).read_text(encoding="utf-8")
    assert "http://" not in content, relative
    assert "https://" not in content, relative


@pytest.mark.parametrize("page_name", ["index.html"] + [f"nodes/{n}.html" for n in DEMO_NODE_IDS])
def test_all_links_and_assets_are_relative(built_site, page_name):
    """Every href/src resolves to a sibling file (file://-openable)."""
    _project, dist = built_site
    text = (dist / page_name).read_text(encoding="utf-8")
    urls = re.findall(r'(?:href|src)="([^"]+)"', text)
    assert urls  # pages do reference their assets/pages
    for url in urls:
        assert "://" not in url and not url.startswith("//"), url
        assert not url.startswith("/"), url


# ------------------------------------------------------------- node page parts


def test_node_page_breadcrumb_is_clickable_path(built_site):
    """Spec §23 + V0.1.2 final polish §4: the trail starts at the project,
    ancestors carry id *and* title, and every crumb is a link."""
    _project, dist = built_site
    text = (dist / "nodes" / "P2-A2.html").read_text(encoding="utf-8")

    match = re.search(r'<nav class="breadcrumb".*?</nav>', text, re.DOTALL)
    assert match, "breadcrumb nav missing"
    breadcrumb = match.group(0)

    # the project is the root of the trail and links back to the dashboard
    assert '<a class="crumb crumb--root" href="../index.html" title="Demo Project">Demo Project</a>' in breadcrumb

    # crumbs read Program > Phase > Strategy > node, root first
    crumbs = re.findall(r'<span class="mono">([^<]+)</span>', breadcrumb)
    assert crumbs == ["P1", "P2", "P2-A", "P2-A2"]
    titles = re.findall(r'<span class="crumb-title">([^<]+)</span>', breadcrumb)
    assert titles == ["Program Foundation", "Product Rollout", "Rollout Strategy"]
    # every ancestor crumb is a link, the current one is marked
    assert 'aria-current="page"' in breadcrumb
    assert len(re.findall(r'<a class="crumb" href="\.\./nodes/', breadcrumb)) == 3


def test_node_page_breadcrumb_does_not_repeat_the_h1_title(built_site):
    """VIS-AC-03: the current crumb is the id alone; the full title lives in
    the H1 and, for hover, in the crumb's `title` attribute (VIS-AC-04)."""
    _project, dist = built_site
    text = (dist / "nodes" / "P2-A4.html").read_text(encoding="utf-8")

    breadcrumb = re.search(r'<nav class="breadcrumb".*?</nav>', text, re.DOTALL).group(0)
    current = re.search(r'<span class="crumb is-current".*?</span></span>', breadcrumb, re.DOTALL).group(0)

    assert "Rollout Readiness Preflight" not in breadcrumb.replace(
        'title="P2-A4 — Rollout Readiness Preflight"', ""
    )
    assert 'title="P2-A4 — Rollout Readiness Preflight"' in current
    assert 'aria-current="page"' in current

    # the H1 keeps id + full title (final polish §5)
    head = re.search(r'<header class="node-head">.*?</header>', text, re.DOTALL).group(0)
    assert '<span class="mono node-id">P2-A4</span>' in head
    assert '<span class="node-title">Rollout Readiness Preflight</span>' in head


def test_topbar_keeps_overview_then_language_selector(built_site):
    """VIS-AC-01/02: fixed utility order, and Overview is never the primary
    call to action — that weight belongs to Copy Context alone."""
    _project, dist = built_site

    for page in ("index.html", "nodes/P2-A4.html"):
        text = (dist / page).read_text(encoding="utf-8")
        topbar = re.search(r'<header class="topbar">.*?</header>', text, re.DOTALL).group(0)
        utils = re.search(r'<div class="topbar-utils">.*?</div>\s*</div>', topbar, re.DOTALL).group(0)
        assert utils.index('class="topbar-nav"') < utils.index('class="lang-switch"')
        assert "btn--primary" not in topbar
        assert 'class="topbar-nav"' in topbar

    # the dashboard marks its own entry instead of hiding it, so the
    # control never changes position between pages
    index = (dist / "index.html").read_text(encoding="utf-8")
    node = (dist / "nodes" / "P2-A4.html").read_text(encoding="utf-8")
    assert '<a class="topbar-nav" href="index.html" aria-current="page"' in index
    assert '<a class="topbar-nav" href="../index.html" data-i18n' in node


def test_node_page_copy_context_button_has_aria_label(built_site):
    _project, dist = built_site
    text = (dist / "nodes" / "P2-A4.html").read_text(encoding="utf-8")

    buttons = re.findall(r'<button[^>]*data-copy-from="capsule-text"[^>]*>', text)
    assert buttons, "Copy Context button missing"
    assert "Copy Context</button>" in text
    for button in buttons:
        assert re.search(r'aria-label="[^"]+"', button)
        assert re.search(r'data-copied-label="[^"]+"', button)
    # a Copy ID button carries the raw node id, never a localized form
    assert 'data-copy-value="P2-A4"' in text
    # the clipboard fallback is a labelled, read-only textarea
    assert re.search(r'<textarea readonly aria-label="[^"]+"[^>]*>', text)
    # the result of a copy is announced, not only shown (spec §36)
    assert 'class="copy-status" role="status" aria-live="polite"' in text


def test_node_page_embeds_capsule_matching_cli(demo_root, built_site, capsys):
    """The 'Resume This Work' capsule equals ``pcp context <node>`` output."""
    from planning_control_plane import cli

    _project, dist = built_site
    page = (dist / "nodes" / "P2-A4.html").read_text(encoding="utf-8")

    match = re.search(r'<pre id="capsule-text" class="capsule-text">(.*?)</pre>', page, re.DOTALL)
    assert match
    embedded = html_module.unescape(match.group(1))

    assert cli.main(["-p", str(demo_root), "context", "P2-A4"]) == 0
    printed = capsys.readouterr().out

    assert embedded == printed
    assert "=== PCP CONTEXT CAPSULE ===" in embedded
    assert "BD-401" in embedded


def test_node_page_shows_inherited_frozen_decisions(built_site):
    _project, dist = built_site
    text = (dist / "nodes" / "P2-A1.html").read_text(encoding="utf-8")

    # P2-A1 sits under P2-A / P2 / P1; the program-level frozen decision
    # FD-001 is displayed as inherited, grouped by ancestor in <details>
    assert "Inherited from ancestors" in text
    assert "FD-101" in text  # frozen at P2
    assert "FD-001" in text  # frozen at P1
    assert '<details class="dgroup"' in text


def test_node_page_track_status_shows_na(built_site):
    """Spec §34: each track shows label, shape and the raw enum value."""
    _project, dist = built_site
    text = (dist / "nodes" / "P2-A4.html").read_text(encoding="utf-8")

    # P2-A4: discussion NOT_STARTED, writeback N/A, implementation N/A.
    # Since V0.1.2 the label carries its runtime translation key and the
    # raw chip is always in the document (hidden under `en` by the
    # stylesheet, shown under every other locale).
    for label, key, raw, shape in (
        ("Discussion", "discussion", "NOT_STARTED", "○"),
        ("Writeback", "writeback", "N/A", "–"),
        ("Implementation", "implementation", "N/A", "–"),
    ):
        pattern = (
            rf"<dt data-i18n=\"node\.track\.{key}\">{label}</dt>\s*"
            rf"<dd><span class=\"track-badge\" data-track=\"{re.escape(raw)}\">"
            rf"<span class=\"shape\" aria-hidden=\"true\">{shape}</span>"
            rf"<span data-i18n=\"[^\"]*\">{re.escape(raw)}</span>"
            rf" <span class=\"badge-raw mono\">{re.escape(raw)}</span></span>"
        )
        assert re.search(pattern, text), label


# --------------------------------------------------------------- dashboard


def test_dashboard_shows_focus_exceptions_branch_progress_queue(built_site):
    """UI-D3: orientation, exceptions and next work — never the whole tree."""
    _project, dist = built_site
    text = (dist / "index.html").read_text(encoding="utf-8")

    for heading in ("Current Focus", "Needs Attention", "Focus Branch", "Progress", "Ready Queue", "Recently Updated"):
        assert heading in text, heading

    # current focus card: node, status, next action, three tracks, resume
    assert "P2-A4" in text
    assert "Rollout Readiness Preflight" in text
    assert "NOT_STARTED" in text
    assert "Resolve BD-401" in text
    assert "Copy Context</button>" in text
    assert "Parent path" in text

    # progress numbers: total 7, done 4, blocked 0, pending 1 (planning only)
    assert '<span class="stat-value">7</span>' in text
    assert '<span class="stat-value">4</span>' in text
    assert '<span class="stat-value">0</span>' in text
    assert "not product or engineering completion" in text

    # the demo project has one blocking decision, so the exception panel exists
    assert "BD-401" in text
    assert 'class="panel panel--exception"' in text

    # ready queue: P2-A4 is the one ready node
    queue = re.search(r'id="queue-heading".*?</section>', text, re.DOTALL).group(0)
    assert "P2-A4" in queue

    # recently updated sorts by date, newest first
    recent = re.search(r'id="recent-heading".*?</section>', text, re.DOTALL).group(0)
    dates = re.findall(r'<td class="mono nowrap">([^<]+)</td>', recent)
    assert dates == sorted(dates, reverse=True)
    assert dates[0] == "2026-08-17"  # P2-A4 is the most recently updated


def test_dashboard_does_not_repeat_the_planning_tree(built_site):
    """UI-D3: the sidebar owns the full topology; the main region must not
    render a second copy of it."""
    _project, dist = built_site
    text = (dist / "index.html").read_text(encoding="utf-8")

    main = re.search(r'<main class="content".*?</main>', text, re.DOTALL).group(0)
    assert 'role="tree"' not in main
    assert 'class="treeitem' not in main
    # ... while the sidebar still carries every node
    sidebar = re.search(r'<aside class="sidebar".*?</aside>', text, re.DOTALL).group(0)
    for node_id in DEMO_NODE_IDS:
        assert f'data-node-id="{node_id}"' in sidebar


def test_dashboard_focus_branch_points_at_the_sidebar(built_site):
    """Spec §21: a branch view, explicitly not the whole tree."""
    _project, dist = built_site
    text = (dist / "index.html").read_text(encoding="utf-8")

    branch = re.search(r'id="branch-heading".*?</section>', text, re.DOTALL).group(0)
    assert "full planning tree is in the sidebar" in branch.lower()
    # lineage down to the focus, then its siblings with the focus marked
    lineage = re.search(r'<p class="branch-lineage">.*?</p>', branch, re.DOTALL).group(0)
    assert re.findall(r'<span class="mono">([^<]+)</span>', lineage) == ["P1", "P2", "P2-A"]
    for sibling in ("P2-A1", "P2-A2", "P2-A3", "P2-A4"):
        assert sibling in branch
    assert 'class="branch-item is-current"' in branch
    # a branch view, not a second tree
    assert 'role="tree"' not in branch and 'class="treeitem' not in branch


def test_sidebar_marks_current_focus_with_its_own_visual_system(built_site):
    """Spec §14: focus is a pill plus aria-current, never another status."""
    _project, dist = built_site
    text = (dist / "index.html").read_text(encoding="utf-8")

    focus_item = re.search(r'<li role="treeitem"[^>]*class="[^"]*is-focus[^"]*"', text)
    assert focus_item
    # the focus marker must be visible text, not colour-only (spec §29)
    assert re.search(r'class="focus-pill"[^>]*>\s*focus\s*<', text)
    assert 'aria-current="true"' in text
    # ... and it is not expressed as a status value
    assert 'data-status="FOCUS"' not in text


def test_sidebar_tree_has_no_redundant_tab_stops(built_site):
    """Spec §43/§44: branch rows expose a real toggle button; the treeitems
    themselves are no longer 15 extra tab stops."""
    _project, dist = built_site
    text = (dist / "index.html").read_text(encoding="utf-8")

    assert 'role="treeitem" tabindex' not in text
    toggles = re.findall(r'<button type="button" class="tree-toggle"[^>]*>', text)
    assert toggles, "branch rows need a toggle button"
    for toggle in toggles:
        assert 'aria-expanded=' in toggle
        assert 'aria-controls=' in toggle
        assert 'aria-label=' in toggle


def test_theme_css_supports_dark_mode(built_site):
    """SPEC §29: dark/light follows the system — pin both sides of the theme."""
    _project, dist = built_site
    css = (dist / "assets" / "style.css").read_text(encoding="utf-8")
    assert ":root" in css  # light tokens
    assert "@media (prefers-color-scheme: dark)" in css  # dark variant
