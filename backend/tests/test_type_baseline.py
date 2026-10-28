from collections import Counter

import pytest

from scripts.check_type_baseline import compare_baseline, parse_output


def test_baseline_rejects_new_and_extra_errors() -> None:
    baseline = {
        "checked_files": 2,
        "errors": [
            {"path": "app/a.py", "code": "arg-type", "message": "bad", "count": 1}
        ],
    }
    actual = Counter({("app/a.py", "arg-type", "bad"): 2})

    assert compare_baseline(actual, 2, baseline) == ["app/a.py [arg-type] +1: bad"]
    assert compare_baseline(
        Counter({("tests/new.py", "assignment", "new error"): 1}), 2, baseline
    ) == ["tests/new.py [assignment] +1: new error"]
    assert compare_baseline(Counter(), 1, baseline) == [
        "Coverage shrank: checked 1 files; baseline is 2"
    ]


def test_parser_normalizes_paths_and_checks_summary() -> None:
    output = (
        "app\\a.py:12: error: bad  [arg-type]\n"
        "app/a.py:19: error: bad  [arg-type]\n"
        "Found 2 errors in 1 file (checked 2 source files)\n"
    )

    assert parse_output(output) == (Counter({("app/a.py", "arg-type", "bad"): 2}), 2)
    with pytest.raises(ValueError, match="summary"):
        parse_output(output.replace("Found 2 errors", "Found 3 errors"))
    with pytest.raises(ValueError, match="Unrecognized"):
        parse_output("other/file.py:1: error: bad  [arg-type]\n")
