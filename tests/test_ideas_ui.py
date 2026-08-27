"""Idea layer projection tests (spec: specs/ideas-spec-draft.zh-CN.md, phase 2).

Covers the generated ideas page, the conditional sidebar entry, the
bilingual strings and the phase-2 wording of backward-compatibility
invariant 4.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from planning_control_plane import generator, i18n
from planning_control_plane.model import IdeaStatus, NodeStatus


def test_idea_status_labels_exist_in_both_locales():
    for status in IdeaStatus:
        for locale in i18n.SUPPORTED_LOCALES:
            assert i18n.idea_status_label(locale, status.value)


def test_english_idea_status_labels_are_the_raw_enum():
    """Mirrors status_label: under en the label IS the enum, so the page
    never prints the same value twice (the badge-raw chip is CSS-hidden)."""
    for status in IdeaStatus:
        assert i18n.idea_status_label("en", status.value) == status.value


def test_chinese_idea_status_labels_are_translated_and_distinct():
    labels = {s.value: i18n.idea_status_label("zh-CN", s.value) for s in IdeaStatus}
    for raw, label in labels.items():
        assert label != raw
    assert len(set(labels.values())) == len(labels)


def test_idea_status_key_is_none_outside_the_controlled_enum():
    assert i18n.idea_status_key("OPEN") == "idea_status.OPEN"
    assert i18n.idea_status_key("WISHLIST") is None
    assert i18n.idea_status_label("zh-CN", "WISHLIST") == "WISHLIST"


def test_idea_status_namespace_does_not_collide_with_node_status():
    """Two enums, two namespaces (IDEA-D14). A shared key would let a node
    status re-label an idea badge at runtime, or the reverse."""
    idea_keys = {k for k in i18n.TRANSLATIONS["en"] if k.startswith("idea_status.")}
    assert idea_keys
    for status in IdeaStatus:
        assert i18n.status_key(status.value) is None, status.value
    for status in NodeStatus:
        assert i18n.idea_status_key(status.value) is None, status.value


def test_ideas_page_strings_exist_in_both_locales():
    required = {
        "ideas.nav", "ideas.nav_label", "ideas.title", "ideas.subtitle",
        "ideas.benchmark", "ideas.methodology",
        "ideas.relates_to", "ideas.outcome", "ideas.created", "ideas.updated",
        "ideas.no_sources", "ideas.unknown_node", "ideas.group_count",
    }
    for locale in i18n.SUPPORTED_LOCALES:
        missing = required - set(i18n.TRANSLATIONS[locale])
        assert not missing, (locale, sorted(missing))


# ---------------------------------------------------------- fixtures


IDEA_NODES = [
    {"id": "P1", "title": "Program One", "type": "PROGRAM", "status": "IMPLEMENTING"},
    {"id": "P2", "title": "Phase Two", "type": "PHASE", "status": "READY", "parent": "P1"},
]

IDEA_FILES = {
    "ideas/IDEA-0007.yaml": (
        "id: IDEA-0007\n"
        "title: Trend comparison view 趋势对比\n"
        "status: OPEN\n"
        "detail: One paragraph, no structure required at capture time.\n"
        "relates_to: [P2]\n"
        "benchmark_sources:\n"
        "  - ref: docs/bench.md\n"
        "    note: Grafana time-compare panels\n"
        "  - note: Stripe dashboard month-over-month\n"
        "methodology_sources:\n"
        "  - ref: docs/method.md\n"
        "created: 2026-08-27\n"
        "last_updated: 2026-08-27\n"
    ),
    "ideas/IDEA-0001.yaml": (
        "id: IDEA-0001\ntitle: Stale open idea\nstatus: OPEN\nlast_updated: 2026-01-05\n"
    ),
    "ideas/IDEA-0003.yaml": "id: IDEA-0003\ntitle: Undated idea\nstatus: OPEN\n",
    "ideas/IDEA-0020.yaml": (
        "id: IDEA-0020\ntitle: Parked idea\nstatus: PARKED\nlast_updated: 2026-07-01\n"
    ),
    "ideas/IDEA-0012.yaml": (
        "id: IDEA-0012\n"
        "title: Graduated idea\n"
        "status: PROMOTED\n"
        "outcome:\n"
        "  node: P2\n"
        "  note: pilot is the evidence\n"
        "last_updated: 2026-08-20\n"
    ),
    "ideas/IDEA-0030.yaml": (
        "id: IDEA-0030\ntitle: Discarded idea\nstatus: DISCARDED\nlast_updated: 2026-06-01\n"
    ),
    "ideas/IDEA-DANGLING.yaml": (
        "id: IDEA-DANGLING\ntitle: Dangling relation\nstatus: OPEN\nrelates_to: [NOSUCH]\n"
    ),
}


def _build_with_ideas(make_project, tmp_path, locale=None, name="repo-ideas"):
    room = tmp_path / name
    room.mkdir()
    config = {"project": {"id": "p", "name": "Ideas Project"}, "planning": {"current_focus": "P2"}}
    if locale is not None:
        config["ui"] = {"locale": locale}
    project, root = make_project(
        room,
        config_dict=config,
        node_dicts=IDEA_NODES,
        raw_files=IDEA_FILES,
        repo_files={"docs/bench.md": "b", "docs/method.md": "m"},
    )
    dist = root / ".planning" / "dist"
    generator.build_site(project, dist)
    return dist


@pytest.fixture
def ideas_dist(make_project, tmp_path):
    return _build_with_ideas(make_project, tmp_path)


@pytest.fixture
def ideas_dist_zh(make_project, tmp_path):
    return _build_with_ideas(make_project, tmp_path, "zh-CN", "repo-ideas-zh")


def _page(dist, name):
    return (dist / name).read_text(encoding="utf-8")


# ---------------------------------------------------- ordering source


def test_idea_sort_key_is_shared_by_cli_and_generator():
    """IDEA-D61: one ordering source, so the same data never lists in two
    different orders across the CLI and the page."""
    from planning_control_plane import cli as cli_module
    from planning_control_plane.model import Idea, idea_sort_key

    undated = Idea(id="B", title="b")
    stale = Idea(id="A", title="a", last_updated="2026-01-05")
    fresh = Idea(id="C", title="c", last_updated="2026-08-27")
    assert sorted([undated, fresh, stale], key=idea_sort_key) == [stale, fresh, undated]
    assert cli_module._idea_sort_key is idea_sort_key


# ------------------------------------------------------- the ideas page


def test_ideas_page_is_generated_when_the_project_has_ideas(ideas_dist):
    assert (ideas_dist / "ideas.html").is_file()


def test_ideas_page_groups_statuses_in_the_fixed_order(ideas_dist):
    page = _page(ideas_dist, "ideas.html")
    positions = [page.index(f'data-idea-group="{s}"') for s in ("OPEN", "PARKED", "PROMOTED", "DISCARDED")]
    assert positions == sorted(positions)


def test_ideas_page_orders_each_group_by_the_shared_key(ideas_dist):
    """Stale first, undated last (IDEA-D61) — identical to `pcp ideas`."""
    page = _page(ideas_dist, "ideas.html")
    open_block = page[page.index('data-idea-group="OPEN"'):page.index('data-idea-group="PARKED"')]
    order = re.findall(r'data-idea-id="([^"]+)"', open_block)
    # Undated ties break by id ascending ('0' < 'D'), so IDEA-0003 precedes
    # IDEA-DANGLING — the same order `pcp ideas` prints.
    assert order == ["IDEA-0001", "IDEA-0007", "IDEA-0003", "IDEA-DANGLING"]


def test_ideas_page_shows_every_documented_field(ideas_dist):
    """IDEA-D54: id + status + title, detail, both justification slots
    (ref as text), relates_to and outcome as node links, created/updated."""
    page = _page(ideas_dist, "ideas.html")
    assert "IDEA-0007" in page
    assert "Trend comparison view 趋势对比" in page
    assert "One paragraph, no structure required at capture time." in page
    assert "docs/bench.md" in page                       # ref rendered as text
    assert "Grafana time-compare panels" in page         # note
    assert "Stripe dashboard month-over-month" in page   # note-only entry
    assert "docs/method.md" in page
    assert "2026-08-27" in page
    assert 'href="nodes/P2.html"' in page                # relates_to link
    assert "pilot is the evidence" in page               # outcome note


def test_ideas_page_never_links_a_node_it_did_not_generate(ideas_dist):
    """Mirrors _node_ref: an unknown target stays plain text (no fabricated
    href), so a dangling relates_to can never produce a 404 link."""
    page = _page(ideas_dist, "ideas.html")
    assert "NOSUCH" in page
    assert 'href="nodes/NOSUCH.html"' not in page


def test_ideas_page_ref_is_text_not_a_link(ideas_dist):
    """IDEA-D18/§52.2: PCP describes repository paths, it does not resolve
    them into the generated site."""
    page = _page(ideas_dist, "ideas.html")
    assert 'href="docs/bench.md"' not in page
    assert "docs/bench.md</" in page


def test_ideas_page_shows_localized_label_and_raw_enum(ideas_dist_zh):
    """IDEA-D56: `开放 OPEN` — localized text plus the stored enum."""
    page = _page(ideas_dist_zh, "ideas.html")
    assert 'data-i18n="idea_status.OPEN"' in page
    assert "开放" in page
    assert ">OPEN</span>" in page  # badge-raw chip keeps the enum greppable


def test_ideas_page_does_not_translate_author_data(ideas_dist_zh):
    """IDEA-D56 / LANG-D3: ids, titles, detail and notes are author text."""
    page = _page(ideas_dist_zh, "ideas.html")
    for user_class in ("idea-id", "idea-title", "idea-detail", "idea-source-note", "idea-source-ref"):
        assert not re.search(rf'class="[^"]*{user_class}[^"]*"[^>]*data-i18n=', page), user_class
    assert "Trend comparison view 趋势对比" in page


# ------------------------------------------- IDEA-D63 conditional output


def test_no_ideas_project_gets_no_ideas_page(make_project, tmp_path):
    project, root = make_project(tmp_path, node_dicts=IDEA_NODES)
    dist = root / ".planning" / "dist"
    generator.build_site(project, dist)
    assert not (dist / "ideas.html").exists()


def test_ideas_directory_with_only_broken_files_gets_no_page(make_project, tmp_path):
    """IDEA-D63 keys off the loaded idea set, not off the directory: a
    directory of unparseable files projects nothing."""
    project, root = make_project(
        tmp_path, node_dicts=IDEA_NODES, raw_files={"ideas/broken.yaml": "id: [unclosed\n"}
    )
    assert project.ideas == {}
    dist = root / ".planning" / "dist"
    generator.build_site(project, dist)
    assert not (dist / "ideas.html").exists()


# --------------------------------------------------- IDEA-D55 no overflow


def test_ideas_never_reach_node_pages_or_the_dashboard(ideas_dist):
    """Invariants 1–3 at the projection layer: idea content appears on the
    ideas page and nowhere else."""
    for name in ("index.html", "nodes/P1.html", "nodes/P2.html"):
        page = _page(ideas_dist, name)
        body = re.sub(
            r'<script type="application/json" id="pcp-i18n">.*?</script>', "", page, flags=re.DOTALL
        )
        assert "IDEA-0007" not in body, name
        assert "Trend comparison view" not in body, name
        assert "pilot is the evidence" not in body, name


def test_build_with_ideas_is_deterministic(make_project, tmp_path):
    """Invariant §59.5 extends to the ideas page."""
    first = _build_with_ideas(make_project, tmp_path, name="det-a")
    second = _build_with_ideas(make_project, tmp_path, name="det-b")
    assert _page(first, "ideas.html") == _page(second, "ideas.html")


# ------------------------------------ group-drop, unknown outcome, dedup


def test_ideas_page_drops_empty_groups(make_project, tmp_path):
    """A project whose only idea is OPEN renders exactly one group: groups
    with no members are dropped rather than rendered empty."""
    project, root = make_project(
        tmp_path,
        node_dicts=IDEA_NODES,
        raw_files={"ideas/IDEA-0001.yaml": "id: IDEA-0001\ntitle: Only one\nstatus: OPEN\n"},
    )
    dist = root / ".planning" / "dist"
    generator.build_site(project, dist)
    page = _page(dist, "ideas.html")
    assert re.findall(r'data-idea-group="([^"]+)"', page) == ["OPEN"]


def test_ideas_page_renders_unknown_outcome_as_text(make_project, tmp_path):
    """A PROMOTED idea whose outcome node does not exist keeps the id as
    plain text and the note as text — the generator never fabricates a
    link for a page it did not write."""
    project, root = make_project(
        tmp_path,
        node_dicts=IDEA_NODES,
        raw_files={
            "ideas/IDEA-0042.yaml": (
                "id: IDEA-0042\n"
                "title: Graduated into a missing node\n"
                "status: PROMOTED\n"
                "outcome:\n"
                "  node: NOSUCH\n"
                "  note: graduation target vanished\n"
            ),
        },
    )
    dist = root / ".planning" / "dist"
    generator.build_site(project, dist)
    page = _page(dist, "ideas.html")
    assert "NOSUCH" in page
    assert 'href="nodes/NOSUCH.html"' not in page
    assert "graduation target vanished" in page


def test_ideas_page_dedupes_repeated_relates_to(make_project, tmp_path):
    """``relates_to: [P2, P2]`` renders one link, not two."""
    project, root = make_project(
        tmp_path,
        node_dicts=IDEA_NODES,
        raw_files={
            "ideas/IDEA-0009.yaml": (
                "id: IDEA-0009\ntitle: Repeated relation\nstatus: OPEN\nrelates_to: [P2, P2]\n"
            ),
        },
    )
    dist = root / ".planning" / "dist"
    generator.build_site(project, dist)
    page = _page(dist, "ideas.html")
    # `idea-node-link` appears only in the ideas content (the sidebar tree
    # uses its own link classes), so a page-wide findall pins the card.
    assert re.findall(r'class="idea-node-link" href="([^"]+)"', page) == ["nodes/P2.html"]


# ------------------------------------------------- IDEA-D54 sidebar entry


def test_sidebar_entry_appears_on_every_page_of_an_ideas_project(ideas_dist):
    for name in ("index.html", "ideas.html", "nodes/P1.html"):
        page = _page(ideas_dist, name)
        assert 'class="sidebar-extra"' in page, name
        assert 'data-i18n="ideas.nav"' in page, name


def test_sidebar_entry_sits_outside_the_planning_tree(ideas_dist):
    """IDEA-D54: a separate section, not a tree node — the sidebar tree
    stays the planning graph and nothing else (invariant 3)."""
    page = _page(ideas_dist, "index.html")
    nav_start = page.index('<nav class="sidebar-nav"')
    nav_end = page.index("</nav>", nav_start)
    tree_nav = page[nav_start:nav_end]
    assert "sidebar-extra" not in tree_nav
    # ... and the entry lives in the gap between that nav's close and the
    # aside's — after the tree, still inside the sidebar.
    assert nav_end < page.index('class="sidebar-extra"') < page.index("</aside>")


def test_sidebar_entry_carries_no_count_badge(ideas_dist):
    """IDEA-D54: MVP has no count badge on the entry."""
    page = _page(ideas_dist, "index.html")
    entry = page[page.index('class="sidebar-extra"'):]
    entry = entry[: entry.index("</nav>")]
    # Tags are stripped first: the raw markup must keep its house-convention
    # i18n hooks, and the attribute *name* ``data-i18n`` itself carries the
    # digits "18" — a badge would be visible text, so that is what is checked.
    # The slice starts mid-tag (at the nav's class attribute), so the nav's
    # own opening tag is cut at its closing bracket first.
    inner = entry[entry.index(">") + 1:]
    visible = re.sub(r"<[^>]+>", "", inner)
    assert not re.search(r"\d", visible)


def test_ideas_page_marks_its_own_sidebar_entry_as_current(ideas_dist):
    page = _page(ideas_dist, "ideas.html")
    assert re.search(r'class="sidebar-extra-link"[^>]*aria-current="page"', page)
    assert 'href="index.html" aria-current="page"' not in page  # topbar Overview is not current


# ------------------------------ invariant §59.4 phase 2: no-ideas projects


@pytest.fixture
def plain_dist(demo_root, tmp_path):
    """The shipped demo project — seven nodes, no ideas/ directory."""
    from planning_control_plane.loader import load_project

    project = load_project(demo_root)
    dist = tmp_path / "plain-dist"
    generator.build_site(project, dist)
    return dist


def test_no_ideas_project_keeps_the_exact_phase1_file_list(plain_dist):
    """'No new page' in its literal, checkable form."""
    files = sorted(p.relative_to(plain_dist).as_posix() for p in plain_dist.rglob("*") if p.is_file())
    assert files == [
        "assets/app.js",
        "assets/style.css",
        "index.html",
        "nodes/P1.html",
        "nodes/P2-A.html",
        "nodes/P2-A1.html",
        "nodes/P2-A2.html",
        "nodes/P2-A3.html",
        "nodes/P2-A4.html",
        "nodes/P2.html",
    ]


def test_no_ideas_pages_contain_no_idea_markup_outside_the_payload(plain_dist):
    """'No new navigation entry, no new visible content' — the i18n payload
    is the one allowed increment (invariant §59.4 phase 2), so it is cut out
    before the check."""
    for path in sorted(plain_dist.rglob("*.html")):
        page = path.read_text(encoding="utf-8")
        body = re.sub(
            r'<script type="application/json" id="pcp-i18n">.*?</script>', "", page, flags=re.DOTALL
        )
        lowered = body.lower()
        assert "idea" not in lowered, (
            path.name,
            re.findall(r".{0,30}idea.{0,30}", lowered)[:3],
        )


#: Header comment of the idea-layer block in style.css. Both CSS gates
#: below key off it; the asserts guard the lookup so a reworded marker
#: reads as a gate failure, not a ValueError.
_IDEA_LAYER_MARKER = "/* ----------------------------------------------------------- idea layer */"


def test_idea_css_cannot_restyle_pages_that_have_no_ideas(plain_dist):
    """style.css is a shared asset, so the idea rules ship to every project.
    They are inert there only if every selector is namespaced — this pins
    that, so a future edit cannot silently restyle existing pages.

    The gate polices marker-to-EOF: a later, unrelated feature that
    appends CSS after the idea block will trip it. That is deliberate —
    the friction forces a conscious fixture/gate update, never silent drift.
    """
    css = (plain_dist / "assets" / "style.css").read_text(encoding="utf-8")
    assert _IDEA_LAYER_MARKER in css
    block = css[css.index(_IDEA_LAYER_MARKER):]

    # Comments are stripped first, so comment prose can neither pose as a
    # selector nor hide one. What remains is plain rules, and a selector
    # run is *everything* between the previous `}` and the next `{` (plus
    # the prefix before the very first `{`) — which, unlike a line-anchored
    # regex, also sees `#id` selectors, `:not()`/`:is()`-style parentheses
    # and every line of a multi-line selector group. At-rules are rejected
    # wholesale before that: the idea layer styles with the existing tokens
    # (already redefined under the phase-1 dark-mode `@media`), so needing
    # one would mean a hard-coded colour — exactly when a review should
    # happen.
    rules = re.sub(r"/\*.*?\*/", "", block, flags=re.DOTALL)
    assert not re.search(r"^\s*@", rules, flags=re.MULTILINE), "at-rule in the idea layer"

    selectors = re.findall(r"\}([^{}]*)\{", rules)
    if "{" in rules:
        selectors.insert(0, rules[: rules.index("{")])
    for selector in selectors:
        for part in selector.split(","):
            part = part.strip()
            if part:
                assert part.startswith((".idea-", ".ideas-", ".sidebar-extra")), part


def test_idea_css_is_append_only_over_phase1(plain_dist):
    """The prefix check above proves new rules stay inert; this proves no
    *existing* rule was rewritten. Together they are 'append only'.

    The fixture is the phase-1 stylesheet captured byte-for-byte from
    ``main``. It is not frozen forever: a later, unrelated UI change may
    legitimately edit existing rules — but it must then update this fixture
    **in its own commit**, which is precisely the visibility this gate
    exists to force. What it must never do is drift silently as a
    side effect of idea-layer work.
    """
    built = (plain_dist / "assets" / "style.css").read_bytes()
    phase1 = (Path(__file__).parent / "fixtures" / "phase1_style.css").read_bytes()
    marker = _IDEA_LAYER_MARKER.encode()
    assert marker in built
    # Every byte is pinned by exactly one gate: the head below must be the
    # phase-1 sheet plus the single newline that separates it from the idea
    # layer — a bare ``startswith(phase1)`` would leave that one-byte gap
    # unchecked — and everything from the marker on belongs to the
    # selector/at-rule gate in the test above.
    assert built[: built.index(marker)] == phase1 + b"\n"
