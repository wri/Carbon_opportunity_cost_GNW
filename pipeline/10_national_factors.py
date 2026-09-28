"""
10 — National and regional factors in the COC tool's format -> results/national/

Aggregates step 09's inputs back to crop x country and crop x region (Global + the 10 Table A-1 regions),
and lays the result beside the tool's own factors. See coc/national.py. ~3 min.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coc import national  # noqa: E402

if __name__ == "__main__":
    national.run()
