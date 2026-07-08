import pytest
from pathlib import Path
from local_sage.validation.contracts import ContractChecker, Contract

def test_check_preconditions_ast(tmp_path: Path):
    source_code = """
def test_func():
    assert 1 == 1, "first precondition"
    assert 2 == 2
    return True
"""
    source_file = tmp_path / "test_src.py"
    source_file.write_text(source_code)
    
    checker = ContractChecker()
    
    contract = Contract(
        symbol_id="test_src.py::test_func",
        exception_types=[],
        return_shape=None,
        preconditions=["1 == 1", "2 == 2"],
        source_file=Path("test_src.py"),
        function_name="test_func"
    )
    
    failures = checker._check_preconditions_ast(contract, tmp_path)
    assert len(failures) == 0
    
    contract_fail = Contract(
        symbol_id="test_src.py::test_func",
        exception_types=[],
        return_shape=None,
        preconditions=["1 == 1", "2 == 2", "3 == 3"],
        source_file=Path("test_src.py"),
        function_name="test_func"
    )
    
    failures_fail = checker._check_preconditions_ast(contract_fail, tmp_path)
    assert len(failures_fail) == 1
    assert failures_fail[0].constraint == "preconditions"
