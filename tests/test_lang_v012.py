"""Runtime language switching contracts (V0.1.2, Owner LANG-D1…LANG-D6).

These tests pin the *mechanism* of the in-browser locale switch against the
generated output: the embedded payload must be the Python translation table
verbatim (single source), every ``data-i18n`` key stamped by the templates
must exist in that payload, the boot script and the switcher must agree on
the ``localStorage`` key, and nothing that is planning data — ids, stored
enums, user text, the capsule — may carry a translation key.

The behavioural half of the acceptance list (LANG-AC-03/04/05: click,
refresh, navigate) is exercised against the same files over ``file://`` in
a real browser as part of the release checklist; what Python can prove is
that the shipped files contain everything the browser needs and nothing it
must not touch.
"""

from __future__ import annotations

import json
import re

import pytest

from planning_control_plane import generator, i18n

# ---------------------------------------------------------------- fixtures


def _nodes():
    return [
        {
            "id": "ROOT",
            "title": "Root Program 根节点",
            "type": "PROGRAM",
            "status": "IMPLEMENTING",
            "frozen_decisions": [
                {"id": "FD-ROOT-1", "summary": "Root rule one", "source": "docs/gov/one.md"},
                {"id": "FD-ROOT-2", "summary": "Root rule two", "source": "docs/gov/two.md"},
            ],
        },
        {
            "id": "LEAF",
            "title": "Leaf Discussion",
            "type": "DISCUSSION",
            "parent": "ROOT",
            "status": "NOT_STARTED",
            "objective": "Decide the leaf question.",
            "next_action": "Open the leaf discussion.",
            "scope": ["in one"],
            "out_of_scope": ["out one"],
            "open_decisions": [{"id": "OD-LEAF-1", "summary": "Still open"}],
            "blocking_decisions": [{"id": "BD-1", "summary": "Needs an owner call"}],
            "deferred_decisions": [{"id": "DD-LEAF-1", "summary": "Postponed"}],
            "discussion_status": "IN_PROGRESS",
            "writeback_status": "N/A",
            "last_updated": "2026-08-18",
        },
    ]


def _config(locale: str | None) -> dict:
    config: dict = {
        "project": {"id": "lang-test", "name": "Lang Test 项目"},
        "planning": {"current_focus": "LEAF"},
    }
    if locale is not None:
        config["ui"] = {"locale": locale}
    return config


def _build(make_project, tmp_path, locale, name):
    room = tmp_path / name
    room.mkdir()
    project, root = make_project(room, config_dict=_config(locale), node_dicts=_nodes())
    dist = root / ".planning" / "dist"
    generator.build_site(project, dist)
    return dist


@pytest.fixture
def en_dist(make_project, tmp_path):
    return _build(make_project, tmp_path, None, "repo-en")


@pytest.fixture
def zh_dist(make_project, tmp_path):
    return _build(make_project, tmp_path, "zh-CN", "repo-zh")


def _page(dist, name):
    return (dist / name).read_text(encoding="utf-8")


def _files(dist):
    return {
        p.relative_to(dist).as_posix(): p.read_bytes()
        for p in sorted(dist.rglob("*"))
        if p.is_file()
    }


def _payload(page):
    match = re.search(
        r'<script type="application/json" id="pcp-i18n">(.*?)</script>', page, re.DOTALL
    )
    assert match, "i18n payload missing"
    return json.loads(match.group(1))


ALL_PAGES = ("index.html", "nodes/LEAF.html")


# ------------------------------------------------- LANG-AC-01/02: defaults


def test_without_ui_config_the_default_locale_is_english(en_dist):
    """LANG-AC-01: no config → build locale and payload default are ``en``."""
    for name in ALL_PAGES:
        page = _page(en_dist, name)
        assert '<html lang="en" data-locale="en">' in page, name
        assert _payload(page)["default"] == "en"


def test_project_locale_is_the_build_default(zh_dist):
    """LANG-AC-02: ``ui.locale: zh-CN`` renders zh-CN and defaults to it."""
    for name in ALL_PAGES:
        page = _page(zh_dist, name)
        assert '<html lang="zh-CN" data-locale="zh-CN">' in page, name
        assert _payload(page)["default"] == "zh-CN"


# --------------------------------------------- LANG-AC-03: switch = no build


def test_every_page_ships_both_locale_tables(en_dist, zh_dist):
    """LANG-AC-03: switching locales in the browser needs no rebuild, so the
    *other* locale's full table must already be embedded in every page."""
    for dist in (en_dist, zh_dist):
        for name in ALL_PAGES:
            payload = _payload(_page(dist, name))
            assert payload["locales"] == ["en", "zh-CN"]
            assert payload["messages"]["en"] == i18n.TRANSLATIONS["en"]
            assert payload["messages"]["zh-CN"] == i18n.TRANSLATIONS["zh-CN"]


