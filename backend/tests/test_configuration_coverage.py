"""Coverage accounting must fail closed on missing and failed validators."""

from scripts.check_configuration_coverage import discover_paths, execute, summarize


def test_unknown_configuration_is_uncovered(tmp_path):
    directory = tmp_path / ".github/workflows"
    directory.mkdir(parents=True)
    (directory / "new.yaml").write_text("name: new", encoding="utf-8")
    paths = discover_paths(tmp_path, tracked=[])
    result = summarize(paths, [], {"application": 0})
    assert result["uncovered_paths"] == [".github/workflows/new.yaml"]
    assert result["uncovered_count"] == 1
    assert result["exit_code"] == 1


def test_failed_tool_cannot_produce_successful_coverage():
    result = summarize(
        ["docker-compose.yml"],
        [{"path": "docker-compose.yml", "status": "pass"}],
        {"compose": 1},
    )
    assert result["exit_code"] == 1


def test_missing_result_and_failed_path_are_counted_separately():
    result = summarize(
        ["first.yaml", "second.ini"],
        [{"path": "first.yaml", "status": "fail"}],
        {"application": 1},
    )
    assert result["failed_count"] == 1
    assert result["uncovered_count"] == 1
    assert result["exit_code"] == 1


def test_only_complete_success_passes():
    result = summarize(
        ["first.yaml"],
        [{"path": "first.yaml", "status": "pass"}],
        {"application": 0, "actionlint": 0, "compose": 0},
    )
    assert result["uncovered_count"] == 0
    assert result["exit_code"] == 0


def test_new_tracked_backend_configuration_is_discovered(tmp_path):
    assert discover_paths(
        tmp_path, tracked=["backend/new.toml", "backend/app/x.py"]
    ) == ["backend/new.toml"]


def test_duplicate_or_unknown_status_is_rejected():
    for records in (
        [{"path": "first.yaml", "status": "UNKNOWN"}],
        [
            {"path": "first.yaml", "status": "pass"},
            {"path": "first.yaml", "status": "pass"},
        ],
    ):
        assert summarize(["first.yaml"], records, {"application": 0})["exit_code"] == 1


def test_missing_authority_tool_is_a_failure(tmp_path):
    assert execute([str(tmp_path / "missing-authority-tool")], tmp_path) == 127
