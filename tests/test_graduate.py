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


def test_append_to_top_level_list_adopts_a_wider_indent():
    text = "id: P1\nevidence_sources:\n    - docs/a.md\n"
    out = cli_module._append_to_top_level_list(text, "evidence_sources", ["docs/b.md"])
    assert out == "id: P1\nevidence_sources:\n    - docs/a.md\n    - docs/b.md\n"


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


# ------------------------------------------------------ the write path


def test_graduate_writes_both_files_and_preserves_author_text(make_project, tmp_path, cli):
    _project, root = _graduate_project(make_project, tmp_path)
    code, out, _err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 0
    assert "graduated: IDEA-0007 -> P2-A5 (OPEN -> PROMOTED)" in out

    idea_text = (root / ".planning" / "ideas" / "IDEA-0007.yaml").read_text(encoding="utf-8")
    assert "# captured thinking" in idea_text           # author comment survives
    assert "status: PROMOTED" in idea_text
    assert "outcome:\n  node: P2-A5" in idea_text
    assert "outcome: ~" not in idea_text
    assert "relates_to: [P2]" in idea_text              # untouched keys untouched

    node_text = (root / ".planning" / "nodes" / "P2-A5.yaml").read_text(encoding="utf-8")
    assert "# pilot target" in node_text
    assert "objective: >" in node_text
    assert node_text.count("  - docs/existing.md") == 1  # existing entry kept once
    assert "  - docs/bench.md" in node_text
    assert "  - docs/method.md" in node_text


def test_graduate_output_names_transcribed_refs_and_files(make_project, tmp_path, cli):
    _project, root = _graduate_project(make_project, tmp_path)
    code, out, _err = cli(
        "-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5",
        "--note", "pilot is the evidence",
    )
    assert code == 0
    assert "evidence transcribed into P2-A5: docs/bench.md, docs/method.md" in out
    assert "idea file: .planning/ideas/IDEA-0007.yaml" in out
    assert "node file: .planning/nodes/P2-A5.yaml" in out
    idea_text = (root / ".planning" / "ideas" / "IDEA-0007.yaml").read_text(encoding="utf-8")
    assert "  note: pilot is the evidence" in idea_text


def test_graduate_without_note_writes_no_note_line(make_project, tmp_path, cli):
    """The idea's own justification entries keep their note lines; what must
    stay absent is a note inside the outcome block (asserted on the
    reloaded model, not on raw text)."""
    _project, root = _graduate_project(make_project, tmp_path)
    code, _out, _err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 0
    from planning_control_plane.loader import load_project

    project = load_project(root)
    assert project.ideas["IDEA-0007"].outcome.note == ""


def test_graduate_dedupes_refs_already_on_the_node(make_project, tmp_path, cli):
    node_text = GRAD_NODE.replace(
        "  - docs/existing.md", "  - docs/existing.md\n  - docs/bench.md"
    )
    _project, root = _graduate_project(make_project, tmp_path, node_text=node_text)
    code, out, _err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 0
    node_new = (root / ".planning" / "nodes" / "P2-A5.yaml").read_text(encoding="utf-8")
    assert node_new.count("docs/bench.md") == 1
    assert "evidence transcribed into P2-A5: docs/method.md" in out
    assert "skipped 1 ref(s) already present" in out


def test_graduate_note_only_sources_leave_the_node_file_untouched(make_project, tmp_path, cli):
    raw = GRAD_IDEA.replace(
        "  - ref: docs/bench.md\n    note: Grafana time-compare\n",
        "  - note: Grafana time-compare\n",
    ).replace("  - ref: docs/method.md\n", "")
    _project, root = _graduate_project(make_project, tmp_path, idea_text=raw)
    node_file = root / ".planning" / "nodes" / "P2-A5.yaml"
    before = node_file.read_text(encoding="utf-8")
    code, out, _err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 0
    assert node_file.read_text(encoding="utf-8") == before
    assert "no evidence refs to transcribe" in out


def test_graduate_accepts_a_parked_idea(make_project, tmp_path, cli):
    raw = GRAD_IDEA.replace("status: OPEN", "status: PARKED")
    _project, root = _graduate_project(make_project, tmp_path, idea_text=raw)
    code, out, _err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 0
    assert "(PARKED -> PROMOTED)" in out


