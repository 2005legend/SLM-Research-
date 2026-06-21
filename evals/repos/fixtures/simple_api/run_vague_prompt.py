import subprocess
import shutil
import os
import sys
from pathlib import Path

repo_dir = Path(r"C:\Users\USER\sidaarth\SLM research\evals\repos\fixtures\simple_api")
sage_dir = repo_dir / ".sage"

for i in range(1, 11):
    print(f"\n=== RUN {i} ===")
    
    # 1. Reset the buggy core.py
    core_file = repo_dir / "simple_api" / "core.py"
    core_file.write_text('''"""Core API helpers with an intentional divide-by-zero bug."""\n\n\ndef divide(a: float, b: float) -> float:\n    """Return a divided by b.\n\n    Raises:\n        ZeroDivisionError: When *b* is zero.\n    """\n    if b == 0:\n        raise ValueError("Divisor cannot be zero")\n    return a / b\n''', encoding="utf-8")

    # 2. Wipe the session
    if sage_dir.exists():
        shutil.rmtree(sage_dir, ignore_errors=True)
        
    # 3. Run the task
    cmd = [sys.executable, "-m", "local_sage.__main__", "task", "Fix divide() using contract and test context from simple_api"]
    
    process = subprocess.Popen(cmd, cwd=repo_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='cp1252', errors='replace')
    
    output_lines = []
    contract_failure_found = False
    passed_found = False
    
    for line in process.stdout:
        print(line, end="")
        output_lines.append(line)
        if "ContractFailure: symbol_id=simple_api/core.py::divide" in line or "which is not in ['ZeroDivisionError']" in line:
            contract_failure_found = True
        if "Task completed and patch applied" in line or "[OK] Task completed" in line:
            passed_found = True
            
    process.wait()
    
    if contract_failure_found:
        print(f"\n[SUCCESS] ContractFailure naturally occurred on run {i}!")
        break
    elif passed_found:
        print(f"\n[INFO] Clean success without ContractFailure on run {i}.")
        break
    else:
        print(f"\n[WARNING] Task failed for other reasons on run {i}.")
