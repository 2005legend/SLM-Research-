"""Consistency validation after Harness multi-file tasks."""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ConsistencyFailure:
    message: str
    file_path: str | None = None


class ConsistencyChecker:
    """Verifies whole-repo state consistency using global checks like mypy."""

    def check(self, repo_root: Path, files: list[str] | None = None) -> list[ConsistencyFailure]:
        """Run a global consistency check across the entire repository or specific files."""
        import subprocess
        import sys
        
        failures = []
        try:
            cmd = [sys.executable, "-m", "mypy"]
            if files:
                cmd.extend(files)
            else:
                cmd.append(".")
                
            result = subprocess.run(
                cmd,
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                check=False
            )
            if result.returncode != 0:
                for line in result.stdout.splitlines():
                    if "error:" in line:
                        failures.append(ConsistencyFailure(message=line.strip()))
        except FileNotFoundError:
            failures.append(ConsistencyFailure(message="mypy not found"))
            
        # Run CFG analysis on target files
        from local_sage.validation.cfg import CFGChecker
        cfg_checker = CFGChecker()
        if files:
            for file_path in files:
                p = Path(file_path)
                if p.exists() and p.suffix == ".py":
                    source = p.read_text(encoding="utf-8")
                    warnings = cfg_checker.check_source(source)
                    for w in warnings:
                        failures.append(
                            ConsistencyFailure(
                                message=f"CFG Warning: {w.message} at line {w.line_number}",
                                file_path=str(p)
                            )
                        )
            
        return failures
