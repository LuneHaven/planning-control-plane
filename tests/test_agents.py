"""Harness integration: the AGENTS.md advisory command (spec INT-D1..D5, D14, D17)."""

from planning_control_plane import cli as cli_module

BEGIN = "<!-- pcp:agents begin v1 -->"
END = "<!-- pcp:agents end -->"


def test_agents_prints_a_marker_delimited_block(cli):
    code, out, err = cli("agents")
    assert (code, err) == (0, "")
    assert out.startswith(BEGIN)
    assert out.rstrip().endswith(END)
    assert out.endswith("\n")  # append-friendly: 'pcp agents >> AGENTS.md'


def test_agents_covers_every_int_d3_point(cli):
    _code, out, _err = cli("agents")
    # INT-D3 1..7, in order: data plane, session workflow, idea capture,
    # graduation, validate, document naming, registration convention.
    for needle in (
        ".planning/",
        "dist/",
        "pcp context",
        "pcp status",
        "pcp ideas",
        ".planning/ideas/IDEA-",
        "relates_to",
        "benchmark_sources",
        "methodology_sources",
        "pcp graduate",
        "pcp validate",
        "YYYY-MM-DD-",
        "ref",
    ):
        assert needle in out, needle


def test_agents_naming_advice_excludes_specs(cli):
    """INT-D3-6: the date prefix covers one-shot artifacts only."""
    _code, out, _err = cli("agents")
    assert "stable slug" in out


def test_agents_writes_nothing(cli, tmp_path):
    """INT-D1: read-only — no project load, no file written, not even AGENTS.md."""
    root = tmp_path / "repo"
    root.mkdir()
    code, _out, _err = cli("-p", str(root), "agents")
    assert code == 0
    assert list(root.iterdir()) == []


def test_agents_works_without_a_planning_directory(cli, tmp_path):
    """No .planning is needed: the snippet is a static template (INT-D4)."""
    root = tmp_path / "bare"
    root.mkdir()
    code, out, err = cli("-p", str(root), "agents")
    assert (code, err) == (0, "")
    assert BEGIN in out


def test_agents_help_says_it_prints_an_agents_md_snippet():
    """INT-D17: 'agents' reads as 'manage agents' in a harness context."""
    help_text = cli_module._build_parser().format_help()
    assert "agents" in help_text
    assert "AGENTS.md" in help_text
