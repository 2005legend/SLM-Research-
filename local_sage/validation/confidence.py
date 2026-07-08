"""Confidence scoring for generated patches."""

from dataclasses import dataclass
from typing import Any

@dataclass
class ConfidenceScore:
    """A confidence score for a patch, ranging from 0.0 to 1.0."""
    score: float
    factors: dict[str, float]
    
    @property
    def passed(self) -> bool:
        """A patch passes if its confidence score is >= 0.6."""
        return self.score >= 0.6

class PatchConfidenceScorer:
    """Calculates confidence score for a patch based on static analysis signals."""
    
    def score(self, 
              syntax_passed: bool = False, 
              mypy_passed: bool = False, 
              cfg_warnings: int = 0,
              contract_passed: bool = False,
              complexity_score: int = 0) -> ConfidenceScore:
        """Calculate confidence based on various validation signals."""
        factors: dict[str, float] = {}
        total = 0.0
        
        if syntax_passed:
            factors["syntax"] = 0.4
            total += 0.4
            
        if mypy_passed:
            factors["mypy"] = 0.3
            total += 0.3
            
        if contract_passed:
            factors["contract"] = 0.1
            total += 0.1
            
        if cfg_warnings == 0:
            factors["cfg"] = 0.2
            total += 0.2
        else:
            factors["cfg"] = -0.1 * cfg_warnings
            total -= 0.1 * cfg_warnings
            
        if complexity_score > 10:
            factors["complexity"] = -0.2
            total -= 0.2
            
        final_score = max(0.0, min(1.0, total))
        return ConfidenceScore(score=final_score, factors=factors)
