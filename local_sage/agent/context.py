"""Context management utilities for the agent."""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from local_sage.repo_graph.graph import SymbolInfo

@dataclass
class PromptBudget:
    """Tracks token usage to ensure prompts fit within the model context window.

    Attributes:
        max_tokens: The maximum allowed tokens (default 6000).
        current_tokens: The number of tokens used so far.
    """
    max_tokens: int = 6000
    current_tokens: int = 0

    def add(self, text: str) -> None:
        """Add the estimated token count of *text* to the budget."""
        self.current_tokens += len(text) // 4

    def fits(self, text: str) -> bool:
        """Return True if *text* fits within the remaining budget."""
        return self.current_tokens + (len(text) // 4) <= self.max_tokens


def get_windowed_context(symbol_info: "SymbolInfo", repo_root: Path, context_lines: int = 20) -> str:
    """Return a windowed source context around the target symbol.

    Includes the first 15 lines of the file (usually imports) and a window
    of *context_lines* before and after the symbol, capped at 100 total lines.
    """
    full_path = repo_root / symbol_info.file_path
    if not full_path.is_file():
        return ""
    
    content = full_path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    if not lines:
        return ""

    result_lines = _build_window(lines, symbol_info, context_lines)
    
    if len(result_lines) > 100:
        result_lines = result_lines[:100]
        if not result_lines[-1].endswith("\n"):
            result_lines[-1] += "\n"
        result_lines.append("# ... [truncated due to length] ...\n")

    return "".join(result_lines)

def _build_window(lines: list[str], symbol_info: "SymbolInfo", context_lines: int) -> list[str]:
    import_lines = lines[:15]
    start_idx = max(15, symbol_info.start_line - 1 - context_lines)
    end_idx = min(len(lines), symbol_info.end_line + context_lines)
    
    result_lines = import_lines[:]
    if start_idx > 15:
        result_lines.append("\n# ... [code hidden] ...\n\n")
    
    result_lines.extend(lines[start_idx:end_idx])
    return result_lines
