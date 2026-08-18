"""Contracts for the public Chinese demo repository (``examples/demo-project-zh``).

The Chinese demo exists because the runtime language switch localizes PCP's
*interface* only — it never translates planning content (LANG-D3). A Chinese
screenshot therefore needs Chinese planning data, not an English demo viewed
through a Chinese UI. These tests pin what the public demo must stay:

* it validates clean and rebuilds deterministically, exactly like the English
  demo (so ``pcp build --check`` in the release checklist is meaningful);
* it defaults to ``zh-CN`` and renders Chinese planning content;
* it stays generic — no real project, product, or internal path leaks into a
  repository that ships public screenshots.
"""

from __future__ import annotations

import re

import pytest

from planning_control_plane import generator
from planning_control_plane.cli import EXIT_OK
from planning_control_plane.loader import load_project
from planning_control_plane.validator import validate_project

ZH_NODE_IDS = ["P1", "P2", "P2-A", "P2-A1", "P2-A2", "P2-A3", "P2-A4"]

#: Titles the public demo tree is expected to carry (final polish §7).
ZH_TITLES = {
    "P1": "规划基础",
    "P2": "产品推广",
    "P2-A": "推广策略",
    "P2-A1": "调研现有推广文档",
    "P2-A2": "定义推广就绪标准",
    "P2-A3": "冻结推广顺序",
    "P2-A4": "推广就绪度预检",
}


@pytest.fixture
def zh_site(demo_zh_root, tmp_path):
    """Build the Chinese demo into a temp dir; the demo itself stays read-only."""
    project = load_project(demo_zh_root)
    dist = tmp_path / "dist"
    generator.build_site(project, dist)
    return project, dist


# ------------------------------------------------------------------ data


def test_demo_zh_validates_clean(demo_zh_root, cli):
    code, out, err = cli("-p", str(demo_zh_root), "validate")
    assert code == EXIT_OK, (out, err)
    assert not validate_project(load_project(demo_zh_root))


def test_demo_zh_tree_matches_the_documented_shape(demo_zh_root):
    project = load_project(demo_zh_root)
    assert project.sorted_node_ids() == ZH_NODE_IDS
    assert {node_id: project.nodes[node_id].title for node_id in ZH_NODE_IDS} == ZH_TITLES
    assert project.config.current_focus == "P2-A4"
    assert project.config.ui.locale == "zh-CN"


def test_demo_zh_focus_node_carries_every_section_the_dashboard_shows(demo_zh_root):
    """§7: the focus node must exercise objective, next action, scope,
    frozen/open/blocking decisions, dependencies and the three tracks —
    otherwise the public screenshot shows empty panels."""
    node = load_project(demo_zh_root).nodes["P2-A4"]
    assert node.objective and node.next_action
    assert node.scope and node.out_of_scope
    assert node.open_decisions and node.blocking_decisions
    assert node.depends_on == ["P2-A3"]
    assert node.discussion_status and node.writeback_status and node.implementation_status
    # inherited frozen decisions come from the ancestors
    ancestors = load_project(demo_zh_root)
    assert ancestors.nodes["P2-A"].frozen_decisions
    assert ancestors.nodes["P2"].frozen_decisions
    assert ancestors.nodes["P1"].frozen_decisions


def test_demo_zh_stays_generic(demo_zh_root):
    """§8: a repository that ships public screenshots must not carry real
    project names, real internal paths or real business rules."""
    forbidden = ("zhixiaoyun", "知效云", "/home/", "C:\\Users")
    for path in sorted(demo_zh_root.rglob("*")):
        if not path.is_file() or ".planning/dist" in path.as_posix():
            continue
        text = path.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in text, (path, needle)


# ------------------------------------------------------------------ build


def test_demo_zh_builds_deterministically(demo_zh_root, tmp_path):
    project = load_project(demo_zh_root)
    first, second = tmp_path / "a", tmp_path / "b"
    generator.build_site(project, first)
    generator.build_site(project, second)

    def files(root):
        return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}

    assert files(first) == files(second)
    assert sorted(files(first)) == sorted(
        ["index.html", "assets/style.css", "assets/app.js", *[f"nodes/{n}.html" for n in ZH_NODE_IDS]]
    )


def test_demo_zh_pages_default_to_chinese_ui(zh_site):
    _project, dist = zh_site
    for page in ("index.html", "nodes/P2-A4.html"):
        text = (dist / page).read_text(encoding="utf-8")
        assert '<html lang="zh-CN" data-locale="zh-CN">' in text, page
        assert ">总览</a>" in text, page  # the topbar Overview entry


def test_demo_zh_planning_content_is_chinese_and_untranslated(zh_site):
    """LANG-AC-09 / VIS-AC-06: the Chinese screenshot gets its Chinese text
    from the planning data, never from a runtime translation of user text."""
    _project, dist = zh_site
    text = (dist / "nodes" / "P2-A4.html").read_text(encoding="utf-8")

    assert '<span class="node-title">推广就绪度预检</span>' in text
    for sentence in ("先和门禁负责人裁决 BD-401", "第一批领域的就绪度核对"):
        assert sentence in text, sentence
    # user text carries no translation key in any locale
    for user_class in ("tree-title", "prose", "decision-summary", "scope-list", "node-title"):
        assert not re.search(rf'class="{user_class}"[^>]*data-i18n', text), user_class
