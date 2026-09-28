"""
The carbon opportunity cost (COC) calculation, cell by cell, for 46 crops.

The model, per crop and per grid cell:

    dC   = (native plant + native soil) - (agricultural plant + agricultural soil)     [tC/ha]
    COCh = (44/12) x dC / A                                                             [tCO2e/ha/yr]
    COCt = COCh / yield                                                                 [tCO2e/t]

with A = 30 years. COCh x crop area gives the cell's total (tCO2e/yr), summed over crops for the map.

On drained agricultural organic (peat) soil the soil stock difference is REPLACED by the annual drainage
flux, while the plant term is kept. For a cell whose share of cropped area on drained peat is f:

    COCh = (1 - f) x (44/12) x dC / A   +   f x ((44/12) x (native plant - ag plant) / A + EF)

The flux EF is already annual and already CO2 equivalent (tCO2e/ha/yr), so it is neither divided by A
nor converted by 44/12. Dropping the soil pair on the peat share, rather than adding the flux on top, is
what prevents counting peat carbon twice: the measured soil layer already contains it.

f is the drained agricultural organic-soil area (GFW) as a share of the cell's CROP area, capped at 1,
not of its whole area. GFW's layer is already restricted to cropland and plantations, so dividing by cell
area would discount the same information twice (it costs 8.57 Mha of GFW's 22.04 against 15.68 here;
17.215 against 17.462 GtCO2e/yr).

Inputs, all from harmonized/ (see pipeline/):
  native plant   Erb et al. 2018 five-map mean                                       step 02
  native soil    Table A-9 run backwards on OpenLandMap, annual or perennial layer    step 07
  ag plant       Cornell biomass for its 29 crops; IPCC for rubber; the COC tool's
                 value (col F / Table A-8) for the rest, and wherever Cornell is nodata  steps 03-04
  ag soil        OpenLandMap 0-100 cm SOC stock, 2015-2020                           step 05
  crop area      MapSPAM 2020 V2r2 physical area, all technologies                    step 01
  yield          MapSPAM harvested-area-weighted yield (production / harvested area)   step 01
  peat           WRI/GFW drained agricultural organic soil + CO2/N2O factor           step 08

Writes results/: per_ha/, per_tonne/, total/ (one GeoTIFF per crop), total_coc_tco2_yr.tif, qc/ and run.json.
"""
from __future__ import annotations

import csv
import datetime as _dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from coc import paths
from coc.constants import (ANNUALIZATION_YEARS, CO2_PER_C, IPCC_RUBBER_AGB_TC_HA, PERENNIAL_CODES,
                           YIELD_KG_TO_T)
from coc.grid import TH, TW, cell_area_ha, rd, save

METHOD = "v7.3"      # the method version, as named in the development work and docs/method.md

# Which layer feeds which part of the model: written into results/run.json, so a result names its inputs.
INPUTS = {
    "native_plant": {"layer": "harmonized/native_plant_carbon_tc_ha.tif",
                     "source": "Erb et al. 2018, mean of Extended Data Fig. 4 maps A-E"},
    "native_soil": {"layer": "harmonized/native_soil_a9_reverse/native_soil_{annual,perennial}_tc_ha.tif",
                    "source": "COC tool Table A-9 run backwards on OpenLandMap 0-100 cm SOC, by Dinerstein 2017 biome"},
    "ag_plant": {"layer": "harmonized/ag_plant_cornell/<CROP>_ag_plant_tc_ha.tif, falling back to "
                          "harmonized/ag_plant_tool/<item>_ag_plant_tc_ha.tif",
                 "source": "Cao et al. 2026 (29 crops); IPCC 2019 Table 5.3 for rubber (40.1 tC/ha); "
                           "COC tool col F / Table A-8 otherwise"},
    "ag_soil": {"layer": "harmonized/soc_openlandmap_0-100cm_tc_ha.tif",
                "source": "OpenLandMap-soildb socd, mean, 2015-2020, 0-100 cm"},
    "crop_area_yield": {"layer": "harmonized/mapspam/<CROP>_{physical_area_ha,harvested_area_ha,yield_kg_ha}.tif",
                        "source": "MapSPAM 2020 V2r2, all production systems (_A layers)"},
    "organic_soils": {"layer": "harmonized/gfw_peat/gfw_peat_ag_{frac,ef_tco2e_ha_yr}.tif",
                      "source": "WRI/GFW AFOLU organic-soils model v1.0.1, 2016-2020, agricultural classes, "
                                "on-site CO2 + N2O"},
    "annualization_years": ANNUALIZATION_YEARS,
}


