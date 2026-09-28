"""
Check that a run reproduces the published release, file by file.

    python verify.py                       # harmonized/ and results/ under the configured data root
    python verify.py --only results        # e.g. after `run_pipeline.py --from 09`

Compares every layer and table listed in reference/<release>_manifest.csv against what is on disk.
Rasters are compared by a hash of their decoded pixels (dtype, shape and values, NaN treated as one
value), not of the file bytes, so a file written with different compression or metadata but identical
pixels still matches. CSV tables are compared by file hash, line endings normalized. Exit code 1 if
anything differs or is missing.

v1.0.0 reproduces bit for bit with the pinned requirements. A difference in harmonized/ from a re-run
of step 05 or 08 most likely means the streamed source (OpenLandMap, GFW) has changed since the release.

    python verify.py --write               # maintainers: regenerate the manifest from the current data
"""
import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

from coc import paths

MANIFEST = paths.REFERENCE / f"{paths.RELEASE}_manifest.csv"
# what the manifest covers: every raster, plus the tables a user reads. Timestamped files (run.json,
# the .xlsx workbook) are left out; the workbook's two result sheets are covered by their CSV twins.
TABLES = ["results/qc/coc_per_crop_summary.csv", "results/qc/coc_coverage.csv",
          "results/national/coc_by_crop_country.csv", "results/national/coc_by_crop_region.csv"]
CRLF, LF = bytes([13, 10]), bytes([10])


def pixel_hash(path):
    with rasterio.open(path) as d:
        a = d.read(1)
    if a.dtype.kind == "f":
        a = np.where(np.isnan(a), np.array(np.nan, a.dtype), a)   # one NaN bit pattern
    h = hashlib.sha256(f"{a.dtype}|{a.shape}|".encode())
    h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


def file_hash(path):
    "Hash of a text table with line endings normalized (pandas can write the OS's own)."
    return hashlib.sha256(Path(path).read_bytes().replace(CRLF, LF)).hexdigest()


def entries(root):
    "(relative path, kind) for everything the manifest should cover that exists under root."
    for tier in ("harmonized", "results"):
        for p in sorted((root / tier).rglob("*.tif")):
            yield p.relative_to(root).as_posix(), "pixels"
    for t in TABLES:
        if (root / t).exists():
            yield t, "file"


def digest(root, rel, kind):
    return pixel_hash(root / rel) if kind == "pixels" else file_hash(root / rel)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--only", choices=["harmonized", "results"])
    ap.add_argument("--write", action="store_true", help="regenerate the manifest (maintainers)")
    args = ap.parse_args()
    root = paths.DATA_ROOT

    if args.write:
        rows = [{"path": rel, "kind": kind, "sha256": digest(root, rel, kind)} for rel, kind in entries(root)]
        pd.DataFrame(rows).to_csv(MANIFEST, index=False, encoding="utf-8")
        print(f"wrote {len(rows)} entries -> {MANIFEST}")
        return 0

    m = pd.read_csv(MANIFEST)
    if args.only:
        m = m[m["path"].str.startswith(args.only + "/")]
    status = []
    for r in m.itertuples():
        if not (root / r.path).exists():
            status.append((r.path, "MISSING"))
        else:
            status.append((r.path, "OK" if digest(root, r.path, r.kind) == r.sha256 else "DIFF"))
    df = pd.DataFrame(status, columns=["path", "status"])
    df["folder"] = df["path"].str.rsplit("/", n=1).str[0]
    print(f"data root: {root}   release: {paths.RELEASE}   manifest: {len(m)} entries")
    print(df.groupby(["folder", "status"]).size().unstack(fill_value=0).to_string())
    for r in df[df.status != "OK"].itertuples():
        print(f"  {r.status:7s} {r.path}")
    n_ok = int((df.status == "OK").sum())
    print(f"\n{n_ok} of {len(df)} identical to {paths.RELEASE}")
    return 0 if n_ok == len(df) else 1


if __name__ == "__main__":
    sys.exit(main())
