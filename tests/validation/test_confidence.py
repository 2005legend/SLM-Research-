import pytest
from local_sage.validation.confidence import PatchConfidenceScorer

def test_confidence_scoring_passes():
    scorer = PatchConfidenceScorer()
    # High confidence scenario
    score = scorer.score(
        syntax_passed=True, 
        mypy_passed=True, 
        cfg_warnings=0,
        contract_passed=True
    )
    assert score.score >= 0.6
    assert score.passed is True

def test_confidence_scoring_fails_due_to_unreachable_code():
    scorer = PatchConfidenceScorer()
    # CFG warnings reduce confidence
    score = scorer.score(
        syntax_passed=True, 
        mypy_passed=True, 
        cfg_warnings=4,
        contract_passed=False
    )
    assert score.score < 0.6
    assert score.passed is False
