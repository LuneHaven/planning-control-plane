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


# ------------------------------------------------------------- fixtures


GRAD_NODE = """\
# pilot target
id: P2-A5
title: Pilot
type: INVESTIGATION
status: NOT_STARTED

objective: >
  Pilot the hypothesis in one domain.

evidence_sources:
  - docs/existing.md

last_updated: 2026-08-27
"""

GRAD_IDEA = """\
# captured thinking
id: IDEA-0007
title: Trend comparison view
status: OPEN

detail: >
  One paragraph, no structure required.

relates_to: [P2]
benchmark_sources:
  - ref: docs/bench.md
    note: Grafana time-compare
  - note: Stripe month-over-month
methodology_sources:
  - ref: docs/method.md

outcome: ~

created: 2026-08-27
last_updated: 2026-08-27
"""


def _graduate_project(make_project, tmp_path, idea_text=GRAD_IDEA, node_text=GRAD_NODE, name="repo"):
    """A one-idea project whose node file carries author comments, a folded
    scalar and an existing evidence entry — the shapes the surgery must
    preserve. repo_files make every ref resolvable for post-graduate
    validate runs."""
    room = tmp_path / name
    room.mkdir()
    return make_project(
        room,
        node_dicts=[
            ("P2-A5.yaml", node_text),
            ("P2.yaml", "id: P2\ntitle: P2\ntype: PHASE\nstatus: READY\n"),
        ],
        raw_files={"ideas/IDEA-0007.yaml": idea_text},
        repo_files={"docs/existing.md": "x", "docs/bench.md": "b", "docs/method.md": "m"},
    )


# --------------------------------------------- resolution and refusals


def test_graduate_requires_to(make_project, tmp_path, cli, capsys):
    """argparse enforces the required flag itself and exits before any
    handler runs (usage error → exit 2). The `cli` fixture does not catch
    SystemExit, so this one asserts the exit directly."""
    _project, root = _graduate_project(make_project, tmp_path)
    with pytest.raises(SystemExit) as excinfo:
        cli("-p", str(root), "graduate", "IDEA-0007")
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert "--to" in captured.err


def test_graduate_unknown_idea_says_so(make_project, tmp_path, cli):
    _project, root = _graduate_project(make_project, tmp_path)
    idea_file = root / ".planning" / "ideas" / "IDEA-0007.yaml"
    before = idea_file.read_text(encoding="utf-8")
    code, _out, err = cli("-p", str(root), "graduate", "IDEA-9999", "--to", "P2-A5")
    assert code == 1
    assert "unknown idea 'IDEA-9999'" in err
    assert "pcp ideas" in err
    assert idea_file.read_text(encoding="utf-8") == before


def test_graduate_node_id_gets_an_idea_layer_hint(make_project, tmp_path, cli):
    """IDEA-D15 lets idea and node ids collide; passing a node id where an
    idea id is expected is the natural mistake (mirrors _idea_hint)."""
    _project, root = _graduate_project(make_project, tmp_path)
    code, _out, err = cli("-p", str(root), "graduate", "P2", "--to", "P2-A5")
    assert code == 1
    assert "'P2' is a node id" in err


def test_graduate_refuses_an_already_promoted_idea(make_project, tmp_path, cli):
    raw = GRAD_IDEA.replace("status: OPEN", "status: PROMOTED")
    _project, root = _graduate_project(make_project, tmp_path, idea_text=raw)
    code, _out, err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 1
    assert "already graduated" in err
    assert (root / ".planning" / "ideas" / "IDEA-0007.yaml").read_text(encoding="utf-8") == raw


def test_graduate_refuses_a_discarded_idea(make_project, tmp_path, cli):
    raw = GRAD_IDEA.replace("status: OPEN", "status: DISCARDED")
    _project, root = _graduate_project(make_project, tmp_path, idea_text=raw)
    code, _out, err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 1
    assert "revive it to OPEN" in err


def test_graduate_refuses_an_invalid_status(make_project, tmp_path, cli):
    raw = GRAD_IDEA.replace("status: OPEN", "status: WISHLIST")
    _project, root = _graduate_project(make_project, tmp_path, idea_text=raw)
    code, _out, err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 1
    assert "invalid status 'WISHLIST'" in err


def test_graduate_unknown_target_node_says_so(make_project, tmp_path, cli):
    _project, root = _graduate_project(make_project, tmp_path)
    code, _out, err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "NOSUCH")
    assert code == 1
    assert "unknown node 'NOSUCH'" in err


def test_graduate_target_idea_id_gets_a_node_hint(make_project, tmp_path, cli):
    _project, root = _graduate_project(make_project, tmp_path)
    code, _out, err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "IDEA-0007")
    assert code == 1
    assert "'IDEA-0007' is an idea id" in err


def test_graduate_refuses_an_inline_roadmap_node(make_project, tmp_path, cli):
    """Transcription edits the node's own file; an inline roadmap node has
    no file of its own to edit."""
    room = tmp_path / "roadmap-repo"
    room.mkdir()
    _project, root = make_project(
        room,
        roadmap_nodes=[
            {"id": "R1", "title": "Inline", "type": "DISCUSSION", "status": "NOT_STARTED"}
        ],
        raw_files={"ideas/IDEA-0007.yaml": GRAD_IDEA},
    )
    code, _out, err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "R1")
    assert code == 1
    assert "standalone file" in err
