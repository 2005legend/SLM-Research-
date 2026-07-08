import subprocess
import sys

commands = [
    [sys.executable, "-m", "local_sage", "task", "Refactor: add helper to return magic number"],
    [sys.executable, "-m", "local_sage", "plan", "Create a helper function and document it in README", "--yes"],
    [sys.executable, "-m", "local_sage", "status"],
]

for cmd in commands:
    print("\n---- RUN: {} ----".format(" ".join(cmd)))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        print("EXIT CODE:", proc.returncode)
        print("STDOUT:\n", proc.stdout)
        print("STDERR:\n", proc.stderr)
    except Exception as e:
        print("ERROR running command:", e)