def load_concordance():
    "46 rows: spam_code, spam_name, the COC tool item keys, status (ok / ADDED)."
    return list(csv.DictReader(open(paths.CONCORDANCE, encoding="utf-8")))


# --------------------------------------------------------------------------------------------------
# crop area, yield and production (MapSPAM, all technologies)
# --------------------------------------------------------------------------------------------------
def crop_area(code):
    "Physical area [ha per cell]."
    return rd(paths.mapspam(code, "physical_area_ha"))


def yield_harv_prod(code):
    "Yield [t/ha], harvested area [ha] and production [t] per cell. Yield = production / harvested area."
    prod = np.zeros((TH, TW), "float64"); harv = np.zeros((TH, TW), "float64")
    Y = rd(paths.mapspam(code, "yield_kg_ha")) * YIELD_KG_TO_T
    H = rd(paths.mapspam(code, "harvested_area_ha"))
    prod += np.nan_to_num(Y) * np.nan_to_num(H); harv += np.nan_to_num(H)     # NaN = absent
    Y_out = np.where(harv > 0, prod / harv, np.nan).astype("float32")
    harvested = np.where(harv > 0, harv, np.nan).astype("float32")
    production = np.where(harv > 0, prod, np.nan).astype("float32")
    return Y_out, harvested, production


# --------------------------------------------------------------------------------------------------
# the four carbon pools: each returns fn(concordance_row) -> tC/ha array
# --------------------------------------------------------------------------------------------------
def cropland_mean(directory: Path, suffix: str):
    "Per-cell mean over every *{suffix}.tif in a folder: the stand-in for crops with no tool item."
    s = np.zeros((TH, TW), "float64"); n = np.zeros((TH, TW), "float64")
    for f in sorted(Path(directory).glob(f"*{suffix}.tif")):
        a = rd(f); m = np.isfinite(a); s[m] += a[m]; n[m] += 1
    out = np.full((TH, TW), np.nan, "float32"); nz = n > 0
    out[nz] = (s[nz] / n[nz]).astype("float32")
    return out


def native_plant_pool():
    arr = rd(paths.H_NATIVE_PLANT)
    return lambda row: arr


def native_soil_pool():
    "Table A-9 gives annual and permanent tree/bush crops different loss factors, so two layers."
    annual = rd(paths.H_NATIVE_SOIL / "native_soil_annual_tc_ha.tif")
    perennial = rd(paths.H_NATIVE_SOIL / "native_soil_perennial_tc_ha.tif")
    return lambda row: perennial if row["spam_code"] in PERENNIAL_CODES else annual


def ag_plant_pool():
    """Best available per crop and per cell.

    Cornell where it has a layer, falling back per CELL to the COC tool's value wherever Cornell is
    nodata; the IPCC value for rubber, which has neither (masked to the tool layer's footprint, so it
    changes a value, never the extent); the tool's value for every other crop. Crops with no tool item
    (the concordance marks them '__...') take the per-cell mean of all tool items.
    """
    suffix = "ag_plant_tc_ha"
    proxy = cropland_mean(paths.H_AG_PLANT_TOOL, suffix)
    constants = {"RUBB": IPCC_RUBBER_AGB_TC_HA}

    def tool_value(row):
        slug = row["ag_plant"]
        if slug.startswith("__"):
            return proxy
        return rd(paths.H_AG_PLANT_TOOL / f"{slug}_{suffix}.tif")

    def fn(row):
        code = row["spam_code"]
        fallback = tool_value(row)
        path = paths.H_AG_PLANT_CORNELL / f"{code}_{suffix}.tif"
        if path.exists():
            arr = rd(path)
            return np.where(np.isfinite(arr), arr, fallback)
        if code in constants:
            value = np.float32(constants[code])
            return np.where(np.isfinite(fallback), value, np.nan).astype("float32")
        return fallback
    return fn


