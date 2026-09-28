"""
07 — Native soil carbon by running COC tool Table A-9 backwards -> harmonized/native_soil_a9_reverse/

Table A-9 gives the FRACTION f of native soil carbon lost when native land becomes cropland, by native
ecosystem (step 06) x annual vs permanent tree/bush crop. The tool applies it forwards. Here it is
applied backwards to the MEASURED present-day stock (step 05):

    current = native x (1 - f)    ->    native = current / (1 - f)
    soil carbon lost = native - current = current x f / (1 - f)

    native_soil_annual_tc_ha.tif / native_soil_perennial_tc_ha.tif    (+ qc.csv)

What this buys: both sides of the soil subtraction come from one measured product, so there is no
level offset between two soil datasets (which made most pairings of independent products meaningless
in the development work). What it costs: native soil stops being an observation. It is present-day
soil carbon times a biome constant, so the soil term carries an assumption about proportional loss, not
independent evidence about the native state. Report it as such.

Two decisions made in development and kept: f is applied to the full 0-100 cm stock (Beillouin et al.
2023, the source of the positive factors, is mostly topsoil, so this likely overstates the loss), and
organic (peat) soils are left in here, because step 08 and the engine remove them from the stock
difference altogether on the drained agricultural fraction.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coc import paths  # noqa: E402
from coc.constants import A9_CLASS_NAMES, A9_LOSS_ANNUAL, A9_LOSS_PERENNIAL  # noqa: E402
from coc.engine import load_concordance  # noqa: E402
from coc.grid import TH, TW, rd, save  # noqa: E402


def main():
    biome_path = paths.H_BIOME / "a9_native_class.tif"
    for p, step in ((paths.H_SOC, "05"), (biome_path, "06")):
        if not p.exists():
            sys.exit(f"{p} not found — run step {step} first")
    ag = rd(paths.H_SOC)
    with rasterio.open(biome_path) as d:
        a9 = d.read(1)
    crop = np.zeros((TH, TW), "float64")
    for r in load_concordance():
        crop += np.nan_to_num(rd(paths.mapspam(r["spam_code"], "physical_area_ha")))

    rows = []
    for tag, F in (("annual", A9_LOSS_ANNUAL), ("perennial", A9_LOSS_PERENNIAL)):
        # cells outside every ecoregion stay NaN: no biome, no defensible factor (0.01% of cropland)
        native = np.full((TH, TW), np.nan, "float32")
        for c, f in F.items():
            m = (a9 == c) & np.isfinite(ag)
            native[m] = ag[m] / (1.0 - f)
        save(native, paths.H_NATIVE_SOIL / f"native_soil_{tag}_tc_ha.tif", tags={"units": "tC/ha"})
        dC = native - ag
        for c, f in F.items():
            m = (a9 == c) & np.isfinite(ag) & (crop > 0)
            w = crop[m]
            if w.sum() == 0:
                continue
            rows.append({"crop_type": tag, "a9_class": c, "name": A9_CLASS_NAMES[c], "f": f,
                         "multiplier_on_ag_soil": round(f / (1 - f), 4),
                         "cropland_Mha": round(float(w.sum()) / 1e6, 3),
                         "mean_ag_soil_tc_ha": round(float(np.average(ag[m], weights=w)), 2),
                         "mean_native_tc_ha": round(float(np.average(native[m], weights=w)), 2),
                         "mean_soil_dC_tc_ha": round(float(np.average(dC[m], weights=w)), 2)})
        ok = np.isfinite(native) & (crop > 0)
        print(f"  {tag:9s} cropland-weighted native {np.average(native[ok], weights=crop[ok]):6.2f} tC/ha, "
              f"soil loss {np.average(dC[ok], weights=crop[ok]):6.2f} tC/ha")
    pd.DataFrame(rows).to_csv(paths.H_NATIVE_SOIL / "qc.csv", index=False, encoding="utf-8")
    print(f"native soil (A-9 reversed) -> {paths.H_NATIVE_SOIL}")


if __name__ == "__main__":
    main()
