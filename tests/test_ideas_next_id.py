"""The next-free-id hint on pcp ideas (spec INT-D12, INT-D18)."""

TAIL = "next free id: "


def _tail(out: str) -> str:
    return out.splitlines()[-1]


def test_missing_ideas_directory_starts_at_one(make_project, tmp_path, cli):
    """pcp init does not create ideas/, so this is a new project's default."""
    _project, root = make_project(tmp_path)
    code, out, err = cli("-p", str(root), "ideas")
    assert (code, err) == (0, "")
    assert _tail(out) == TAIL + "IDEA-0001"


def test_empty_ideas_directory_starts_at_one(make_project, tmp_path, cli):
    _project, root = make_project(tmp_path)
    (root / ".planning" / "ideas").mkdir()
    code, out, _err = cli("-p", str(root), "ideas")
    assert code == 0
    assert _tail(out) == TAIL + "IDEA-0001"


def test_highest_number_plus_one(make_project, tmp_path, cli):
    _project, root = make_project(
        tmp_path,
        raw_files={"ideas/IDEA-0007.yaml": "id: IDEA-0007\ntitle: T\nstatus: OPEN\n"},
    )
    code, out, _err = cli("-p", str(root), "ideas")
    assert code == 0
    assert _tail(out) == TAIL + "IDEA-0008"


def test_loaded_id_reserves_even_with_mismatched_filename(make_project, tmp_path, cli):
    """The union's loaded-id arm in isolation: a well-formed idea whose file
    name differs from its id (idea-filename-mismatch territory) still counts."""
    _project, root = make_project(
        tmp_path,
        raw_files={"ideas/notes.yaml": "id: IDEA-0007\ntitle: T\nstatus: OPEN\n"},
    )
    code, out, _err = cli("-p", str(root), "ideas")
    assert code == 0
    assert _tail(out) == TAIL + "IDEA-0008"


def test_unparsable_file_still_reserves_its_number(make_project, tmp_path, cli):
    """INT-D18: the data-safety clause. A file that failed to load never
    reaches project.ideas; suggesting its id would tell the reader — usually
    an agent — to overwrite a file the user has not fixed yet."""
    _project, root = make_project(tmp_path, raw_files={"ideas/IDEA-0008.yaml": "id: [unclosed\n"})
    code, out, _err = cli("-p", str(root), "ideas")
    assert code == 0
    assert _tail(out) == TAIL + "IDEA-0009"
    assert (root / ".planning" / "ideas" / "IDEA-0008.yaml").exists()


def test_yml_file_also_reserves_its_number(make_project, tmp_path, cli):
    """A top-level .yml is not loaded (ignored-idea-file) but does occupy the name."""
    _project, root = make_project(
        tmp_path,
        raw_files={"ideas/IDEA-0003.yml": "id: IDEA-0003\ntitle: T\nstatus: OPEN\n"},
    )
    code, out, _err = cli("-p", str(root), "ideas")
    assert code == 0
    assert _tail(out) == TAIL + "IDEA-0004"


def test_subdirectory_files_do_not_reserve_numbers(make_project, tmp_path, cli):
    """Only top-level names can collide with a new top-level file."""
    _project, root = make_project(
        tmp_path,
        raw_files={"ideas/archive/IDEA-0100.yaml": "id: IDEA-0100\ntitle: T\nstatus: OPEN\n"},
    )
    code, out, _err = cli("-p", str(root), "ideas")
    assert code == 0
    assert _tail(out) == TAIL + "IDEA-0001"


def test_non_idea_ids_do_not_participate(make_project, tmp_path, cli):
    """INT-D18: anchored match — a substring match would count MY-IDEA-0042-x."""
    _project, root = make_project(
        tmp_path,
        raw_files={"ideas/MY-IDEA-0042-x.yaml": "id: MY-IDEA-0042-x\ntitle: T\nstatus: OPEN\n"},
    )
    code, out, _err = cli("-p", str(root), "ideas")
    assert code == 0
    assert _tail(out) == TAIL + "IDEA-0001"


