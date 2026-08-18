"""UI V0.1.1 rendering contracts (Owner Decisions UI-D1…UI-D6).

These tests pin the *presentation* promises of this round against a built
site: locale projection, decision ranking and progressive disclosure,
source deduplication, exception-only exception panels, and the guarantee
that nothing here changes planning data.

The fixture below is a synthetic project with three generations of frozen
decisions, a shared source path and a mixed-source group — the shapes that
the real dogfood repository exercises.
"""

from __future__ import annotations

import re

import pytest

from planning_control_plane import generator

SHARED_SOURCE = "docs/governance/very/long/path/Strategy_Document_With_A_Long_Name.md"
OTHER_SOURCE = "docs/governance/other/Second_Source.md"


def _nodes():
    """Root ▸ mid ▸ leaf, plus a blocked sibling and a clean sibling."""
    return [
        {
            "id": "ROOT",
            "title": "Root Program 根节点",
            "type": "PROGRAM",
            "status": "IMPLEMENTING",
            "frozen_decisions": [
                {"id": "FD-ROOT-1", "summary": "Root rule one", "source": SHARED_SOURCE},
                {"id": "FD-ROOT-2", "summary": "Root rule two", "source": OTHER_SOURCE},
            ],
        },
        {
            "id": "MID",
            "title": "Middle Strategy",
            "type": "STRATEGY",
            "parent": "ROOT",
            "status": "DONE",
            "frozen_decisions": [
                {"id": f"FD-MID-{n}", "summary": f"Mid rule {n}", "source": SHARED_SOURCE}
                for n in range(1, 5)
            ],
        },
        {
            "id": "LEAF",
            "title": "Leaf Discussion",
            "type": "DISCUSSION",
            "parent": "MID",
            "status": "NOT_STARTED",
            "objective": "Decide the leaf question.",
            "next_action": "Open the leaf discussion.",
            "scope": ["in one", "in two"],
            "out_of_scope": ["out one"],
            "open_decisions": [{"id": "OD-LEAF-1", "summary": "Still open"}],
            "deferred_decisions": [{"id": "DD-LEAF-1", "summary": "Postponed"}],
            "discussion_status": "IN_PROGRESS",
            "writeback_status": "N/A",
            "last_updated": "2026-08-18",
        },
        {
            "id": "BLOCKED-ONE",
            "title": "Blocked Sibling",
            "parent": "MID",
            "status": "BLOCKED",
            "blocking_decisions": [{"id": "BD-1", "summary": "Needs an owner call"}],
        },
    ]


def _config(locale: str | None, focus: str = "LEAF") -> dict:
    config: dict = {
        "project": {"id": "ui-test", "name": "UI Test 项目"},
        "planning": {"current_focus": focus},
    }
    if locale is not None:
        config["ui"] = {"locale": locale}
    return config


def _build(make_project, tmp_path, locale, nodes=None, focus="LEAF"):
    project, root = make_project(
        tmp_path, config_dict=_config(locale, focus), node_dicts=nodes or _nodes()
    )
    dist = root / ".planning" / "dist"
    generator.build_site(project, dist)
    return dist


@pytest.fixture
def zh_site(make_project, tmp_path):
    room = tmp_path / "zh"
    room.mkdir()
    return _build(make_project, room, "zh-CN")


@pytest.fixture
def en_site(make_project, tmp_path):
    room = tmp_path / "en"
    room.mkdir()
    return _build(make_project, room, None)


def _page(dist, name):
    return (dist / name).read_text(encoding="utf-8")


def _section(text, heading_id):
    match = re.search(rf'<section[^>]*aria-labelledby="{heading_id}".*?</section>', text, re.DOTALL)
    assert match, heading_id
    return match.group(0)


# ------------------------------------------------------------- AC-UI-01/05


