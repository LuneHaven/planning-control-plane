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
from planning_control_plane.model import IdeaStatus


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
    node_keys = {k for k in i18n.TRANSLATIONS["en"] if k.startswith("status.")}
    idea_keys = {k for k in i18n.TRANSLATIONS["en"] if k.startswith("idea_status.")}
    assert idea_keys
    assert not node_keys & idea_keys
    assert i18n.status_key("OPEN") is None  # OPEN is not a NodeStatus


def test_ideas_page_strings_exist_in_both_locales():
    required = {
        "ideas.nav", "ideas.nav_label", "ideas.title", "ideas.subtitle",
        "ideas.detail", "ideas.benchmark", "ideas.methodology",
        "ideas.relates_to", "ideas.outcome", "ideas.created", "ideas.updated",
        "ideas.no_sources", "ideas.unknown_node", "ideas.group_count",
    }
    for locale in i18n.SUPPORTED_LOCALES:
        missing = required - set(i18n.TRANSLATIONS[locale])
        assert not missing, (locale, sorted(missing))