def test_unpadded_ids_are_normalized(make_project, tmp_path, cli):
    """IDEA-7 counts as 7; the suggestion is always four-digit padded."""
    _project, root = make_project(
        tmp_path,
        raw_files={"ideas/IDEA-7.yaml": "id: IDEA-7\ntitle: T\nstatus: OPEN\n"},
    )
    code, out, _err = cli("-p", str(root), "ideas")
    assert code == 0
    assert _tail(out) == TAIL + "IDEA-0008"


def test_numbers_above_the_padding_width_grow(make_project, tmp_path, cli):
    _project, root = make_project(
        tmp_path,
        raw_files={"ideas/IDEA-9999.yaml": "id: IDEA-9999\ntitle: T\nstatus: OPEN\n"},
    )
    code, out, _err = cli("-p", str(root), "ideas")
    assert code == 0
    assert _tail(out) == TAIL + "IDEA-10000"


def test_hint_is_independent_of_filters(make_project, tmp_path, cli):
    """INT-D18 point 4: filtering is a display choice, not a data question."""
    raw = {
        "ideas/IDEA-0001.yaml": "id: IDEA-0001\ntitle: T\nstatus: OPEN\nrelates_to: [P1]\n",
        "ideas/IDEA-0002.yaml": "id: IDEA-0002\ntitle: T\nstatus: DISCARDED\n",
    }
    _project, root = make_project(
        tmp_path,
        node_dicts=[{"id": "P1", "title": "P1", "type": "PROGRAM", "status": "DONE"}],
        raw_files=raw,
    )
    for argv in (
        ("ideas",),
        ("ideas", "--status", "OPEN"),
        ("ideas", "--status", "DISCARDED"),
        ("ideas", "--for", "P1"),
    ):
        code, out, _err = cli("-p", str(root), *argv)
        assert code == 0
        assert _tail(out) == TAIL + "IDEA-0003", argv


def test_hint_comes_after_the_hidden_records_note(make_project, tmp_path, cli):
    """INT-D12: the hint closes the output; the note keeps its place."""
    raw = {
        "ideas/IDEA-0001.yaml": "id: IDEA-0001\ntitle: First\nstatus: OPEN\n",
        "ideas/dup.yaml": "id: IDEA-0001\ntitle: Second\nstatus: OPEN\n",
    }
    _project, root = make_project(tmp_path, raw_files=raw)
    code, out, _err = cli("-p", str(root), "ideas")
    assert code == 0
    lines = out.splitlines()
    assert lines[-2].startswith("note: 1 idea record(s) not shown")
    assert lines[-1] == TAIL + "IDEA-0002"


def test_hint_shows_on_the_all_files_broken_path(make_project, tmp_path, cli):
    """INT-D12 boundary: 'could not be loaded' is an exit-0 listing path, not
    a failure path — and it is exactly where the disk-name rule pays off."""
    _project, root = make_project(tmp_path, raw_files={"ideas/IDEA-0004.yaml": "id: [unclosed\n"})
    code, out, err = cli("-p", str(root), "ideas")
    assert (code, err) == (0, "")
    assert out.splitlines()[0] == "idea files exist but could not be loaded; run 'pcp validate'"
    assert _tail(out) == TAIL + "IDEA-0005"


def test_no_hint_when_the_project_fails_to_load(cli, tmp_path):
    """Load failure returns EXIT_USAGE before any listing output."""
    bare = tmp_path / "no-planning"
    bare.mkdir()
    code, out, _err = cli("-p", str(bare), "ideas")
    assert code == 2
    assert TAIL not in out


def test_no_hint_on_usage_error(make_project, tmp_path, cli):
    _project, root = make_project(tmp_path)
    code, out, _err = cli("-p", str(root), "ideas", "--subtree")
    assert code == 2
    assert TAIL not in out