def ag_soil_pool():
    arr = rd(paths.H_SOC)
    return lambda row: arr


def peat_blend(concordance):
    """(fn(coc_mineral, coc_plant_only) -> blended per-ha COC, f): the organic-soil carve-out.

    f is GFW's drained agricultural organic-soil area as a share of the cell's crop area, capped at 1.
    Cells with no crop area get f = 0. A cell whose soil layers are NaN stays NaN even where f > 0,
    because NaN propagates through both branches: the carve-out reprices cells, never adds coverage.
    """
    frac = rd(paths.H_GFW_PEAT / "gfw_peat_ag_frac.tif")
    frac = np.where(np.isfinite(frac), frac, 0.0).astype("float32")
    if not (0.0 <= float(frac.min()) and float(frac.max()) <= 1.0):
        raise ValueError(f"peat fraction outside [0,1]: min {frac.min()} max {frac.max()}")
    ef = rd(paths.H_GFW_PEAT / "gfw_peat_ag_ef_tco2e_ha_yr.tif")
    ef = np.where(np.isfinite(ef), ef, 0.0).astype("float32")
    if float(ef.min()) < 0.0:
        raise ValueError(f"negative emission factor: min {ef.min()}")

    tot = np.zeros((TH, TW), "float64")
    for row in concordance:
        tot += np.nan_to_num(crop_area(row["spam_code"]))
    gfw_ha = frac.astype("float64") * cell_area_ha()
    frac = np.where(tot > 0, np.minimum(1.0, gfw_ha / np.maximum(tot, 1e-9)), 0.0).astype("float32")

    def fn(coc_mineral, coc_plant_only):
        return np.where(frac > 0,
                        (1.0 - frac) * coc_mineral + frac * (coc_plant_only + ef),
                        coc_mineral).astype("float32")
    return fn, frac


