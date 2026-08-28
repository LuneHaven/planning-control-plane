"""The harness skill asset and its drift gate (spec INT-D6..D9, D15)."""

import argparse
import re
from pathlib import Path

from planning_control_plane import cli as cli_module

SKILL_PATH = Path(__file__).resolve().parent.parent / "integrations" / "skills" / "pcp" / "SKILL.md"

#: Commands as they appear in prose: `pcp <name>` inside backticks.
_COMMAND_MENTION_RE = re.compile(r"`pcp ([a-z][a-z0-9-]*)")


def _registered_commands() -> set[str]:
    """The authoritative command set: argparse's own subparser choices."""
    parser = cli_module._build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    raise AssertionError("no subparsers registered on the pcp parser")


def test_skill_asset_exists():
    assert SKILL_PATH.is_file(), f"missing harness asset: {SKILL_PATH}"


def test_skill_frontmatter_covers_the_trigger_scenarios():
    """INT-D8: only the description stays in context, so it carries the
    triggers — progressive disclosure means the body is loaded on demand."""
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    frontmatter = text.split("---", 2)[1]
    assert "name: pcp" in frontmatter
    lowered = frontmatter.lower()
    for scenario in (".planning", "resum", "idea", "graduat", "validate", "naming"):
        assert scenario in lowered, scenario


def test_skill_documents_every_registered_command():
    """INT-D15 (a): no command may be missing from the manual."""
    text = SKILL_PATH.read_text(encoding="utf-8")
    mentioned = set(_COMMAND_MENTION_RE.findall(text))
    missing = _registered_commands() - mentioned
    assert not missing, f"SKILL.md does not document: {sorted(missing)}"


def test_skill_mentions_no_unregistered_command():
    """INT-D15 (b): and none may outlive its removal from the CLI."""
    text = SKILL_PATH.read_text(encoding="utf-8")
    mentioned = set(_COMMAND_MENTION_RE.findall(text))
    unknown = mentioned - _registered_commands()
    assert not unknown, f"SKILL.md documents commands that do not exist: {sorted(unknown)}"


def test_skill_defers_repository_rules_to_agents_md():
    """INT-D7: repository rules live in AGENTS.md alone; the skill points at
    it instead of copying it, so the two cannot drift apart."""
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "AGENTS.md" in text
    # The naming convention is a repository rule: it must NOT be restated here.
    assert "YYYY-MM-DD-" not in text
