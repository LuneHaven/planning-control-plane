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
    _project, dist = built_site
    text = (dist / "nodes" / "P2-A2.html").read_text(encoding="utf-8")

    match = re.search(r'<nav class="breadcrumb".*?</nav>', text, re.DOTALL)
    assert match, "breadcrumb nav missing"
    breadcrumb = match.group(0)

    # crumbs read Program > Phase > Strategy > node, root first
    crumbs = re.findall(r'<(?:a|span) class="mono"[^>]*>([^<]+)</(?:a|span)>', breadcrumb)
    assert crumbs == ["P1", "P2", "P2-A", "P2-A2"]
    # every non-current crumb is a link, the current one is marked
    assert 'aria-current="page"' in breadcrumb
    assert len(re.findall(r'<a class="mono" href="\.\./nodes/', breadcrumb)) == 3


def test_node_page_copy_context_button_has_aria_label(built_site):
    _project, dist = built_site
    text = (dist / "nodes" / "P2-A4.html").read_text(encoding="utf-8")

    button = re.search(r'<button[^>]*class="copy-context"[^>]*>', text)
    assert button, "Copy Context button missing"
    assert "Copy Context</button>" in text
    assert re.search(r'aria-label="[^"]+"', button.group(0))
    # the clipboard fallback is a labelled, read-only textarea
    assert re.search(r'<textarea readonly aria-label="[^"]+">', text)


def test_node_page_embeds_capsule_matching_cli(demo_root, built_site, capsys):
    """The 'Resume This Work' capsule equals ``pcp context <node>`` output."""
    from planning_control_plane import cli

    _project, dist = built_site
    page = (dist / "nodes" / "P2-A4.html").read_text(encoding="utf-8")

    match = re.search(r'<pre class="capsule-text">(.*?)</pre>', page, re.DOTALL)
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
    # FD-001 is displayed as inherited, grouped by ancestor
    assert "Inherited from" in text
    assert "FD-101" in text  # frozen at P2
    assert "FD-001" in text  # frozen at P1


def test_node_page_track_status_shows_na(built_site):
    _project, dist = built_site
    text = (dist / "nodes" / "P2-A4.html").read_text(encoding="utf-8")

    # P2-A4: discussion NOT_STARTED, writeback N/A, implementation N/A
    assert re.search(r"<dt>Discussion</dt><dd><span class=\"track-badge\">NOT_STARTED</span>", text)
    assert re.search(r"<dt>Writeback</dt><dd><span class=\"track-badge\">N/A</span>", text)
    assert re.search(r"<dt>Implementation</dt><dd><span class=\"track-badge\">N/A</span>", text)


# --------------------------------------------------------------- dashboard


def test_dashboard_shows_focus_tree_progress_blocking_queue(built_site):
    _project, dist = built_site
    text = (dist / "index.html").read_text(encoding="utf-8")

    # section headings (spec §24)
    for heading in ("Current Focus", "Planning Tree", "Progress Summary", "Blocking Decisions", "Recently Updated", "Next Queue"):
        assert heading in text, heading

    # current focus panel: node, status, next action
    assert "P2-A4" in text
    assert "Rollout Readiness Preflight" in text
    assert "NOT_STARTED" in text
    assert "Resolve BD-401" in text

    # the phase of the focus (P2) is shown
    assert "Current Phase" in text

    # progress numbers: total 7, done 4, blocked 0, pending 1 (planning only)
    assert '<span class="stat-value">7</span>' in text
    assert '<span class="stat-value">4</span>' in text
    assert '<span class="stat-value">0</span>' in text
    assert "not product or engineering completion" in text

    # blocking decisions are collected in one table
    assert "BD-401" in text

    # next queue: P2-A4 is the one ready node
    assert "Next Queue" in text
    queue = re.search(r'id="queue-heading".*?</section>', text, re.DOTALL).group(0)
    assert "P2-A4" in queue

    # recently updated sorts by date, newest first
    recent = re.search(r'id="recent-heading".*?</section>', text, re.DOTALL).group(0)
    dates = re.findall(r'<td class="mono nowrap">([^<]+)</td>', recent)
    assert dates == sorted(dates, reverse=True)
    assert dates[0] == "2026-08-17"  # P2-A4 is the most recently updated


def test_dashboard_tree_marks_current_focus(built_site):
    _project, dist = built_site
    text = (dist / "index.html").read_text(encoding="utf-8")
    focus_item = re.search(r'<li role="treeitem"[^>]*class="[^"]*is-focus[^"]*"', text)
    assert focus_item
    # The focus marker must be visible text, not colour-only (spec §29):
    # pin the rendered <span class="focus-flag">…focus…</span> element itself.
    assert re.search(r'class="focus-flag"[^>]*>\s*focus\s*<', text)


def test_theme_css_supports_dark_mode(built_site):
    """SPEC §29: dark/light follows the system — pin both sides of the theme."""
    _project, dist = built_site
    css = (dist / "assets" / "style.css").read_text(encoding="utf-8")
    assert ":root" in css  # light tokens
    assert "@media (prefers-color-scheme: dark)" in css  # dark variant
