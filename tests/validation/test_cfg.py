import pytest
import ast
from local_sage.validation.cfg import CFGChecker, CFGWarning

def test_cfg_unreachable_after_return():
    code = """
def my_func():
    return 1
    print("unreachable")
"""
    checker = CFGChecker()
    warnings = checker.check_source(code)
    assert len(warnings) == 1
    assert warnings[0].line_number == 4
    assert "Unreachable code" in warnings[0].message

def test_cfg_unreachable_after_raise():
    code = """
def my_func():
    if True:
        raise ValueError("error")
        return 2
"""
    checker = CFGChecker()
    warnings = checker.check_source(code)
    assert len(warnings) == 1
    assert warnings[0].line_number == 5

def test_cfg_valid_code():
    code = """
def my_func(x):
    if x:
        return 1
    else:
        return 2
    
def another():
    pass
"""
    checker = CFGChecker()
    warnings = checker.check_source(code)
    assert len(warnings) == 0
