"""
Download the published data into the configured data root.

    python fetch_data.py results                  # level 1: the results (~400 MB)
    python fetch_data.py harmonized               # level 2: every input on the grid (~160 MB); then run_pipeline.py --from 09
    python fetch_data.py raw                      # level 3: source datasets that may be redistributed (~0.8 GB)
    python fetch_data.py results harmonized --profile my-aws-profile

The release lives at s3://wri-lcl-lea/Carbon_opportunity_cost/<release>/ with a MANIFEST.csv listing every
file, its size and SHA-256. Files already present with the right hash are skipped; every download is
checked against the manifest. Access currently needs AWS credentials for that bucket (any the AWS SDK can
find: environment variables, `aws configure`, or an SSO profile via --profile); `--anon` for once the
release is public. GADM is not redistributable and is not in raw/; see docs/data_sources.md.
"""
import argparse
import csv
import hashlib
import io
import sys
from pathlib import Path

import botocore.session
from botocore import UNSIGNED
from botocore.config import Config

from coc import paths

BUCKET = "wri-lcl-lea"
PREFIX = f"Carbon_opportunity_cost/{paths.RELEASE}"
TIERS = ("results", "harmonized", "raw")


def client(profile=None, anon=False):
    session = botocore.session.Session(profile=profile)
    cfg = Config(signature_version=UNSIGNED) if anon else None
    return session.create_client("s3", region_name="us-east-1", config=cfg)


def sha256(path, chunk=1 << 22):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tiers", nargs="+", choices=TIERS)
    ap.add_argument("--profile", help="AWS profile name (default: the SDK's usual credential chain)")
    ap.add_argument("--anon", action="store_true", help="unsigned requests, for a public bucket")
    args = ap.parse_args()
    s3 = client(args.profile, args.anon)

    from botocore.exceptions import ClientError, NoCredentialsError
    try:
        body = s3.get_object(Bucket=BUCKET, Key=f"{PREFIX}/MANIFEST.csv")["Body"].read().decode("utf-8")
    except NoCredentialsError:
        sys.exit("No AWS credentials found. Set them up for the wri-lcl-lea bucket (e.g. `aws configure sso`, "
                 "then pass --profile), or use --anon once the release is public.")
    except ClientError as e:
        sys.exit(f"Cannot read s3://{BUCKET}/{PREFIX}/MANIFEST.csv: {e.response['Error']['Code']}. "
                 "Your credentials may not have access to this bucket, or the release is not published yet.")
    rows = [r for r in csv.DictReader(io.StringIO(body)) if r["path"].split("/", 1)[0] in args.tiers]
    total = sum(int(r["bytes"]) for r in rows)
    print(f"s3://{BUCKET}/{PREFIX}/ -> {paths.DATA_ROOT}: {len(rows)} files, {total / 1e6:,.0f} MB")

    done = skipped = 0
    for r in rows:
        dest = paths.DATA_ROOT / r["path"]
        if dest.exists() and dest.stat().st_size == int(r["bytes"]) and sha256(dest) == r["sha256"]:
            skipped += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".part")
        obj = s3.get_object(Bucket=BUCKET, Key=f"{PREFIX}/{r['path']}")
        with open(tmp, "wb") as f:
            for chunk in iter(lambda: obj["Body"].read(1 << 22), b""):
                f.write(chunk)
        if sha256(tmp) != r["sha256"]:
            tmp.unlink()
            sys.exit(f"checksum mismatch for {r['path']}; nothing kept for it")
        tmp.replace(dest)
        done += 1
        if done % 25 == 0:
            print(f"  {done + skipped}/{len(rows)}")
    print(f"downloaded {done}, already present {skipped}")


if __name__ == "__main__":
    main()
