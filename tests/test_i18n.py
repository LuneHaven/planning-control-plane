"""Locale layer contracts (UI V0.1.1, Owner Decisions UI-D1 / UI-D2).

The locale is an explicit UI projection configuration: it selects the
language of the generated HTML and nothing else. These tests pin that
boundary from both sides — the ``ui.locale`` config path, and the promise
that planning data, CLI output and context capsules never change with it.
"""

from __future__ import annotations

from planning_control_plane import i18n
from planning_control_plane.cli import EXIT_OK
from planning_control_plane.model import NodeStatus, TrackStatus


# ------------------------------------------------------------- the tables


def test_locales_have_identical_key_sets():
    """AC-UI-06: en and zh-CN must translate exactly the same keys."""
    en = set(i18n.TRANSLATIONS["en"])
    zh = set(i18n.TRANSLATIONS["zh-CN"])
    assert en == zh, {"only in en": sorted(en - zh), "only in zh-CN": sorted(zh - en)}
    assert set(i18n.TRANSLATIONS) == set(i18n.SUPPORTED_LOCALES)


def test_no_translation_value_is_empty():
    for locale, table in i18n.TRANSLATIONS.items():
        for key, value in table.items():
            assert value.strip(), f"{locale}:{key} is empty"


def test_every_status_and_track_enum_has_a_label():
    """Spec §12: all 11 overall statuses and all 4 track statuses."""
    for locale in i18n.SUPPORTED_LOCALES:
        for status in NodeStatus:
            assert i18n.status_label(locale, status.value)
        for track in TrackStatus:
            assert i18n.track_label(locale, track.value)


def test_english_labels_are_the_raw_enum_values():
    """en keeps the V0.1 wording, so a page never prints a value twice."""
    for status in NodeStatus:
        assert i18n.status_label("en", status.value) == status.value


def test_chinese_labels_differ_from_the_enum_and_are_distinct():
    labels = {status.value: i18n.status_label("zh-CN", status.value) for status in NodeStatus}
    for raw, label in labels.items():
        assert label != raw
    assert len(set(labels.values())) == len(labels)  # no two statuses share a label


def test_every_status_has_its_own_shape_and_shapes_are_locale_independent():
    """Spec §13: text + shape + colour, and the shape never depends on locale."""
    for status in NodeStatus:
        assert i18n.status_shape(status.value) in {"○", "◐", "●", "▲", "◇"}
    assert i18n.status_shape(NodeStatus.DONE.value) == "●"
    assert i18n.status_shape(NodeStatus.BLOCKED.value) == "▲"
    assert i18n.status_shape(NodeStatus.NOT_STARTED.value) == "○"
    assert i18n.status_shape(NodeStatus.DEFERRED.value) == "◇"


def test_unknown_enum_values_degrade_instead_of_raising():
    """The generator projects invalid data defensively (spec §37)."""
    assert i18n.status_label("zh-CN", "MADE_UP") == "MADE_UP"
    assert i18n.track_label("zh-CN", "MADE_UP") == "MADE_UP"
    assert i18n.status_shape("MADE_UP") == "?"


# ---------------------------------------------------------- the translator


def test_translator_formats_arguments_and_falls_back_to_english():
    zh = i18n.translator("zh-CN")
    assert "3" in zh("node.decisions.count", n=3)
    assert i18n.translator("en")("node.decisions.count", n=3) == "3 decisions"
    # a key that does not exist anywhere degrades to the key itself
    assert zh("no.such.key") == "no.such.key"


def test_resolve_locale_and_html_lang():
    assert i18n.resolve_locale(None) == "en"
    assert i18n.resolve_locale("") == "en"
    assert i18n.resolve_locale("zh-CN") == "zh-CN"
    assert i18n.resolve_locale("xx") == "en"
    assert i18n.html_lang("zh-CN") == "zh-CN"
    assert i18n.html_lang("xx") == "en"


# --------------------------------------------------------- project config


def test_missing_ui_section_defaults_to_english(make_project, tmp_path, node_dict):
    """AC-UI-05: a V0.1 project.yaml keeps working, in English."""
    project, _root = make_project(tmp_path, node_dicts=[node_dict("A")])
    assert project.config.ui.locale == "en"
    assert project.config.ui.raw_locale is None
    assert project.load_issues == []