# --------------------------------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------------------------------
def run(out=None, verbose=True):
    out = Path(out or paths.RESULTS)
    A = ANNUALIZATION_YEARS
    FACTOR = CO2_PER_C / A                                   # tC -> tCO2e, spread over A years
    for sub in ("per_ha", "total", "per_tonne", "qc"):
        (out / sub).mkdir(parents=True, exist_ok=True)

    conc = load_concordance()
    np_fn, ns_fn, ap_fn, as_fn = native_plant_pool(), native_soil_pool(), ag_plant_pool(), ag_soil_pool()
    peat_fn, peat_frac = peat_blend(conc)

    total = np.zeros((TH, TW), "float64")
    valid = np.zeros((TH, TW), bool)
    glob_coc = glob_prod = 0.0
    rows = []
    for r in conc:
        sc = r["spam_code"]
        area = crop_area(sc)
        Y, _harv, prod = yield_harv_prod(sc)

        npl, nso, apl, aso = np_fn(r), ns_fn(r), ap_fn(r), as_fn(r)      # tC/ha
        dC = npl + nso - (apl + aso)                                     # tC/ha
        coc_h = FACTOR * dC                                              # tCO2e/ha/yr
        coc_h = peat_fn(coc_h, FACTOR * (npl - apl))                     # organic-soil carve-out
        coc_total = coc_h * area                                         # tCO2e/yr in the cell
        coc_t = np.where((Y > 0) & np.isfinite(coc_h), coc_h / Y, np.nan).astype("float32")

        save(coc_h, out / "per_ha" / f"{sc}_coc_perha_tco2_yr.tif")
        save(coc_total, out / "total" / f"{sc}_coc_total_tco2_yr.tif")
        save(coc_t, out / "per_tonne" / f"{sc}_coc_per_tonne_tco2_t.tif")

        m = np.isfinite(coc_total); valid |= m
        total += np.where(m, coc_total, 0.0)

        # global per-tonne is production-weighted: sum COC and production over the SAME cells
        m2 = np.isfinite(coc_t) & np.isfinite(area) & np.isfinite(prod)
        num = float(np.nansum(np.where(m2, coc_h * area, 0.0)))
        den = float(np.nansum(np.where(m2, prod, 0.0)))
        glob_coc += num; glob_prod += den

        a_ok = np.isfinite(area)
        area_ha = float(np.nansum(area))
        area_costed_ha = float(np.nansum(np.where(np.isfinite(dC), area, 0.0)))
        peat_area_costed_ha = float(np.nansum(np.where(np.isfinite(dC), area * peat_frac, 0.0)))
        rows.append({"spam_code": sc, "spam_name": r["spam_name"], "status": r["status"],
                     "mean_stock_dC_tc_ha": float(np.nanmean(dC[a_ok])) if a_ok.any() else np.nan,
                     "mean_coc_tco2_ha_yr": float(np.nanmean(coc_h[a_ok])) if a_ok.any() else np.nan,
                     "mean_yield_t_ha": float(np.nanmean(Y[a_ok])) if a_ok.any() else np.nan,
                     "coc_per_tonne_tco2_t": (num / den) if den > 0 else np.nan,
                     "total_coc_MtCO2_yr": float(np.nansum(coc_total) / 1e6),
                     "total_production_Mt_yr": den / 1e6,
                     "n_valid_cells": int(m.sum()),
                     "area_ha": area_ha,
                     "area_costed_ha": area_costed_ha,
                     "pct_area_costed": (100 * area_costed_ha / area_ha) if area_ha > 0 else np.nan,
                     "peat_area_costed_ha": peat_area_costed_ha})

    total[~valid] = np.nan                       # cells no crop reached are unknown, not zero
    save(total, out / "total_coc_tco2_yr.tif")
    T_gt = float(np.nansum(total) / 1e9)
    per_tonne = glob_coc / glob_prod if glob_prod else float("nan")
    tot_area = sum(r["area_ha"] for r in rows)
    tot_costed = sum(r["area_costed_ha"] for r in rows)
    tot_peat = sum(r["peat_area_costed_ha"] for r in rows)
    summary = {"release": paths.RELEASE, "method": METHOD, "annualization_years": A,
               "total_coc_GtCO2_yr": round(T_gt, 4),
               "valid_cells": int(valid.sum()),
               "pct_grid": round(100 * valid.sum() / (TW * TH), 3),
               "global_coc_per_tonne_tco2_t": round(per_tonne, 4),
               "total_production_Gt_yr": round(glob_prod / 1e9, 4),
               "total_area_Mha": round(tot_area / 1e6, 3),
               "costed_area_Mha": round(tot_costed / 1e6, 3),
               "pct_area_costed": round(100 * tot_costed / tot_area, 3) if tot_area else np.nan,
               "peat_area_costed_Mha": round(tot_peat / 1e6, 3)}
    pd.DataFrame(rows).sort_values("coc_per_tonne_tco2_t", ascending=False) \
        .to_csv(out / "qc" / "coc_per_crop_summary.csv", index=False)
    pd.DataFrame([summary]).to_csv(out / "qc" / "coc_coverage.csv", index=False)
    (out / "run.json").write_text(json.dumps(
        {"created": _dt.datetime.now().isoformat(timespec="seconds"), "data_root": str(paths.DATA_ROOT),
         "inputs": INPUTS, "results": summary}, indent=2), encoding="utf-8")
    if verbose:
        print(f"total {T_gt:.3f} GtCO2e/yr | {summary['valid_cells']:,} cells | "
              f"{per_tonne:.3f} tCO2e/t | {tot_peat / 1e6:.2f} Mha costed as drained peat -> {out}")
    return summary
