"""
03 — Geography keys + the COC tool's agricultural plant carbon -> harmonized/geography/, harmonized/ag_plant_tool/

Geography (see coc/geography.py): GADM 4.1 ADM0 + the tool's Table A-1 ->
    geography/geo_key.tif          the tool geography of each cell (1-10 region, 11-14 override country)
    geography/country_key.tif      one code per country, for national aggregation (step 10)
    geography/country_key.csv      what each country_key code is
    geography/qc/                  country -> region table + the strict-fail logs (all empty on success)

Agricultural plant carbon from the tool: column F of the "Raw LO and COC data" sheet (tC/ha, the same
values as the tool's Table A-8), stated per crop for Global / regions / override countries, painted
onto geo_key with the fallback chain in coc.geography.value_vector:
    ag_plant_tool/<item>_ag_plant_tc_ha.tif     one per tool item with a value (60)
    ag_plant_tool/qc/                           raster manifest + where each painted value came from

These are the fallback for the 17 crops the Cornell biomass layers do not cover (see coc/engine.py).
Three SPAM crops have no tool item at all (REST, TOBA, RUBB): they take the per-cell mean of every
file here instead, so all 60 files matter, not only the ones the concordance names. (Rubber then
swaps that mean for the IPCC value, keeping only its footprint.)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coc import paths  # noqa: E402
from coc import geography as G  # noqa: E402
from coc.grid import TH, TW, save  # noqa: E402

COL_F = 5
SUFFIX = "ag_plant_tc_ha"


def column_lookup(xlsx, col_val):
    """{item_key: {REGION string: value}}, display names, and value conflicts (first value wins).

    Items are keyed on their normalized name so spelling/case variants collapse into one. Only the 15
    geographies that carry values (Global, 10 regions, 4 overrides) are read; blank or text cells leave
    that geography unset, so value_vector falls back to the parent region or Global.
    """
    raw = pd.read_excel(xlsx, sheet_name=G.SHEET_RAW, header=None, engine="openpyxl")
    lookup, display, name_counts, conflicts = {}, {}, {}, []
    for i in range(G.DATA_START_ROW, len(raw)):
        region, item, val = raw.iat[i, G.COL_REGION], raw.iat[i, G.COL_ITEM], raw.iat[i, col_val]
        if item is None or (isinstance(item, float) and pd.isna(item)):
            continue
        region = None if region is None or (isinstance(region, float) and pd.isna(region)) else str(region).strip()
        if region not in G.VALID_REGION_VALUES:
            continue
        item_str = str(item).strip()
        key = G.norm(item_str)
        if not key:
            continue
        name_counts.setdefault(key, {}).setdefault(item_str, 0)
        name_counts[key][item_str] += 1
        if not isinstance(val, (int, float)) or (isinstance(val, float) and pd.isna(val)):
            continue
        val = float(val)
        d = lookup.setdefault(key, {})
        if region in d:
            if abs(d[region] - val) > 1e-9:
                conflicts.append((key, region, d[region], val))
            continue
        d[region] = val
    for key, sp in name_counts.items():
        display[key] = max(sp.items(), key=lambda kv: kv[1])[0]
    return lookup, display, conflicts


def main():
    if not paths.COC_TOOL_XLSX.exists():
        sys.exit(f"{paths.COC_TOOL_XLSX} not found — see README for the COC tool workbook")
    geo_dir = paths.H_GEOGRAPHY

    # --- geography: strict, since an unresolved country would become a hole in every layer ---
    gdf, df, failures = G.build_geography(paths.COC_TOOL_XLSX)
    G.write_geo_qc(df, gdf, failures, geo_dir / "qc")
    if any(failures.values()):
        for k, v in failures.items():
            if v:
                print(f"  {k}: {len(v)} -> {[x.get('country_name') or x.get('iso3') for x in v]}")
        sys.exit("ABORT: geography incomplete; see harmonized/geography/qc/")
    geo_key, n_shapes = G.rasterize_geo_key(gdf)
    save(geo_key, geo_dir / "geo_key.tif", dtype="uint8", nodata=G.GEOKEY_NODATA)
    country_key, table = G.rasterize_country_key(gdf)
    save(country_key, geo_dir / "country_key.tif", dtype="int32", nodata=0)
    table.to_csv(geo_dir / "country_key.csv", index=False, encoding="utf-8")
    print(f"geography: {len(gdf)} countries, {int((geo_key > 0).sum()):,} cells "
          f"({100 * (geo_key > 0).sum() / (TW * TH):.2f}% of grid) -> {geo_dir}")

    # --- column F, painted per tool item ---
    code_to_label, region_value_by_code = G.code_maps()
    lookup, display, conflicts = column_lookup(paths.COC_TOOL_XLSX, COL_F)
    out_dir = paths.H_AG_PLANT_TOOL
    manifest, status_rows = [], []
    for key in sorted(lookup, key=lambda k: display[k].lower()):
        name, slug = display[key], G.slugify(key)
        vals, status = G.value_vector(lookup[key])
        out = np.where(geo_key > 0, vals[geo_key], np.float32(np.nan)).astype("float32")
        save(out, out_dir / f"{slug}_{SUFFIX}.tif")
        finite = out[np.isfinite(out)]
        manifest.append({"item": name, "slug": slug, "filename": f"{slug}_{SUFFIX}.tif",
                         "has_global": G.GLOBAL_NAME in lookup[key],
                         "n_geog_present": sum(1 for c in range(1, 15) if status[c] == "present"),
                         "n_geog_filled": sum(1 for c in range(1, 15) if status[c] in ("from_parent", "from_global")),
                         "n_valid_cells": int(finite.size),
                         "min": float(finite.min()) if finite.size else None,
                         "mean": float(finite.mean()) if finite.size else None,
                         "max": float(finite.max()) if finite.size else None})
        for c in range(1, 15):
            status_rows.append({"item": name, "geo_code": c, "geo_label": code_to_label[c],
                                "region_value": region_value_by_code[c], "status": status[c],
                                "value": vals[c] if np.isfinite(vals[c]) else ""})
    (out_dir / "qc").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(manifest).to_csv(out_dir / "qc" / "raster_manifest.csv", index=False, encoding="utf-8")
    pd.DataFrame(status_rows).to_csv(out_dir / "qc" / "value_status.csv", index=False, encoding="utf-8")
    if conflicts:
        pd.DataFrame(conflicts, columns=["item_key", "region", "value_kept", "value_dropped"]) \
            .to_csv(out_dir / "qc" / "value_conflicts.csv", index=False, encoding="utf-8")
    print(f"tool ag plant (col F): {len(manifest)} items -> {out_dir}")


if __name__ == "__main__":
    main()