def test_graduate_result_validates_clean(make_project, tmp_path, cli):
    """The written state is the state the spec promises: PROMOTED with a
    reachable outcome — no ERROR, no outcome-without-promotion."""
    _project, root = _graduate_project(make_project, tmp_path)
    assert cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")[0] == 0
    code, out, _err = cli("-p", str(root), "validate")
    assert code == 0
    assert "IDEA-0007" not in out


def test_graduate_note_that_looks_like_a_yaml_scalar_round_trips(make_project, tmp_path, cli):
    """`--note 42` must land as a string the loader keeps: an unquoted
    scalar would reparse as an int and be silently dropped."""
    _project, root = _graduate_project(make_project, tmp_path)
    code, _out, _err = cli(
        "-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5", "--note", "42"
    )
    assert code == 0
    from planning_control_plane.loader import load_project

    project = load_project(root)
    assert project.ideas["IDEA-0007"].outcome.note == "42"


# os.geteuid is Unix-only: calling it here (a decorator argument, evaluated
# at import time) would fail collection of this whole file on Windows.
# Windows has no root that bypasses permissions, so absent means "not root",
# and the test runs there against the read-only attribute os.chmod sets.
@pytest.mark.skipif(
    getattr(os, "geteuid", lambda: 1)() == 0, reason="root ignores file permissions"
)
def test_graduate_restores_files_when_a_write_fails(make_project, tmp_path, cli):
    """The idea file is written first; if the node write then fails, the
    idea file must go back to its original content (IDEA-D35)."""
    _project, root = _graduate_project(make_project, tmp_path)
    idea_file = root / ".planning" / "ideas" / "IDEA-0007.yaml"
    node_file = root / ".planning" / "nodes" / "P2-A5.yaml"
    idea_before = idea_file.read_text(encoding="utf-8")
    node_before = node_file.read_text(encoding="utf-8")
    os.chmod(node_file, 0o444)
    try:
        code, _out, err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
        assert code == 1
        assert "restored" in err
    finally:
        os.chmod(node_file, 0o644)
    assert idea_file.read_text(encoding="utf-8") == idea_before
    assert node_file.read_text(encoding="utf-8") == node_before


def test_graduate_restores_files_when_reverification_fails(make_project, tmp_path, cli, monkeypatch):
    """A reload that cannot even run counts as verification failure: both
    files go back to their originals and the command exits 1."""
    from planning_control_plane import loader as loader_module

    _project, root = _graduate_project(make_project, tmp_path)
    idea_file = root / ".planning" / "ideas" / "IDEA-0007.yaml"
    node_file = root / ".planning" / "nodes" / "P2-A5.yaml"
    idea_before = idea_file.read_text(encoding="utf-8")
    node_before = node_file.read_text(encoding="utf-8")

    real_load = loader_module.load_project
    calls = {"count": 0}

    def flaky_load(root_arg):
        calls["count"] += 1
        if calls["count"] > 1:
            raise loader_module.LoadError("simulated unreadable project")
        return real_load(root_arg)

    monkeypatch.setattr(loader_module, "load_project", flaky_load)
    code, _out, err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 1
    assert "verification failed" in err
    assert idea_file.read_text(encoding="utf-8") == idea_before
    assert node_file.read_text(encoding="utf-8") == node_before


# ------------------------------------------------- author file shapes


def test_graduate_appends_outcome_when_the_key_is_absent(make_project, tmp_path, cli):
    raw = GRAD_IDEA.replace("outcome: ~\n\n", "")
    assert "outcome" not in raw
    _project, root = _graduate_project(make_project, tmp_path, idea_text=raw)
    code, _out, _err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 0
    idea_text = (root / ".planning" / "ideas" / "IDEA-0007.yaml").read_text(encoding="utf-8")
    assert idea_text.count("outcome:") == 1
    assert "outcome:\n  node: P2-A5" in idea_text