def test_runtime_payload_is_the_python_table_verbatim():
    """Single translation source: the payload is generated from the same
    dictionaries that rendered the page — no second JS-side truth."""
    for locale in ("en", "zh-CN"):
        payload = i18n.runtime_payload(locale)
        assert payload["messages"] == {
            "en": i18n.TRANSLATIONS["en"],
            "zh-CN": i18n.TRANSLATIONS["zh-CN"],
        }


# ------------------------------- LANG-AC-04/05/06: persistence and fallback


def test_boot_script_applies_a_stored_preference_before_first_paint(zh_dist):
    """A tiny inline script in <head> reads the same key app.js uses, so
    the very first paint already honours the stored preference (LANG-AC-04)
    and node pages resolve to the same key as the dashboard (LANG-AC-05)."""
    for name in ALL_PAGES:
        page = _page(zh_dist, name)
        head = re.search(r"<head>.*?</head>", page, re.DOTALL).group(0)
        assert "pcp.locale:" in head, f"boot script missing in {name}"
        assert 'root.setAttribute("data-locale", pref)' in head
        # runs before the stylesheet, i.e. before first paint
        assert head.index("<script>") < head.index('rel="stylesheet"')
        # only the two shipped locales can override the build locale
        assert 'pref === "en" || pref === "zh-CN"' in head
        # anything else (including a cleared preference) keeps the default
        assert 'data-locale="zh-CN"' in page


def test_app_js_shares_the_storage_key_and_strips_the_nodes_level(zh_dist):
    script = _page(zh_dist, "assets/app.js")
    assert '"pcp.locale:"' in script
    assert '"pcp.tree:"' in script
    # node pages live one directory down; both keys must collapse to the
    # site root so navigation keeps the preference (LANG-AC-05)
    assert "nodes\\/$" in script
    # the fallback order is stored preference -> project default
    assert "readStoredLocale() || i18n.default" in script


def test_the_preference_is_scoped_per_site(en_dist):
    """LANG persistence rule: the key embeds the site path, so a second
    project opened from the same origin cannot be polluted."""
    head = re.search(r"<head>.*?</head>", _page(en_dist, "index.html"), re.DOTALL).group(0)
    assert '"pcp.locale:" + location.pathname' in head


# ------------------------------------------------- LANG-AC-07: html lang


def test_switch_updates_the_document_language_attribute(zh_dist):
    script = _page(zh_dist, "assets/app.js")
    assert "root.lang = locale;" in script
    assert 'root.setAttribute("data-locale", locale)' in script


# -------------------------- LANG-AC-08/09: data is never translated


def test_technical_identifiers_carry_no_translation_keys(zh_dist):
    """LANG-AC-08: node ids, decision ids and stored enum values stay raw."""
    page = _page(zh_dist, "nodes/LEAF.html")

    # machine-facing containers must not be re-labeled at runtime
    for raw_class in ("tree-id", "decision-id", "node-id", "type-chip", "capsule-text", "crumb-title"):
        assert not re.search(rf'class="{raw_class}"[^>]*data-i18n', page), raw_class
        assert not re.search(rf'data-i18n="[^"]*"[^>]*class="{raw_class}"', page), raw_class

    # the raw enums remain searchable, in attributes and in badge chips
    assert 'data-status="NOT_STARTED"' in page
    assert ">NOT_STARTED</span>" in page  # badge-raw chip
    assert ">IN_PROGRESS</span>" in page
    assert ">N/A</span>" in page


def test_user_planning_text_carries_no_translation_keys(zh_dist):
    """LANG-AC-09: titles, objective, next action and scope items are user
    data — PCP never translates them in any locale."""
    page = _page(zh_dist, "nodes/LEAF.html")
    for user_class in ("tree-title", "prose", "decision-summary", "scope-list", "focus-node-title"):
        assert not re.search(rf'class="{user_class}"[^>]*data-i18n', page), user_class
    for sentence in ("Leaf Discussion", "Decide the leaf question.", "Open the leaf discussion.", "in one", "out one"):
        assert sentence in page, sentence


def test_the_capsule_stays_agent_facing_and_untranslated(zh_dist):
    page = _page(zh_dist, "nodes/LEAF.html")
    capsule = re.search(r'<pre id="capsule-text" class="capsule-text">(.*?)</pre>', page, re.DOTALL)
    assert capsule
    assert "data-i18n" not in capsule.group(0)
    assert "=== PCP CONTEXT CAPSULE ===" in capsule.group(1)


# ------------------------------------------ template keys actually resolve


