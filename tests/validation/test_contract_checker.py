"""Tests for ContractChecker.fix_contract_violation method using Groq API.

This tests the AI-powered contract violation fixing functionality.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from local_sage.validation.contracts import ContractChecker
from local_sage.validation.result import ContractFailure


class TestContractChecker:
    """Tests for ContractChecker fix functionality."""

    @pytest.mark.asyncio
    async def test_groq_client_basic(self) -> None:
        """Test basic Groq client functionality."""
        # Skip if no Groq API key
        if not os.environ.get("GROQ_API_KEY"):
            pytest.skip("GROQ_API_KEY not set")
            
        from local_sage.model.client import GroqClient
        
        client = GroqClient()
        
        # Test simple generation
        response = await client.generate("What is 2+2?", "Answer briefly.")
        
        assert response.text is not None
        assert len(response.text) > 0
        print(f"✅ Groq client working. Response: {response.text[:100]}")

    @pytest.mark.asyncio
    async def test_fix_contract_violation_with_groq(self, tmp_path: Path) -> None:
        """Test that fix_contract_violation can fix a simple exception type violation using Groq."""
        # Skip if no Groq API key
        if not os.environ.get("GROQ_API_KEY"):
            pytest.skip("GROQ_API_KEY not set")
            
        # Create a source file with a contract violation
        source_code = '''def calculate_ratio(a: int, b: int) -> float:
    """Calculate the ratio a/b.
    
    Args:
        a: Numerator
        b: Denominator
        
    Returns:
        The ratio as a float
    """
    if b == 0:
        raise ValueError("Division by zero")  # Contract violation - should be ZeroDivisionError
    return a / b
'''
        
        # Write the source file
        source_dir = tmp_path / "src"
        source_dir.mkdir()
        source_file = source_dir / "math_utils.py"
        source_file.write_text(source_code, encoding="utf-8")
        
        # Create a contract that requires ZeroDivisionError (not ValueError)
        contracts_dir = tmp_path / "contracts"
        contracts_dir.mkdir()
        contract_file = contracts_dir / "math_contract.yaml"
        contract_content = '''symbol_id: math_utils.py::calculate_ratio
exception_types:
  - ZeroDivisionError
return_shape:
  type: float
'''
        contract_file.write_text(contract_content, encoding="utf-8")
        
        # Run contract check to find the violation
        checker = ContractChecker()
        failures = checker.check(contracts_dir, source_dir)
        
        assert len(failures) == 1
        assert failures[0].constraint == "exception_types"
        assert "ValueError" in failures[0].actual
        
        # Use AI to fix the violation
        fixed_code = await checker.fix_contract_violation(failures[0], source_dir, contracts_dir)
        
        assert fixed_code is not None, "Should have generated a fix"
        assert "ZeroDivisionError" in fixed_code, "Fix should use ZeroDivisionError"
        assert "ValueError" not in fixed_code or fixed_code.count("ValueError") < source_code.count("ValueError"), "Should remove or reduce ValueError usage"
        
        # Apply the fix and verify it passes contract check
        source_file.write_text(fixed_code, encoding="utf-8")
        new_failures = checker.check(contracts_dir, source_dir)
        
        # Should have no more exception type violations
        exception_failures = [f for f in new_failures if f.constraint == "exception_types"]
        assert len(exception_failures) == 0, f"Fix should resolve exception violations, but got: {exception_failures}"
        
        print(f"✅ Successfully fixed contract violation")
        print(f"Original violations: {len(failures)}")
        print(f"Remaining violations: {len(new_failures)}")
        print(f"Fixed code length: {len(fixed_code)} chars")