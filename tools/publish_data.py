"""
Maintainers: publish a data release to S3.

    python tools/publish_data.py                  # dry run: build the manifest, show what would be uploaded
    python tools/publish_data.py --upload         # upload (needs write access to the bucket)
    python tools/publish_data.py --upload --profile my-aws-profile

Uploads raw/, harmonized/ and results/ from the configured data root to
s3://wri-lcl-lea/Carbon_opportunity_cost/<release>/, together with
  MANIFEST.csv   every file with its size and SHA-256 (what fetch_data.py downloads against)
  README.md      the data card, docs/DATA_README.md
A release is immutable: the upload refuses to run if anything already exists under the release prefix.
Publish a correction as a new release (bump `release` in config.toml).

Left out: raw/gadm41/ (GADM may not be redistributed), logs, and partial downloads.
Run verify.py first, so what goes up is what reproduces the release.
"""
import argparse
import csv
import hashlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coc import paths  # noqa: E402

BUCKET = "wri-lcl-lea"
PREFIX = f"Carbon_opportunity_cost/{paths.RELEASE}"
TIERS = ("results", "harmonized", "raw")
EXCLUDE = ("raw/gadm41/",)
CONTENT_TYPES = {".tif": "image/tiff", ".csv": "text/csv", ".json": "application/json", ".md": "text/markdown",
                 ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                 ".zip": "application/zip", ".txt": "text/plain"}


def sha256(path, chunk=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


def collect():
    rows = []
    for tier in TIERS:
        for p in sorted((paths.DATA_ROOT / tier).rglob("*")):
            rel = p.relative_to(paths.DATA_ROOT).as_posix()
            if p.is_file() and not rel.startswith(EXCLUDE) and not p.name.endswith(".part"):
                rows.append({"path": rel, "bytes": p.stat().st_size, "sha256": sha256(p)})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--upload", action="store_true", help="actually upload (default: dry run)")
    ap.add_argument("--profile", help="AWS profile name (default: the SDK's usual credential chain)")
    args = ap.parse_args()

    rows = collect()
    for tier in TIERS:
        sel = [r for r in rows if r["path"].startswith(tier + "/")]
        print(f"{tier:>11}: {len(sel):4d} files, {sum(r['bytes'] for r in sel) / 1e6:8,.1f} MB")
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["path", "bytes", "sha256"], lineterminator="\n")
    w.writeheader(); w.writerows(rows)
    card = (paths.REPO / "docs" / "DATA_README.md").read_text(encoding="utf-8")
    print(f"target s3://{BUCKET}/{PREFIX}/  (+ MANIFEST.csv, README.md)")
    if not args.upload:
        print("dry run; add --upload to publish")
        return

    import botocore.session
    s3 = botocore.session.Session(profile=args.profile).create_client("s3", region_name="us-east-1")
    if s3.list_objects_v2(Bucket=BUCKET, Prefix=PREFIX + "/", MaxKeys=1).get("KeyCount", 0):
        sys.exit(f"s3://{BUCKET}/{PREFIX}/ is not empty: releases are immutable, bump `release` instead")
    for i, r in enumerate(rows, 1):
        p = paths.DATA_ROOT / r["path"]
        with open(p, "rb") as f:
            s3.put_object(Bucket=BUCKET, Key=f"{PREFIX}/{r['path']}", Body=f,
                          ContentType=CONTENT_TYPES.get(p.suffix, "application/octet-stream"),
                          Metadata={"sha256": r["sha256"]})
        if i % 50 == 0:
            print(f"  {i}/{len(rows)}")
    s3.put_object(Bucket=BUCKET, Key=f"{PREFIX}/README.md", Body=card.encode("utf-8"), ContentType="text/markdown")
    # the manifest goes last, so a release with a manifest is a complete release
    s3.put_object(Bucket=BUCKET, Key=f"{PREFIX}/MANIFEST.csv", Body=buf.getvalue().encode("utf-8"),
                  ContentType="text/csv")
    print(f"uploaded {len(rows)} files + README.md + MANIFEST.csv")


if __name__ == "__main__":
    main()
