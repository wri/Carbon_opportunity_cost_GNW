"""
04 — Agricultural plant carbon from Cornell crop biomass -> harmonized/ag_plant_cornell/

    tC/ha = (residue DM + yield DM) [t per cell] / physical area [ha per cell] x 0.47 x 0.5

Cornell (Cao et al., Nat. Clim. Change 2026, doi:10.1038/s41558-026-02558-4) supplies gridded crop
residue and harvested-yield dry matter (above + below ground) for 29 of the 46 MapSPAM crops, in t per
cell. Their sum is the crop's annual dry-matter production in the cell.
  0.47  IPCC default carbon fraction of dry matter.
  0.5   annual production approximates the PEAK standing stock; half of it is the time-averaged stock,
        the same basis (Lmean) as the tree-crop values.
Physical area of ALL technologies is the denominator, so the result is carbon per hectare of land (as
Erb's native layer is), and because Cornell's biomass covers all production, subsistence included.

Limitations to keep in mind:
  * A calibrated proxy, not a measured stock: it scales with cropping intensity, so where a cell is
    harvested more than twice a year it exceeds what the land can hold at one time (~20% of rice dry
    matter; capping it would move the global rice mean by 1.7%, so no cap is applied).
  * Cornell's crop footprint is a MapSPAM-family layer but not identical to MapSPAM 2020 V2r2. Cells with
    biomass but no MapSPAM area, or with an implied density above 100 t DM/ha/yr (a near-zero area
    against real biomass, e.g. 7 m2 of maize against 33,086 t), are written as nodata. The calculation
    falls back to the tool's value there, so coverage is never lost.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coc import paths  # noqa: E402
from coc.constants import CARBON_FRACTION_DM, MAX_DM_DENSITY_T_HA, TIME_AVERAGE  # noqa: E402
from coc.grid import TH, TT, TW, save  # noqa: E402

RESIDUE_NAME = "Crop_Residue_Total_DM_Mg_{crop}.tif"
YIELD_NAME = "Crop_Yield_Total_DM_Mg_{crop}.tif"


def read(path):
    "Band 1 as float64 with nodata and non-finite mapped to 0.0 (Cornell stores 0 for 'no crop')."
    with rasterio.open(path) as d:
        if (d.width, d.height) != (TW, TH):
            raise RuntimeError(f"grid mismatch {path}")
        if max(abs(a - b) for a, b in zip(tuple(d.transform)[:6], tuple(TT)[:6])) > 1e-6:
            raise RuntimeError(f"transform mismatch {path}")
        arr = d.read(1).astype("float64")
        nodata = d.nodata
    if nodata is not None:
        arr = np.where(arr == nodata, 0.0, arr)
    return np.where(np.isfinite(arr), arr, 0.0)


def list_crops():
    res = {p.name.rsplit("_", 1)[1][:-4] for p in paths.CORNELL_RESIDUE.glob("*.tif")}
    yld = {p.name.rsplit("_", 1)[1][:-4] for p in paths.CORNELL_YIELD.glob("*.tif")}
    if not res:
        sys.exit(f"no Cornell layers in {paths.CORNELL_RESIDUE} — see README")
    if res != yld:
        raise RuntimeError(f"Residue/yield crop sets differ: {sorted(res ^ yld)}")
    missing = sorted(c for c in res if not paths.mapspam(c, "physical_area_ha").exists())
    if missing:
        raise FileNotFoundError(f"No MapSPAM physical area for {missing} — run step 01 first")
    return sorted(res)


def main():
    crops = list_crops()
    out_dir = paths.H_AG_PLANT_CORNELL
    tags = {"units": "tC/ha", "pool": "agricultural plant carbon, above + below ground",
            "basis": "time-averaged standing stock (peak x 0.5)", "carbon_fraction": str(CARBON_FRACTION_DM),
            "caveat": "calibrated proxy, not a measured stock; scales with cropping intensity"}
    rows = []
    for crop in crops:
        dm = read(paths.CORNELL_RESIDUE / RESIDUE_NAME.format(crop=crop)) + \
             read(paths.CORNELL_YIELD / YIELD_NAME.format(crop=crop))
        area = read(paths.mapspam(crop, "physical_area_ha"))
        has_area = area > 0.0
        density = np.zeros_like(dm)
        np.divide(dm, area, out=density, where=has_area)
        convertible = has_area & (density <= MAX_DM_DENSITY_T_HA)
        out = np.full(dm.shape, np.nan, dtype="float64")
        out[convertible] = density[convertible] * CARBON_FRACTION_DM * TIME_AVERAGE
        save(out, out_dir / f"{crop}_ag_plant_tc_ha.tif", tags=tags)

        orphan = ((dm > 0.0) & ~has_area) | (has_area & (density > MAX_DM_DENSITY_T_HA))
        w = area[convertible]
        rows.append({"crop": crop, "total_dm_Mt": dm.sum() / 1e6, "physical_area_Mha": area.sum() / 1e6,
                     "area_weighted_mean_tC_ha": float((out[convertible] * w).sum() / w.sum()) if w.sum() else np.nan,
                     "cells_written": int(np.isfinite(out).sum()), "orphan_cells": int(orphan.sum()),
                     "orphan_dm_pct": 100.0 * dm[orphan].sum() / dm.sum() if dm.sum() else 0.0})
    pd.DataFrame(rows).to_csv(out_dir / "manifest.csv", index=False, encoding="utf-8")
    print(f"Cornell ag plant: {len(crops)} crops -> {out_dir}")


if __name__ == "__main__":
    main()
