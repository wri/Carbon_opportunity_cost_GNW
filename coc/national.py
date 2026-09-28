"""
Aggregate the gridded result to crop x country and crop x region, in the COC tool's own table format.

Writes results/national/:
  COC_factors_by_country.xlsx   four sheets:
      COC_factors_by_geography    the COC tool's own factors (reference/coc_tool_factors_by_geography.csv)
      COC by crop-country         ours, one row per crop x country, + global_production_share
      COC by crop-region          ours, Global + the 10 Table A-1 regions
      COC aligned to tool rows    ours, on exactly the tool table's rows and order, so the two diff cell by cell
  coc_by_crop_country.csv, coc_by_crop_region.csv   the two "ours" sheets as CSV

Weighting, over the cells where the crop grows and its carbon difference is defined:
  stock columns and coc_per_ha_tC_ha   crop physical-area-weighted mean
  yield_t_per_ha_yr                    sum of production / sum of harvested area
  coc_per_tonne_tCO2e                  sum of annual COC / sum of production (production-weighted)

Two unit traps, as in the tool's table: coc_per_ha_tC_ha is the carbon difference in tC/ha, neither
annualized nor CO2; and coc_per_tonne_tCO2e uses A = 30. On drained peat the soil pair is replaced by a
flux, so there coc_per_ha_tC_ha is the stock-EQUIVALENT of the blended per-ha cost, and the four stock
columns (which stay the raw mineral values) no longer add up to it.

SPAM crops are accumulated into the tool item they map to: Coffee <- arabica + robusta, Millet <- small +
pearl, Seed Cotton <- cotton + other fibre. REST, RUBB and TOBA have no tool item and keep their SPAM name.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

from coc import paths
from coc.constants import ANNUALIZATION_YEARS, CO2_PER_C
from coc.engine import ag_plant_pool, ag_soil_pool, crop_area, load_concordance, native_plant_pool, \
    native_soil_pool, peat_blend, yield_harv_prod
from coc.geography import REGIONS, norm, slugify
from coc.grid import rd

ANNOTATION_COLS = ["value_source"]      # an annotation of the tool sheet's highlighting, not a value
EXTRA_COLS = ["global_production_share"]


def run(results=None):
    results = Path(results or paths.RESULTS)
    out_dir = results / "national"
    out_dir.mkdir(parents=True, exist_ok=True)
    FACTOR = CO2_PER_C / ANNUALIZATION_YEARS

    with rasterio.open(paths.H_GEOGRAPHY / "country_key.tif") as d:
        ckey = d.read(1)
    ck = pd.read_csv(paths.H_GEOGRAPHY / "country_key.csv")
    NB = len(ck) + 1
    code2country = dict(zip(ck["country_key"], ck["country_name"]))
    code2region = dict(zip(ck["country_key"], ck["region_label"]))

    conc = load_concordance()
    # round_trip: pandas' default fast float parser is off by one ulp on ~40% of these values
    tool = pd.read_csv(paths.TOOL_FACTORS, float_precision="round_trip")
    TOOL_COLS = [c for c in tool.columns if c not in ANNOTATION_COLS]
    slug2name = {}
    for c in tool["crop"].dropna().unique():
        slug2name.setdefault(slugify(norm(c)), c)

    def crop_label(r):
        slug = r["ag_plant"]
        if slug.startswith("__"):
            return r["spam_name"]
        return slug2name.get(slug, r["spam_name"])
    labels = {r["spam_code"]: crop_label(r) for r in conc}

    np_fn, ns_fn, ap_fn, as_fn = native_plant_pool(), native_soil_pool(), ag_plant_pool(), ag_soil_pool()
    peat_fn, _ = peat_blend(conc)

    VARS = ["np", "ns", "ap", "as", "dC"]
    acc = defaultdict(lambda: {k: np.zeros(NB) for k in ["A", "P", "H", "COC"] + VARS})
    worst = 0.0

    def bsum(idx, w):
        return np.bincount(idx, weights=np.asarray(w, dtype="float64"), minlength=NB)

    for r in conc:
        sc = r["spam_code"]
        area = crop_area(sc)
        _Y, harv, prod = yield_harv_prod(sc)
        prod, harv = np.nan_to_num(prod), np.nan_to_num(harv)
        npl, ns, ap, asl = np_fn(r), ns_fn(r), ap_fn(r), as_fn(r)
        dC = npl + ns - (ap + asl)
        dC = peat_fn(FACTOR * dC, FACTOR * (npl - ap)) / FACTOR     # stock-equivalent on the peat share

        m = (ckey > 0) & np.isfinite(area) & (area > 0) & np.isfinite(dC)
        if not m.any():
            continue
        idx = ckey[m]; w = area[m].astype("float64")
        a = acc[labels[sc]]
        a["A"] += bsum(idx, w)
        for key, arr in zip(VARS, (npl, ns, ap, asl, dC)):
            a[key] += bsum(idx, arr[m].astype("float64") * w)
        a["P"] += bsum(idx, prod[m]); a["H"] += bsum(idx, harv[m])
        a["COC"] += bsum(idx, FACTOR * dC[m].astype("float64") * w)

        # the carbon difference rebuilt here must match the per-ha raster the engine wrote
        dC_engine = rd(results / "per_ha" / f"{sc}_coc_perha_tco2_yr.tif") * ANNUALIZATION_YEARS / CO2_PER_C
        d = np.abs(dC_engine - dC)[m]
        worst = max(worst, float(np.nanmax(d)) if d.size else 0.0)
    assert worst < 1e-2, f"national inputs disagree with results/per_ha (max {worst:.2e} tC/ha)"

    # --- crop x country ---
    rows = []
    for label, a in acc.items():
        A, P, H = a["A"], a["P"], a["H"]
        Ptot = P.sum()
        yld = np.divide(P, H, out=np.full(NB, np.nan), where=H > 0)
        for c in np.flatnonzero(A > 0):
            y = yld[c]
            rows.append({"crop": label, "geography": code2country[c],
                         "native_plant_tC_ha": a["np"][c] / A[c], "native_soil_tC_ha": a["ns"][c] / A[c],
                         "ag_plant_tC_ha": a["ap"][c] / A[c], "ag_soil_tC_ha": a["as"][c] / A[c],
                         "coc_per_ha_tC_ha": a["dC"][c] / A[c],
                         "land_use_ha_per_t_yr": (1.0 / y) if np.isfinite(y) and y > 0 else np.nan,
                         "yield_t_per_ha_yr": y,
                         "coc_per_tonne_tCO2e": (a["COC"][c] / P[c]) if P[c] > 0 else np.nan,
                         "global_production_share": (P[c] / Ptot) if Ptot > 0 else np.nan})
    agg = pd.DataFrame(rows)[TOOL_COLS + EXTRA_COLS]
    assert agg.duplicated(subset=["crop", "geography"]).sum() == 0, "duplicate crop-country rows"
    assert (agg.groupby("crop")["global_production_share"].sum() - 1.0).abs().max() < 1e-9

    # --- crop x region: each country's Table A-1 region (overrides fold into their parent), + Global ---
    REGION_ORDER = [REGIONS[i][0] for i in sorted(REGIONS)]
    SHORT2FULL = {lab: full for (lab, full) in REGIONS.values()}
    GEO_RANK = {"Global": 0, **{SHORT2FULL[r]: i + 1 for i, r in enumerate(REGION_ORDER)}}
    codes = np.array(sorted(code2country))
    rlab = np.array([code2region[c] for c in codes])

    def region_row(label, geography, a, sel):
        A = a["A"][sel].sum()
        if A <= 0:
            return None
        P, H = a["P"][sel].sum(), a["H"][sel].sum()
        y = (P / H) if H > 0 else np.nan
        return {"crop": label, "geography": geography,
                "native_plant_tC_ha": a["np"][sel].sum() / A, "native_soil_tC_ha": a["ns"][sel].sum() / A,
                "ag_plant_tC_ha": a["ap"][sel].sum() / A, "ag_soil_tC_ha": a["as"][sel].sum() / A,
                "coc_per_ha_tC_ha": a["dC"][sel].sum() / A,
                "land_use_ha_per_t_yr": (1.0 / y) if np.isfinite(y) and y > 0 else np.nan,
                "yield_t_per_ha_yr": y,
                "coc_per_tonne_tCO2e": (a["COC"][sel].sum() / P) if P > 0 else np.nan}

    rows_reg = []
    for label, a in acc.items():
        for geo, sel in [("Global", codes)] + [(SHORT2FULL[r], codes[rlab == r]) for r in REGION_ORDER]:
            row = region_row(label, geo, a, sel)
            if row:
                rows_reg.append(row)
    agg_reg = pd.DataFrame(rows_reg)[TOOL_COLS]
    tot_nat = sum(a["COC"].sum() for a in acc.values())
    tot_reg = sum(a["COC"][codes].sum() for a in acc.values())
    assert abs(tot_nat - tot_reg) < 1.0, "regional roll-up lost COC"

    # --- the tool's rows, filled from ours (row-wise lookup keeps the tool's order and duplicates) ---
    GEO_FROM_REGION = {"Global"} | set(SHORT2FULL.values())
    GEO_FROM_COUNTRY = {"Brazil": "Brazil", "China": "China", "India": "India", "United States": "USA"}
    VAL_COLS = [c for c in TOOL_COLS if c not in ("crop", "geography")]
    reg_lookup = agg_reg.set_index(["crop", "geography"])[VAL_COLS].to_dict("index")
    cty_lookup = agg.set_index(["crop", "geography"])[VAL_COLS].to_dict("index")
    rows_al = []
    for crop, geo in zip(tool["crop"], tool["geography"]):
        src = None
        if geo in GEO_FROM_REGION:
            src = reg_lookup.get((crop, geo))
        elif geo in GEO_FROM_COUNTRY:
            src = cty_lookup.get((crop, GEO_FROM_COUNTRY[geo]))
        rows_al.append({"crop": crop, "geography": geo, **(src if src is not None else {c: np.nan for c in VAL_COLS})})
    aligned = pd.DataFrame(rows_al)[TOOL_COLS]

    agg_out = agg.sort_values(["crop", "geography"]).reset_index(drop=True)
    reg_out = (agg_reg.assign(_r=agg_reg["geography"].map(GEO_RANK)).sort_values(["crop", "_r"])
               .drop(columns="_r").reset_index(drop=True))
    sheets = {"COC_factors_by_geography": tool, "COC by crop-country": agg_out,
              "COC by crop-region": reg_out, "COC aligned to tool rows": aligned}
    from openpyxl.styles import Font
    with pd.ExcelWriter(out_dir / "COC_factors_by_country.xlsx", engine="openpyxl") as xw:
        for sheet, df_ in sheets.items():
            df_.to_excel(xw, sheet_name=sheet, index=False)
            ws = xw.sheets[sheet]
            ws.freeze_panes = "C2"
            for j, h in enumerate(df_.columns, start=1):
                ws.cell(1, j).font = Font(bold=True)
                ws.column_dimensions[ws.cell(1, j).column_letter].width = (
                    26 if j <= 2 else (15 if h in ANNOTATION_COLS else 20))
    agg_out.to_csv(out_dir / "coc_by_crop_country.csv", index=False, encoding="utf-8")
    reg_out.to_csv(out_dir / "coc_by_crop_region.csv", index=False, encoding="utf-8")
    print(f"national: {agg_out['crop'].nunique()} crops x {agg_out['geography'].nunique()} countries "
          f"({len(agg_out):,} rows), {len(reg_out)} regional rows; {tot_nat / 1e9:.3f} GtCO2e/yr -> {out_dir}")
    return out_dir
