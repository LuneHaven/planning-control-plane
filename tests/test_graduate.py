"""Graduation bridge tests (spec §55/§62.3, appendix D.7).

`pcp graduate` is the idea layer's only write command: it flips the idea
to PROMOTED, wires outcome.node at an existing node, and transcribes the
idea's ref-carrying justification entries into the node's evidence_sources.
"""

from __future__ import annotations

import os

import pytest

from planning_control_plane import cli as cli_module


# ------------------------------------------------------- yaml surgery units


def test_set_top_level_key_replaces_the_value_line():
    text = "id: P1\ntitle: T\nstatus: OPEN\n"
    out = cli_module._set_top_level_key(text, "status", ["status: PROMOTED"])
    assert out == "id: P1\ntitle: T\nstatus: PROMOTED\n"


def test_set_top_level_key_replaces_a_multiline_block():
    text = "id: P1\noutcome:\n  node: OLD\n  note: old text\nlast_updated: 2026-01-01\n"
    out = cli_module._set_top_level_key(text, "outcome", ["outcome:", "  node: NEW"])
    assert out == "id: P1\noutcome:\n  node: NEW\nlast_updated: 2026-01-01\n"


def test_set_top_level_key_appends_a_missing_key():
    text = "id: P1\ntitle: T"
    out = cli_module._set_top_level_key(text, "status", ["status: PROMOTED"])
    assert out == "id: P1\ntitle: T\nstatus: PROMOTED\n"


def test_set_top_level_key_adopts_crlf():
    text = "id: P1\r\nstatus: OPEN\r\n"
    out = cli_module._set_top_level_key(text, "status", ["status: PROMOTED"])
    assert out == "id: P1\r\nstatus: PROMOTED\r\n"


def test_set_top_level_key_leaves_indented_same_name_keys_alone():
    """Only a column-0 `key:` is the target; an indented `status:` under
    another key is value data, never the top-level one."""
    text = "outer:\n  status: INNER\nstatus: OPEN\n"
    out = cli_module._set_top_level_key(text, "status", ["status: PROMOTED"])
    assert out == "outer:\n  status: INNER\nstatus: PROMOTED\n"


def test_append_to_top_level_list_appends_after_the_last_item():
    text = "id: P1\nevidence_sources:\n  - docs/a.md\n\nlast_updated: 2026-01-01\n"
    out = cli_module._append_to_top_level_list(text, "evidence_sources", ["docs/b.md"])
    assert out == (
        "id: P1\nevidence_sources:\n  - docs/a.md\n  - docs/b.md\n\nlast_updated: 2026-01-01\n"
    )


def test_append_to_top_level_list_creates_a_missing_key():
    text = "id: P1\ntitle: T\n"
    out = cli_module._append_to_top_level_list(text, "evidence_sources", ["docs/a.md"])
    assert out == "id: P1\ntitle: T\nevidence_sources:\n  - docs/a.md\n"


def test_append_to_top_level_list_refuses_flow_style():
    with pytest.raises(ValueError, match="block list style"):
        cli_module._append_to_top_level_list(
            "id: P1\nevidence_sources: [docs/a.md]\n", "evidence_sources", ["docs/b.md"]
        )
