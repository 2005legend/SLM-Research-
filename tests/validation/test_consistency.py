import pytest
from pathlib import Path
from local_sage.validation.consistency import ConsistencyChecker

from unittest.mock import patch

def test_consistency_checker(tmp_path: Path):
    checker = ConsistencyChecker()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        failures = checker.check(tmp_path, files=["foo.py"])
    assert not failures