def test_html_lang_follows_locale(zh_site, en_site):
    for name in ("index.html", "nodes/LEAF.html"):
        assert '<html lang="zh-CN" data-locale="zh-CN">' in _page(zh_site, name)
        assert '<html lang="en" data-locale="en">' in _page(en_site, name)


def test_chinese_chrome_is_translated(zh_site):
    page = _page(zh_site, "nodes/LEAF.html")
    for label in (
        "下一步行动",
        "目标",
        "范围边界",
        "本轮要做",
        "本轮不做",
        "已冻结决策",
        "恢复这项工作",
        "复制上下文",
    ):
        assert label in page, label
    # V0.1.2 wording fixes really replaced the old terms (spec §12)
    for outdated in ("下一步动作", "范围护栏"):
        assert outdated not in page, outdated


# ---------------------------------------------------------------- UI-D2


def test_ids_and_stored_values_are_never_localized(zh_site):
    """Node ids, decision ids and the capsule stay exactly as stored."""
    page = _page(zh_site, "nodes/LEAF.html")
    for token in ("LEAF", "MID", "ROOT", "OD-LEAF-1", "DD-LEAF-1", "FD-MID-1", "FD-ROOT-1"):
        assert token in page, token
    capsule = re.search(r'<pre id="capsule-text" class="capsule-text">(.*?)</pre>', page, re.DOTALL)
    assert capsule
    body = capsule.group(1)
    assert "=== PCP CONTEXT CAPSULE ===" in body
    assert "NOT_STARTED" in body
    for chinese in ("未开始", "讨论中", "已完成"):
        assert chinese not in body, "the capsule is agent-facing and must stay untranslated"


def test_node_header_and_tracks_show_label_plus_raw_enum(zh_site):
    page = _page(zh_site, "nodes/LEAF.html")
    head = re.search(r'<header class="node-head">.*?</header>', page, re.DOTALL).group(0)
    # since V0.1.2 the localized label is its own element (runtime
    # switching) and the raw chip is always in the document
    for label, key, raw in (
        ("未开始", "status.NOT_STARTED", "NOT_STARTED"),
        ("进行中", "track.IN_PROGRESS", "IN_PROGRESS"),
        ("不适用", "track.NOT_APPLICABLE", "N/A"),
    ):
        assert (
            f'<span data-i18n="{key}">{label}</span> <span class="badge-raw mono">{raw}</span>'
            in head
        ), key
    # the shape is there too: text + shape + colour
    assert '<span class="shape" aria-hidden="true">○</span>' in head


def test_sidebar_and_tables_show_the_label_only(zh_site):
    """UI-D2: compact places carry the localized label, without the enum."""
    page = _page(zh_site, "index.html")
    sidebar = re.search(r'<aside class="sidebar".*?</aside>', page, re.DOTALL).group(0)
    assert '<span class="shape" aria-hidden="true">○</span><span data-i18n="status.NOT_STARTED">未开始</span></span>' in sidebar
    assert "badge-raw" not in sidebar
    # ... but the raw value is still the machine-readable attribute
    assert 'data-status="NOT_STARTED"' in sidebar


# ---------------------------------------------------------------- AC-UI-03


def test_blocking_section_is_absent_when_there_is_nothing_blocking(zh_site):
    page = _page(zh_site, "nodes/LEAF.html")
    assert 'id="blocking-heading"' not in page
    assert "panel--exception" not in page


def test_blocking_section_renders_as_an_exception_when_present(zh_site):
    page = _page(zh_site, "nodes/BLOCKED-ONE.html")
    section = _section(page, "blocking-heading")
    assert "panel--exception" in section
    assert '<span class="exception-icon" aria-hidden="true">▲</span>' in section
    assert "BD-1" in section
    assert '<span class="count">1</span>' in section


