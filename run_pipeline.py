"""
Run the pipeline steps in order.

    python run_pipeline.py                 # everything: 01-10 (~70 min; steps 05 and 08 stream from the internet)
    python run_pipeline.py --from 09       # only the calculation + national tables, from published harmonized/
    python run_pipeline.py --only 03 04    # specific steps

Steps 01-08 build harmonized/ from raw/; 09-10 read only harmonized/. So a user who downloads the
published harmonized layers can start at 09.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

PIPELINE = Path(__file__).resolve().parent / "pipeline"
STEPS = sorted(p for p in PIPELINE.glob("[0-9][0-9]_*.py"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="start", default="01", help="first step to run (e.g. 09)")
    ap.add_argument("--only", nargs="*", help="run just these steps")
    args = ap.parse_args()
    todo = [s for s in STEPS if (s.name[:2] in args.only if args.only else s.name[:2] >= args.start)]
    if not todo:
        sys.exit(f"no steps selected from {[s.name for s in STEPS]}")
    for step in todo:
        print(f"\n=== {step.name} ===", flush=True)
        t0 = time.time()
        if subprocess.run([sys.executable, str(step)]).returncode:
            sys.exit(f"{step.name} failed")
        print(f"=== {step.name} done in {time.time() - t0:.0f}s ===", flush=True)


if __name__ == "__main__":
    main()