def test_every_marked_key_and_attribute_key_exists_in_the_payload(en_dist, zh_dist):
    """A template typo would blank a label at runtime (the translator
    degrades to the key string). Every key the pages stamp must resolve in
    *both* locale tables, and every ``data-i18n-args`` blob must be valid
    JSON covering the translation's placeholders."""
    for dist in (en_dist, zh_dist):
        for name in ALL_PAGES:
            page = _page(dist, name)

            keys = set(re.findall(r'data-i18n="([^"]+)"', page))
            keys |= {
                key.strip()
                for spec in re.findall(r'data-i18n-attr="([^"]+)"', page)
                for pair in spec.split(";")
                for key in [pair.split("=")[-1].strip()]
            }
            assert keys, "no translation markup found"
            for key in sorted(keys):
                assert key in i18n.TRANSLATIONS["en"], (name, key)
                assert key in i18n.TRANSLATIONS["zh-CN"], (name, key)

            for element in re.finditer(r'data-i18n="([^"]+)"[^>]*data-i18n-args=\'([^\']*)\'', page):
                key, raw_args = element.group(1), element.group(2)
                args = json.loads(raw_args)
                placeholders = set(
                    re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", i18n.TRANSLATIONS["en"][key])
                )
                assert placeholders <= set(args), (name, key, placeholders, set(args))


# ---------------------------------------------------- the switcher control


def test_the_language_switcher_is_progressive_enhancement(zh_dist):
    """The control is hidden until app.js runs (without JavaScript it would
    do nothing), is a real button group with per-locale `lang` attributes,
    and reports its state through aria-pressed."""
    page = _page(zh_dist, "index.html")
    switch = re.search(r'<div class="lang-switch".*?</div>\s*</div>', page, re.DOTALL)
    assert switch, "language switcher missing"
    markup = switch.group(0)
    assert "hidden" in markup
    assert 'role="group"' in markup
    assert 'data-i18n-attr="aria-label=lang.label"' in markup
    assert markup.count('class="lang-btn"') == 2
    assert 'data-set-locale="en"' in markup and 'lang="en"' in markup
    assert 'data-set-locale="zh-CN"' in markup and 'lang="zh-CN"' in markup
    # endonyms are fixed text, never translated
    assert ">English</button>" in markup and ">中文</button>" in markup


def test_the_stylesheet_hides_raw_chips_only_under_english(zh_dist):
    """Detailed badges always carry the raw chip; `en` hides the duplicate
    (the label already is the raw enum) through the data-locale attribute
    the boot script and app.js maintain."""
    css = _page(zh_dist, "assets/style.css")
    assert 'html[data-locale="en"] .badge-raw' in css
    assert ".lang-btn" in css


def test_the_boot_scripts_locale_whitelist_matches_the_shipped_locales(en_dist):
    """The inline boot script cannot read the payload cheaply, so it repeats
    the locale ids. If a locale is ever added, that whitelist must follow —
    this test fails until it does."""
    head = re.search(r"<head>.*?</head>", _page(en_dist, "index.html"), re.DOTALL).group(0)
    for locale in i18n.SUPPORTED_LOCALES:
        assert f'pref === "{locale}"' in head, locale
    quoted = re.findall(r'pref === "([a-zA-Z-]+)"', head)
    assert sorted(quoted) == sorted(i18n.SUPPORTED_LOCALES)


# ------------------------------------------------- LANG-AC-10: determinism


def test_a_runtime_switch_can_never_change_the_generated_files(make_project, tmp_path, cli):
    """LANG-AC-10 / LANG-D4: the preference lives in the browser only. Two
    builds of the same source stay byte-identical and ``pcp build --check``
    passes — a browser session cannot write anything the check would see."""
    from planning_control_plane.cli import EXIT_OK

    first = _build(make_project, tmp_path, "zh-CN", "a")
    second = _build(make_project, tmp_path, "zh-CN", "b")
    assert _files(first) == _files(second)

    room = tmp_path / "c"
    room.mkdir()
    _project, root = make_project(room, config_dict=_config("zh-CN"), node_dicts=_nodes())
    assert cli("-p", str(root), "build")[0] == EXIT_OK
    code, out, _err = cli("-p", str(root), "build", "--check")
    assert code == EXIT_OK
    assert "dist is up to date" in out


# ------------------------------------------------- zh-CN terminology (§12)


def test_chinese_terminology_matches_the_public_glossary():
    zh = i18n.TRANSLATIONS["zh-CN"]
    assert zh["node.next_action"] == "下一步行动"
    assert zh["node.next_action.empty"] == "未记录下一步行动。"
    assert zh["node.scope"] == "范围边界"
    assert zh["node.decisions.frozen"] == "已冻结决策"
    # terms this round explicitly keeps
    for key, expected in (
        ("node.scope.in", "本轮要做"),
        ("node.scope.out", "本轮不做"),
        ("dash.focus", "当前焦点"),
        ("dash.attention.blocking", "阻塞决策"),
        ("node.resume", "恢复这项工作"),
        ("action.copy_context", "复制上下文"),
    ):
        assert zh[key] == expected, key
    for outdated in ("下一步动作", "范围护栏"):
        assert outdated not in "".join(zh.values())
    assert i18n.TRANSLATIONS["en"]["node.scope"] == "Scope Boundary"