def test_dashboard_exception_panel_only_exists_when_something_is_wrong(make_project, tmp_path):
    clean = [node for node in _nodes() if node["id"] != "BLOCKED-ONE"]
    dist = _build(make_project, tmp_path, "zh-CN", nodes=clean)
    page = _page(dist, "index.html")
    assert "panel--exception" not in page
    assert 'id="attention"' not in page
    # the "nothing is blocking" statement rides inside the focus card instead
    assert '<span class="chip chip--ok" data-i18n="dash.no_blockers">无阻塞</span>' in page


def test_dashboard_exception_panel_collects_blocking_and_blocked(zh_site):
    page = _page(zh_site, "index.html")
    attention = re.search(r'<section class="panel panel--exception" id="attention".*?</section>', page, re.DOTALL)
    assert attention
    body = attention.group(0)
    assert "阻塞决策" in body and "BD-1" in body
    assert "阻塞节点" in body and "BLOCKED-ONE" in body
    assert "无阻塞" not in page


# ------------------------------------------------------------ UI-D4 / §30


def test_inherited_groups_disclose_progressively(zh_site):
    """Nearest ancestor expanded, higher ancestors collapsed, counts always
    visible (Owner UI-D4)."""
    section = _section(_page(zh_site, "nodes/LEAF.html"), "frozen-heading")
    groups = re.findall(r"<details class=\"dgroup\"( open)?>.*?</details>", section, re.DOTALL)
    assert len(groups) == 2  # MID (nearest) and ROOT
    assert groups[0] == " open"  # nearest ancestor
    assert groups[1] == ""  # higher ancestor collapsed

    summaries = re.findall(r"<summary>(.*?)</summary>", section, re.DOTALL)
    assert "MID" in summaries[0] and "4 条" in summaries[0]
    assert "ROOT" in summaries[1] and "2 条" in summaries[1]
    # every inherited decision is still in the document, collapsed or not
    for decision_id in ("FD-MID-1", "FD-MID-4", "FD-ROOT-1", "FD-ROOT-2"):
        assert decision_id in section


def test_deferred_decisions_are_collapsed_but_counted(zh_site):
    section = _section(_page(zh_site, "nodes/LEAF.html"), "deferred-heading")
    assert "<details class=\"dgroup\">" in section  # no `open`
    assert "1 条" in section
    assert "DD-LEAF-1" in section


def test_decision_sections_are_ranked(zh_site):
    """Spec §27: blocking, open, own frozen (+ inherited), deferred."""
    page = _page(zh_site, "nodes/BLOCKED-ONE.html")
    order = [
        page.index('id="blocking-heading"'),
        page.index('id="open-heading"'),
        page.index('id="frozen-heading"'),
        page.index('id="deferred-heading"'),
    ]
    assert order == sorted(order)


# ---------------------------------------------------------------- AC-UI-09


def test_a_shared_source_path_is_shown_once_per_group(zh_site):
    section = _section(_page(zh_site, "nodes/LEAF.html"), "frozen-heading")
    mid = re.search(r"<details class=\"dgroup\" open>.*?</details>", section, re.DOTALL).group(0)

    # four decisions, but the path is named exactly once — in the summary
    assert mid.count("FD-MID-") == 4
    assert mid.count(SHARED_SOURCE) == 1
    assert SHARED_SOURCE in re.search(r"<summary>.*?</summary>", mid, re.DOTALL).group(0)
    assert 'class="decision-source"' not in mid


def test_a_mixed_source_group_counts_sources_and_shortens_rows(zh_site):
    section = _section(_page(zh_site, "nodes/LEAF.html"), "frozen-heading")
    root = re.findall(r"<details class=\"dgroup\">.*?</details>", section, re.DOTALL)[0]

    summary = re.search(r"<summary>.*?</summary>", root, re.DOTALL).group(0)
    assert "来源 · 2 处" in summary
    assert SHARED_SOURCE not in summary
    # rows name the basename only, with the full path available on hover
    assert "Strategy_Document_With_A_Long_Name.md</span>" in root
    assert f'title="{SHARED_SOURCE}"' in root


