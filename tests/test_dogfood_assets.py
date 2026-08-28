"""This repository consumes its own harness assets (dogfood gates).

The three files these tests pin — root ``AGENTS.md``, the one-line
``CLAUDE.md`` bridge and the project-level skill copy under
``.agents/skills/pcp/`` — are copies of assets the tool itself produces or
ships. Without a gate, each copy can drift from its source silently.

Context for the bridge: AGENTS.md is the open standard most harnesses read
natively (Codex, Cursor, Gemini CLI, ZCode, …); Claude Code only reads
``CLAUDE.md``, so the ecosystem-standard bridge is a ``CLAUDE.md`` whose sole
content is the import directive ``@AGENTS.md``.
"""

from pathlib import Path

from planning_control_plane import cli as cli_module

REPO_ROOT = Path(__file__).resolve().parent.parent
DOGFOOD_SKILL = REPO_ROOT / ".agents" / "skills" / "pcp" / "SKILL.md"
ASSET_SKILL = REPO_ROOT / "integrations" / "skills" / "pcp" / "SKILL.md"


def test_repo_dogfoods_the_agents_snippet():
    """The block in this repo's AGENTS.md is byte-identical to what
    `pcp agents` prints, so a snippet edit cannot ship untested here."""
    text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert cli_module._AGENTS_SNIPPET in text


def test_repo_bridges_claude_md_to_agents_md():
    """Claude Code does not read AGENTS.md; the bridge is a CLAUDE.md whose
    only content is the @AGENTS.md import directive."""
    text = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert text.strip() == "@AGENTS.md"


def test_repo_carries_a_project_level_skill_copy():
    """The project-level skill under .agents/skills/ (what ZCode and Codex
    discover in a repository) matches the shipped asset byte for byte."""
    assert DOGFOOD_SKILL.read_bytes() == ASSET_SKILL.read_bytes()