def test_ui_locale_is_read_from_project_yaml(make_project, tmp_path, node_dict):
    project, _root = make_project(
        tmp_path,
        config_dict={
            "project": {"id": "p", "name": "P"},
            "planning": {"current_focus": None},
            "ui": {"locale": "zh-CN"},
        },
        node_dicts=[node_dict("A")],
    )
    assert project.config.ui.locale == "zh-CN"
    assert project.config.ui.raw_locale == "zh-CN"
    assert project.load_issues == []


def test_unknown_locale_falls_back_with_a_warning_and_still_builds(
    make_project, tmp_path, node_dict, cli, by_rule
):
    """Spec §5: unknown locale → fall back to en + WARNING, never a failed build."""
    project, root = make_project(
        tmp_path,
        config_dict={
            "project": {"id": "p", "name": "P"},
            "planning": {"current_focus": None},
            "ui": {"locale": "xx"},
        },
        node_dicts=[node_dict("A")],
    )
    assert project.config.ui.locale == "en"
    assert project.config.ui.raw_locale == "xx"

    warnings = by_rule(project.load_issues, "unknown-ui-locale")
    assert len(warnings) == 1
    assert warnings[0].severity.value == "WARNING"
    assert "xx" in warnings[0].message and "en" in warnings[0].message

    code, out, _err = cli("-p", str(root), "build")
    assert code == EXIT_OK
    assert "unknown-ui-locale" in out
    page = (root / ".planning" / "dist" / "index.html").read_text(encoding="utf-8")
    assert '<html lang="en" data-locale="en">' in page


def test_ui_section_is_not_an_unknown_top_level_key(make_project, tmp_path, node_dict, by_rule):
    project, _root = make_project(
        tmp_path,
        config_dict={
            "project": {"id": "p", "name": "P"},
            "planning": {"current_focus": None},
            "ui": {"locale": "zh-CN"},
        },
        node_dicts=[node_dict("A")],
    )
    assert "ui" not in project.config.unknown_keys
    assert by_rule(project.load_issues, "unknown-field") == []


def test_unknown_ui_key_is_reported_but_harmless(make_project, tmp_path, node_dict):
    from planning_control_plane import validator

    project, _root = make_project(
        tmp_path,
        config_dict={
            "project": {"id": "p", "name": "P"},
            "planning": {"current_focus": None},
            "ui": {"locale": "zh-CN", "theme": "dark"},
        },
        node_dicts=[node_dict("A")],
    )
    assert project.config.ui.unknown_keys == ["theme"]
    assert project.config.ui.locale == "zh-CN"
    assert not [i for i in validator.validate_project(project) if i.severity.value == "ERROR"]


# ------------------------------------------- locale never leaks into data


def test_locale_does_not_change_cli_or_capsule_output(make_project, tmp_path, node_dict, cli):
    """UI-D2: machine-facing surfaces are identical under both locales."""
    node = node_dict(
        "A",
        title="节点",
        status="WRITEBACK_PENDING",
        discussion_status="DONE",
        writeback_status="IN_PROGRESS",
        implementation_status="N/A",
        next_action="do the thing",
    )
    base_config = {"project": {"id": "p", "name": "P"}, "planning": {"current_focus": "A"}}
    en_dir, zh_dir = tmp_path / "en", tmp_path / "zh"
    en_dir.mkdir()
    zh_dir.mkdir()

    _project, en_root = make_project(en_dir, config_dict=dict(base_config), node_dicts=[node])
    _project, zh_root = make_project(
        zh_dir, config_dict={**base_config, "ui": {"locale": "zh-CN"}}, node_dicts=[node]
    )

    for command in (("context", "A"), ("status",), ("focus",)):
        assert cli("-p", str(en_root), *command) == cli("-p", str(zh_root), *command), command

    # and the machine-facing enums stay raw in both
    _code, out, _err = cli("-p", str(zh_root), "status")
    assert "WRITEBACK_PENDING" in out
    _code, out, _err = cli("-p", str(zh_root), "context", "A")
    assert "WRITEBACK_PENDING" in out
    assert "N/A" in out