def test_graduate_replaces_a_transition_state_outcome_block(make_project, tmp_path, cli):
    """OPEN + outcome already set is the legal transition state (IDEA-D38
    WARNING); graduation overwrites it instead of growing a second key."""
    raw = GRAD_IDEA.replace(
        "outcome: ~",
        "outcome:\n  node: P2\n  note: node built, status flip pending",
    )
    _project, root = _graduate_project(make_project, tmp_path, idea_text=raw)
    code, _out, _err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 0
    idea_text = (root / ".planning" / "ideas" / "IDEA-0007.yaml").read_text(encoding="utf-8")
    assert idea_text.count("outcome:") == 1
    assert "node: P2-A5" in idea_text
    assert "status flip pending" not in idea_text


def test_graduate_appends_status_when_the_key_is_absent(make_project, tmp_path, cli):
    """An idea relying on the OPEN default has no status line; graduation
    appends an explicit one (only absent keys fall back — same discipline
    as the loader)."""
    raw = GRAD_IDEA.replace("status: OPEN\n\n", "", 1)
    assert "\nstatus:" not in raw
    _project, root = _graduate_project(make_project, tmp_path, idea_text=raw)
    code, _out, _err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 0
    from planning_control_plane.loader import load_project

    project = load_project(root)
    assert project.ideas["IDEA-0007"].status == "PROMOTED"
    assert project.ideas["IDEA-0007"].outcome.node == "P2-A5"


def test_graduate_preserves_crlf_author_files(make_project, tmp_path, cli):
    _project, root = _graduate_project(make_project, tmp_path)
    idea_file = root / ".planning" / "ideas" / "IDEA-0007.yaml"
    node_file = root / ".planning" / "nodes" / "P2-A5.yaml"
    idea_file.write_bytes(GRAD_IDEA.replace("\n", "\r\n").encode("utf-8"))
    node_file.write_bytes(GRAD_NODE.replace("\n", "\r\n").encode("utf-8"))
    code, _out, _err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 0
    assert b"status: PROMOTED\r\n" in idea_file.read_bytes()
    assert b"  node: P2-A5\r\n" in idea_file.read_bytes()
    assert b"  - docs/bench.md\r\n" in node_file.read_bytes()


def test_graduate_note_must_be_a_single_line(make_project, tmp_path, cli):
    _project, root = _graduate_project(make_project, tmp_path)
    idea_file = root / ".planning" / "ideas" / "IDEA-0007.yaml"
    before = idea_file.read_text(encoding="utf-8")
    code, _out, err = cli(
        "-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5", "--note", "two\nlines"
    )
    assert code == 1
    assert "single line" in err
    assert idea_file.read_text(encoding="utf-8") == before


def test_graduate_refuses_a_flow_style_evidence_list(make_project, tmp_path, cli):
    """R4 D.7 #3: a flow-style `evidence_sources: [a, b]` cannot take a
    faithful mechanical append — refuse before the first byte is written."""
    node_text = GRAD_NODE.replace(
        "evidence_sources:\n  - docs/existing.md\n", "evidence_sources: [docs/existing.md]\n"
    )
    _project, root = _graduate_project(make_project, tmp_path, node_text=node_text)
    idea_file = root / ".planning" / "ideas" / "IDEA-0007.yaml"
    node_file = root / ".planning" / "nodes" / "P2-A5.yaml"
    idea_before = idea_file.read_text(encoding="utf-8")
    node_before = node_file.read_text(encoding="utf-8")
    code, _out, err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 1
    assert "block list style" in err
    assert idea_file.read_text(encoding="utf-8") == idea_before
    assert node_file.read_text(encoding="utf-8") == node_before


def test_graduate_creates_a_missing_evidence_sources_key(make_project, tmp_path, cli):
    """A node that never declared evidence_sources gains the key with the
    transcribed refs (the unit-pinned append branch, end to end)."""
    node_text = GRAD_NODE.replace("evidence_sources:\n  - docs/existing.md\n\n", "")
    assert "evidence_sources" not in node_text
    _project, root = _graduate_project(make_project, tmp_path, node_text=node_text)
    code, _out, _err = cli("-p", str(root), "graduate", "IDEA-0007", "--to", "P2-A5")
    assert code == 0
    node_new = (root / ".planning" / "nodes" / "P2-A5.yaml").read_text(encoding="utf-8")
    assert "  - docs/bench.md" in node_new
    assert "  - docs/method.md" in node_new
