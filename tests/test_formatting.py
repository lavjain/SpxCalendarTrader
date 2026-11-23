import json
from pathlib import Path

import pytest

from app import formatting

CASES = json.loads((Path(__file__).parent / "format_cases.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c['fn']}{c['args']}")
def test_python_formatting_matches_shared_cases(case):
    assert getattr(formatting, case["fn"])(*case["args"]) == case["out"]
