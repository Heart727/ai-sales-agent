"""Isolated API regression suite: no live requests, no paid AI, no business DB writes."""
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    for args in (["-m", "unittest", "test_security", "-v"], ["test_rate_limit.py"]):
        result = subprocess.run([sys.executable, "-X", "utf8", *args], cwd=root)
        if result.returncode:
            raise SystemExit(result.returncode)
    print("All isolated security and API checks passed (no AI charges).")
