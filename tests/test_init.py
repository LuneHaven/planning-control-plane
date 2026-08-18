"""``pcp init``: skeleton creation, safe re-init and ``--force`` semantics
(spec §5: never overwrite planning data; ``--force`` only fills gaps).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from planning_control_plane.cli import EXIT_FAILURE, EXIT_OK
from planning_control_plane.model import PLANNING_DIR


def planning_paths(root: Path) -> dict[str, Path]:
    planning = root / PLANNING_DIR
    return {
        "planning": planning,
        "project": planning / "project.yaml",
        "roadmap": planning / "roadmap.yaml",
        "nodes": planning / "nodes",
        "gitignore": planning / ".gitignore",
    }


def snapshot(paths: dict[str, Path]) -> dict[str, str]:
    """Content of every generated file (directories map to their file list)."""
    state = {}
    for name, path in paths.items():
        if path.is_file():
            state[name] = path.read_text(encoding="utf-8")
        elif path.is_dir():
            state[name] = ",".join(sorted(p.name for p in path.iterdir()))
    return state


def test_init_creates_full_skeleton(tmp_path, cli):
    root = tmp_path / "target-repo"
    root.mkdir()

    code, out, err = cli("-p", str(root), "init")

    assert code == EXIT_OK
    assert err == ""
    paths = planning_paths(root)
    assert paths["planning"].is_dir()
    assert paths["project"].is_file()
    assert paths["roadmap"].is_file()
    assert paths["nodes"].is_dir()
    assert paths["gitignore"].is_file()
    # every artifact is reported as created
    for name in ("project.yaml", "roadmap.yaml", ".gitignore", "nodes"):
        assert name in out

    # the generated config parses and carries the slugified directory name
    config = yaml.safe_load(paths["project"].read_text(encoding="utf-8"))
    assert config["project"]["id"] == "target-repo"
    assert config["project"]["name"] == "target-repo"
    assert config["planning"]["current_focus"] is None
    assert config["output"]["directory"] == ".planning/dist"
    # a fresh roadmap is loadable and empty
    assert yaml.safe_load(paths["roadmap"].read_text(encoding="utf-8")) == {"nodes": []}
    # generated output is excluded from version control
    assert "dist/" in paths["gitignore"].read_text(encoding="utf-8")


def test_init_twice_fails_and_changes_nothing(tmp_path, cli):
    root = tmp_path / "target"
    root.mkdir()
    assert cli("-p", str(root), "init")[0] == EXIT_OK

    paths = planning_paths(root)
    before = snapshot(paths)
    # user edits between the two inits must survive the failed re-init
    paths["project"].write_text("# my planning data\nproject:\n  id: mine\n", encoding="utf-8")
    before = snapshot(paths)

    code, out, err = cli("-p", str(root), "init")

    assert code == EXIT_FAILURE
    assert "already exists" in err
    assert snapshot(paths) == before


def test_init_force_only_fills_missing_files(tmp_path, cli):
    root = tmp_path / "target"
    root.mkdir()
    assert cli("-p", str(root), "init")[0] == EXIT_OK
    paths = planning_paths(root)

    # user-owned content plus one deleted skeleton file
    custom_project = "# my comments\nproject:\n  id: mine\n  name: Mine\nplanning:\n  current_focus: null\n"
    paths["project"].write_text(custom_project, encoding="utf-8")
    custom_roadmap = "# my roadmap\nnodes:\n  - id: N1\n    title: Kept\n"
    paths["roadmap"].write_text(custom_roadmap, encoding="utf-8")
    paths["gitignore"].unlink()

    code, out, err = cli("-p", str(root), "init", "--force")

    assert code == EXIT_OK
    # existing planning data is never overwritten, not even with --force
    assert paths["project"].read_text(encoding="utf-8") == custom_project
    assert paths["roadmap"].read_text(encoding="utf-8") == custom_roadmap
    # the missing file is re-created from the template
    assert paths["gitignore"].is_file()
    assert "dist/" in paths["gitignore"].read_text(encoding="utf-8")
    assert "created:" in out and "kept existing:" in out


def test_init_force_on_complete_project_keeps_everything(tmp_path, cli):
    root = tmp_path / "target"
    root.mkdir()
    assert cli("-p", str(root), "init")[0] == EXIT_OK
    paths = planning_paths(root)
    (paths["nodes"] / "A.yaml").write_text("id: A\ntitle: A\n", encoding="utf-8")
    before = snapshot(paths)

    code, out, err = cli("-p", str(root), "init", "--force")

    assert code == EXIT_OK
    assert snapshot(paths) == before
    # node data is untouched as well
    assert (paths["nodes"] / "A.yaml").read_text(encoding="utf-8") == "id: A\ntitle: A\n"