# ------------------------------------------------------------------ AC-UI-02


def test_no_stylesheet_rule_transforms_or_spaces_user_text():
    """User data must reach the page exactly as written (spec §9)."""
    raw = (
        generator._STATIC_DIR / "style.css"  # noqa: SLF001 - asserting on the shipped asset
    ).read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)  # declarations only, not prose
    assert "text-transform" not in css
    assert "letter-spacing" not in css


def test_titles_and_summaries_are_rendered_verbatim(zh_site):
    page = _page(zh_site, "nodes/LEAF.html")
    assert "Leaf Discussion" in page
    assert "Decide the leaf question." in page
    assert "Open the leaf discussion." in page
    assert "in one" in page and "out one" in page
    assert "Still open" in page


# ------------------------------------------------------------ AC-UI-10 / §35


def test_copy_context_is_offered_in_the_node_header_and_the_focus_card(zh_site):
    node_page = _page(zh_site, "nodes/LEAF.html")
    head = re.search(r'<header class="node-head">.*?</header>', node_page, re.DOTALL).group(0)
    assert 'data-copy-from="capsule-text"' in head
    assert "复制上下文" in head
    assert 'data-copy-value="LEAF"' in head

    index = _page(zh_site, "index.html")
    card = re.search(r'<section class="focus-card".*?</section>', index, re.DOTALL).group(0)
    assert 'data-copy-from="focus-capsule"' in card
    assert "复制上下文" in card


def test_resume_panel_reports_capsule_size_and_collapses_the_capsule(zh_site):
    section = _section(_page(zh_site, "nodes/LEAF.html"), "resume-heading")
    assert "恢复这项工作" in section
    assert re.search(r"\d+ 行 · [\d.]+ (KB|B)", section)
    assert '<details class="capsule-details">' in section


# ------------------------------------------------------------ AC-UI-11/12


def test_generation_is_deterministic_per_locale(make_project, tmp_path):
    def files(dist):
        return {p.relative_to(dist).as_posix(): p.read_bytes() for p in sorted(dist.rglob("*")) if p.is_file()}

    first, second, english = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    for path in (first, second, english):
        path.mkdir()

    zh_a = files(_build(make_project, first, "zh-CN"))
    zh_b = files(_build(make_project, second, "zh-CN"))
    en = files(_build(make_project, english, None))

    assert zh_a == zh_b  # same source + same config -> same bytes
    assert sorted(zh_a) == sorted(en)  # the same page set either way
    assert zh_a["index.html"] != en["index.html"]  # ... rendered in another language


def test_ui_preferences_live_only_in_the_browser(zh_site):
    """AC-UI-12 (V0.1.2 reading): browser-side preferences are read at page
    load and written by user action only. The generated pages necessarily
    contain the *mechanism* (boot script + app.js), so what this pins is
    that the only storage keys anywhere are the two preference namespaces
    and that no preference value is ever baked into a build."""
    script = _page(zh_site, "assets/app.js")
    for name in ("index.html", "nodes/LEAF.html"):
        page = _page(zh_site, name)
        keys = set(re.findall(r'"(pcp\.[a-z.]+):', page)) | set(re.findall(r"'(pcp\.[a-z.]+):", page))
        assert keys <= {"pcp.locale"}, (name, keys)
    keys = set(re.findall(r'"(pcp\.[a-z.]+):', script))
    assert keys == {"pcp.tree", "pcp.locale"}


def test_build_check_is_stable_for_a_localized_project(make_project, tmp_path, cli):
    from planning_control_plane.cli import EXIT_OK

    _project, root = make_project(tmp_path, config_dict=_config("zh-CN"), node_dicts=_nodes())
    assert cli("-p", str(root), "build")[0] == EXIT_OK
    code, out, _err = cli("-p", str(root), "build", "--check")
    assert code == EXIT_OK
    assert "dist is up to date" in out
