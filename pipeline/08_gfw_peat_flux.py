"""
08 — Drained agricultural organic (peat) soils and their emissions: WRI/GFW -> harmonized/gfw_peat/

    gfw_peat/gfw_peat_ag_frac.tif              drained AGRICULTURAL organic soil, fraction of the cell (0-1)
    gfw_peat/gfw_peat_ag_ef_tco2e_ha_yr.tif    on-site CO2 + N2O per drained hectare, tCO2e/ha/yr
    gfw_peat/qc.json                           totals against GFW's own zonal statistics

Source: the WRI/GFW AFOLU organic-soils flux model, version 1_0_1, run ogh_mixed_f1_f15_f2_20260513,
period 2016_2020 (the one matching MapSPAM 2020), public at s3://gfw2-data. Only the `combined_state`
class raster is read: GFW's per-hectare CO2 and N2O are an exact lookup on that class (reference/
gfw_combined_state_lookup.csv, derived from GFW's own tables), so the class raster carries the whole
signal and yields the land-use filter in the same pass. Its emission factors are the IPCC 2013 Wetlands
Supplement ones (N2O at GWP100 = 273).

Only agriculture is kept: Cropland (boreal, temperate, tropical), Oil Palm and Other plantation. GFW's
~71 Mha of drained organic soil is mostly forestry, settlement and grassland drainage, which must not be
charged to crops. Grassland is dropped because the method has no pasture. On-site CO2 + N2O only:
off-site DOC, CH4 and fire are left out, as in Wirsenius et al., so the flux is a lower bound.

Method: every 10x10 degree tile (0.00025 deg, ~30 m) is read in 1000-row windows, each exactly 3 grid
rows. A native pixel belongs to the grid cell containing its centre, and both axes collapse with
np.add.reduceat. Pixel areas are analytic on the authalic sphere (R = 6371007.181 m, as GFW's own
pixel-area layer), and tiles stream over HTTPS through GDAL /vsicurl/; no credentials needed.

Note on reproducibility: WRI has fixed this dataset IN PLACE before (the 2016_2020 land-use labels, on
2026-08-26, same path). A re-run reads whatever is there now, which is why the v1.0.0 layers are
published in harmonized/. ~60 min.

    python pipeline/08_gfw_peat_flux.py
    python pipeline/08_gfw_peat_flux.py --tiles 00N_110E 00N_100E      # smoke test (writes partial layers)
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coc import paths  # noqa: E402
from coc.grid import TH, TT, TW, save  # noqa: E402

os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")

BUCKET = "gfw2-data"
S3_BASE = "climate/AFOLU_flux_model/organic_soils/outputs/version_1_0_1"
RUN = "ogh_mixed_f1_f15_f2_20260513"
PERIOD = "2016_2020"
OUT_DATE = "20260525"
STATE_PREFIX = f"{S3_BASE}/combined_state/{RUN}/five_year_intervals/{PERIOD}/40000_pixels/{OUT_DATE}/"

NATIVE_RES = 0.00025
TILE_DEG = 10
ROWS_PER_WINDOW = 1000                  # = 0.25 deg = exactly 3 grid rows
R_AUTHALIC = 6371007.181

# GFW's own totals for this run, period and land-use filter (master zonal table
# zonal_stats/<run>_starting_cpf_global_wdpa_fixed/20260802/master_zonal_full_disaggregation.csv).
# The build should land within a fraction of a percent of them.
QC_TARGET_AREA_MHA = 22.004
QC_TARGET_FLUX_MT = 948.0


def load_lookup():
    "(ef, is_ag, known) as dense arrays indexed by combined_state code."
    rows = list(csv.DictReader(open(paths.GFW_LOOKUP, encoding="utf-8")))
    n = max(int(r["combined_state"]) for r in rows) + 1
    ef = np.zeros(n, "float32")
    ag = np.zeros(n, bool)
    known = np.zeros(n, bool)
    for r in rows:
        c = int(r["combined_state"])
        known[c] = True
        if int(r["is_ag"]):
            ag[c] = True
            ef[c] = float(r["ef_co2_n2o_tco2e_ha_yr"])
    return ef, ag, known


def list_state_tiles():
    import botocore.session
    from botocore import UNSIGNED
    from botocore.config import Config
    c = botocore.session.get_session().create_client(
        "s3", region_name="us-east-1", config=Config(signature_version=UNSIGNED))
    keys = []
    for page in c.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=STATE_PREFIX):
        keys += [o["Key"] for o in page.get("Contents", []) if o["Key"].endswith(".tif")]
    return sorted(keys)


def tile_origin(tile_id):
    "Top-left (lon, lat) of a tile id such as 00N_110E."
    m = re.match(r"^(\d{2})([NS])_(\d{3})([EW])$", tile_id)
    if not m:
        raise ValueError(f"unparseable tile id {tile_id!r}")
    lat = int(m.group(1)) * (1 if m.group(2) == "N" else -1)
    lon = int(m.group(3)) * (1 if m.group(4) == "E" else -1)
    return lon, lat


def row_area_ha(lat_top, n_rows):
    "Area of one native pixel in each of n_rows rows starting at lat_top, in hectares."
    lat1 = np.deg2rad(lat_top - np.arange(n_rows) * NATIVE_RES)
    lat2 = np.deg2rad(lat_top - (np.arange(n_rows) + 1) * NATIVE_RES)
    m2 = R_AUTHALIC ** 2 * np.deg2rad(NATIVE_RES) * (np.sin(lat1) - np.sin(lat2))
    return (m2 / 1e4).astype("float64")


def group_starts(centres_deg, origin_deg, cell_deg, sign=1):
    "Start offsets of each run of native pixels sharing a grid cell, and that cell's index."
    idx = np.floor(sign * (centres_deg - origin_deg) / cell_deg).astype("int64")
    starts = np.flatnonzero(np.r_[True, idx[1:] != idx[:-1]])
    return starts, idx[starts]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tiles", nargs="*", default=None, help="tile ids to process (default: all)")
    args = ap.parse_args()

    ef_lut, ag_lut, known_lut = load_lookup()
    n_codes = ef_lut.size
    keys = list_state_tiles()
    if args.tiles:
        keys = [k for k in keys if Path(k).name.split("__")[0] in set(args.tiles)]
    print(f"{len(keys)} combined_state tiles, run {RUN}, period {PERIOD}")

    acc_area = np.zeros((TH, TW), "float64")      # drained agricultural organic soil, ha
    acc_flux = np.zeros((TH, TW), "float64")      # ha x EF = tCO2e/yr
    unknown_px = 0
    ncol = int(TILE_DEG / NATIVE_RES)
    col_centres = (np.arange(ncol) + 0.5) * NATIVE_RES
    col_starts, _ = group_starts(col_centres, 0.0, TT.a)

    t_start = time.time()
    for n, key in enumerate(keys, 1):
        tile_id = Path(key).name.split("__")[0]
        lon0, lat0 = tile_origin(tile_id)
        c0 = int(round((lon0 - TT.c) / TT.a))
        tile_area = 0.0
        with rasterio.open(f"https://{BUCKET}.s3.us-east-1.amazonaws.com/{key}") as d:
            assert (d.width, d.height) == (ncol, ncol), f"unexpected size for {tile_id}"
            for r0 in range(0, ncol, ROWS_PER_WINDOW):
                nr = min(ROWS_PER_WINDOW, ncol - r0)
                block = d.read(1, window=Window(0, r0, ncol, nr))
                oob = block >= n_codes                   # a class the lookup has never seen
                if oob.any():
                    unknown_px += int(oob.sum())
                    block = np.where(oob, 0, block)
                unk = ~known_lut[block]
                if unk.any():
                    unknown_px += int(unk.sum())
                mask = ag_lut[block]
                if not mask.any():
                    continue
                ef = np.where(mask, ef_lut[block], 0.0).astype("float32")
                cnt_c = np.add.reduceat(mask.astype("float32"), col_starts, axis=1)
                ef_c = np.add.reduceat(ef, col_starts, axis=1)
                lat_top = lat0 - r0 * NATIVE_RES
                a = row_area_ha(lat_top, nr)[:, None]
                row_centres = lat_top - (np.arange(nr) + 0.5) * NATIVE_RES
                row_starts, row_idx = group_starts(row_centres, TT.f, TT.a, sign=-1)
                area_rc = np.add.reduceat(cnt_c * a, row_starts, axis=0)
                flux_rc = np.add.reduceat(ef_c * a, row_starts, axis=0)
                acc_area[row_idx, c0:c0 + area_rc.shape[1]] += area_rc
                acc_flux[row_idx, c0:c0 + flux_rc.shape[1]] += flux_rc
                tile_area += float(area_rc.sum())
        if tile_area > 0 or n % 20 == 0:
            print(f"[{n:3d}/{len(keys)}] {tile_id}  {tile_area / 1e6:8.4f} Mha")

    lat1 = np.deg2rad(TT.f + np.arange(TH) * TT.e)
    lat2 = np.deg2rad(TT.f + (np.arange(TH) + 1) * TT.e)
    cell_ha = (R_AUTHALIC ** 2 * np.deg2rad(TT.a) * (np.sin(lat1) - np.sin(lat2)) / 1e4)[:, None]
    frac = np.clip(acc_area / cell_ha, 0.0, 1.0).astype("float32")
    ef_out = np.where(acc_area > 0, acc_flux / np.maximum(acc_area, 1e-12), 0.0).astype("float32")
    save(frac, paths.H_GFW_PEAT / "gfw_peat_ag_frac.tif", tags={"units": "fraction of cell"})
    save(ef_out, paths.H_GFW_PEAT / "gfw_peat_ag_ef_tco2e_ha_yr.tif", tags={"units": "tCO2e per drained ha per yr"})

    tot_area, tot_flux = float(acc_area.sum()), float(acc_flux.sum())
    qc = {"run": RUN, "period": PERIOD, "output_date": OUT_DATE, "tiles_processed": len(keys),
          "drained_ag_area_Mha": round(tot_area / 1e6, 4),
          "drained_ag_flux_MtCO2e_yr": round(tot_flux / 1e6, 3),
          "mean_ef_tco2e_ha_yr": round(tot_flux / tot_area, 4) if tot_area else 0.0,
          "gfw_zonal_area_Mha": QC_TARGET_AREA_MHA, "gfw_zonal_flux_MtCO2e_yr": QC_TARGET_FLUX_MT,
          "area_pct_diff": round(100 * (tot_area / 1e6 - QC_TARGET_AREA_MHA) / QC_TARGET_AREA_MHA, 3),
          "flux_pct_diff": round(100 * (tot_flux / 1e6 - QC_TARGET_FLUX_MT) / QC_TARGET_FLUX_MT, 3),
          "cells_with_ag_peat": int((acc_area > 0).sum()),
          "unknown_class_pixels": unknown_px,
          "gases": "on-site CO2 + N2O (no off-site DOC, no CH4, no fire)",
          "land_uses": "Cropland (boreal/temperate/tropical), Oil Palm, Other plantation"}
    (paths.H_GFW_PEAT / "qc.json").write_text(json.dumps(qc, indent=2), encoding="utf-8")
    print(f"drained agricultural peat {tot_area / 1e6:.4f} Mha ({qc['area_pct_diff']:+.2f}% vs GFW), "
          f"{tot_flux / 1e6:.3f} Mt CO2e/yr ({qc['flux_pct_diff']:+.2f}%), {time.time() - t_start:.0f}s "
          f"-> {paths.H_GFW_PEAT}")
    if unknown_px:
        print(f"note: {unknown_px:,} pixels carried a class absent from the lookup "
              f"(53 of class 10240, non-peat, are expected for 2016_2020)")


if __name__ == "__main__":
    main()
