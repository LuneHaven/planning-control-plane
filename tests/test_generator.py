"""Deterministic generation and drift detection (spec §22, §23), including
the ``pcp build`` / ``pcp build --check`` CLI contract.

The demo repository is only ever read: engine-level tests build into
temporary directories, CLI-level tests run on a writable copy.
"""

from __future__ import annotations

import shutil

from planning_control_plane.cli import EXIT_FAILURE, EXIT_OK
from planning_control_plane.generator import build_site, check_build
from planning_control_plane.loader import load_project

#: Files the demo build must produce (spec §22).
EXPECTED_DEMO_FILES = sorted(
    [
        "assets/app.js",
        "assets/style.css",
        "index.html",
        *[f"nodes/{node_id}.html" for node_id in ("P1", "P2", "P2-A", "P2-A1", "P2-A2", "P2-A3", "P2-A4")],
    ]
)


def file_map(root) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


# --------------------------------------------------------------- determinism


def test_build_twice_into_two_directories_is_byte_identical(demo_root, tmp_path):
    project = load_project(demo_root)
    first, second = tmp_path / "build-a", tmp_path / "build-b"

    build_site(project, first)
    build_site(project, second)

    files_a, files_b = file_map(first), file_map(second)
    assert sorted(files_a) == EXPECTED_DEMO_FILES
    assert files_a == files_b  # every file byte-for-byte identical


def test_rebuild_after_deleting_dist_is_identical(demo_root, tmp_path):
    project = load_project(demo_root)
    dist = tmp_path / "dist"

    build_site(project, dist)
    original = file_map(dist)
    # delete-and-rebuild: remove the whole tree (and one file separately)
    shutil.rmtree(dist)
    build_site(project, dist)
    assert file_map(dist) == original

    (dist / "index.html").unlink()
    build_site(project, dist)
    assert file_map(dist) == original


def test_check_build_against_fresh_build_is_ok(demo_root, tmp_path):
    project = load_project(demo_root)
    dist = tmp_path / "dist"
    build_site(project, dist)
    ok, messages = check_build(project, dist)
    assert ok
    assert messages == []


# ------------------------------------------------------------ CLI build/check


def test_cli_build_then_check_is_consistent(demo_copy, cli):
    code, out, err = cli("-p", str(demo_copy), "build")
    assert code == EXIT_OK
    assert "Built 10 files into .planning/dist" in out  # index + 7 nodes + 2 assets

    code, out, err = cli("-p", str(demo_copy), "build", "--check")
    assert code == EXIT_OK
    assert "dist is up to date (10 files)" in out


def test_cli_build_check_detects_tampered_byte(demo_copy, cli):
    assert cli("-p", str(demo_copy), "build")[0] == EXIT_OK
    page = demo_copy / ".planning" / "dist" / "nodes" / "P2-A4.html"
    data = bytearray(page.read_bytes())
    data[len(data) // 2] ^= 0xFF  # flip exactly one byte
    page.write_bytes(bytes(data))

    code, out, err = cli("-p", str(demo_copy), "build", "--check")

    assert code == EXIT_FAILURE
    assert "changed: nodes/P2-A4.html" in out
    assert "drift detected; run pcp build" in out


def test_cli_build_check_detects_deleted_file(demo_copy, cli):
    assert cli("-p", str(demo_copy), "build")[0] == EXIT_OK
    (demo_copy / ".planning" / "dist" / "index.html").unlink()

    code, out, _err = cli("-p", str(demo_copy), "build", "--check")

    assert code == EXIT_FAILURE
    assert "missing: index.html" in out


def test_cli_build_check_detects_extra_file(demo_copy, cli):
    assert cli("-p", str(demo_copy), "build")[0] == EXIT_OK
    (demo_copy / ".planning" / "dist" / "stray.txt").write_text("stray", encoding="utf-8")

    code, out, _err = cli("-p", str(demo_copy), "build", "--check")

    assert code == EXIT_FAILURE
    assert "extra: stray.txt" in out


def test_cli_build_check_missing_dist_directory(demo_copy, cli):
    # Self-sufficient: ensure dist exists first, then remove it — the case
    # must not depend on build artifacts left in the working tree.
    assert cli("-p", str(demo_copy), "build")[0] == EXIT_OK
    shutil.rmtree(demo_copy / ".planning" / "dist")
    code, out, err = cli("-p", str(demo_copy), "build", "--check")
    assert code == EXIT_FAILURE
    assert "dist not found" in out


def test_cli_build_check_recovers_after_rebuild(demo_copy, cli):
    """The documented remediation for drift — rerun the build — restores exit 0."""
    assert cli("-p", str(demo_copy), "build")[0] == EXIT_OK
    page = demo_copy / ".planning" / "dist" / "assets" / "style.css"
    page.write_bytes(page.read_bytes() + b"/* tampered */")
    assert cli("-p", str(demo_copy), "build", "--check")[0] == EXIT_FAILURE

    assert cli("-p", str(demo_copy), "build")[0] == EXIT_OK
    code, out, _err = cli("-p", str(demo_copy), "build", "--check")
    assert code == EXIT_OK


def test_cli_build_refuses_invalid_project(make_project, tmp_path, node_dict, cli):
    project, root = make_project(
        tmp_path,
        node_dicts=[node_dict("A", status="DOING", depends_on=["GHOST"])],
    )
    dist = root / ".planning" / "dist"

    code, out, err = cli("-p", str(root), "build")

    assert code == EXIT_FAILURE
    assert "invalid-status" in out
    assert "fix validation errors before build" in out
    # nothing was generated for an invalid project
    assert not dist.exists()


def test_cli_build_check_reports_errors_before_drift(make_project, tmp_path, node_dict, cli):
    project, root = make_project(tmp_path, node_dicts=[node_dict("A", status="DOING")])
    code, out, _err = cli("-p", str(root), "build", "--check")
    assert code == EXIT_FAILURE
    assert "fix validation errors before build" in out
