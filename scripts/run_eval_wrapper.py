"""
Run the evaluation harness and write the benchmark report to a known absolute path.
This avoids CWD confusion with background tasks.
"""
import sys
import os

# Ensure CWD is the repo root
os.chdir(r"C:\1DevG\ddgsSearch")
print(f"CWD: {os.getcwd()}")

sys.argv = [
    "run_eval",
    "--limit", "2",
    "--out", r"C:\1DevG\ddgsSearch\eval\benchmark_report.md",
]

from eval.run_eval import main
sys.exit(main())
