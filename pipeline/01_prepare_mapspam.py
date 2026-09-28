"""
01 — MapSPAM 2020 V2r2 crop area and yield -> harmonized/mapspam/

Reads the public MapSPAM 2020 V2r2 GeoTIFF zips (Harvard Dataverse) straight from raw/, without
unzipping them, and writes three layers per crop for the 46 crops in reference/coc_crop_concordance.csv:

    <CROP>_physical_area_ha.tif     land occupied by the crop (ha per cell)       variable A
    <CROP>_harvested_area_ha.tif    area harvested, counting multiple harvests    variable H
    <CROP>_yield_kg_ha.tif          production / harvested area (kg/ha)           variable Y

All three are MapSPAM's all-technology layer (`_A`): irrigated, rainfed high-input, rainfed low-input
AND subsistence. Subsistence is in scope on purpose: the results are meant to cover all cropland.

Values are copied unchanged. Only the nodata marker changes (MapSPAM's float32 minimum becomes NaN)
and the files are compressed. Why `_A` rather than summing the four technologies, which is what the
development pipeline did with MapSPAM's internal release: in the published data the two differ by
0.0005% of global area (a known inconsistency inside MapSPAM), and the public release ships only `_A`.
"""
import csv
import sys
import zipfile
from pathlib import Path

import numpy as np
from rasterio.io import MemoryFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coc import paths  # noqa: E402
from coc.grid import TH, TT, TW, save  # noqa: E402

VARIABLES = {  # zip stem, variable letter, output suffix
    "physical_area": ("A", "physical_area_ha"),
    "harvested_area": ("H", "harvested_area_ha"),
    "yield": ("Y", "yield_kg_ha"),
}


def read_member(zf, name):
    "Band 1 of a GeoTIFF inside a zip as float32, nodata -> NaN, asserting the grid."
    with MemoryFile(zf.read(name)) as mem, mem.open() as d:
        assert (d.width, d.height) == (TW, TH), f"size mismatch {name}"
        assert max(abs(a - b) for a, b in zip(tuple(d.transform)[:6], tuple(TT)[:6])) < 1e-6, \
            f"transform mismatch {name}"
        return d.read(1, masked=True).astype("float32").filled(np.nan)


def main():
    crops = [r["spam_code"] for r in csv.DictReader(open(paths.CONCORDANCE, encoding="utf-8"))]
    for stem, (letter, suffix) in VARIABLES.items():
        zpath = paths.MAPSPAM_ZIPS / f"spam2020V2r2_global_{stem}.geotiff.zip"
        if not zpath.exists():
            sys.exit(f"{zpath} not found — download it from the MapSPAM 2020 V2r2 Dataverse (see README)")
        with zipfile.ZipFile(zpath) as zf:
            members = {Path(n).name: n for n in zf.namelist() if n.endswith(".tif")}
            missing = [c for c in crops if f"spam2020_V2r2_global_{letter}_{c}_A.tif" not in members]
            if missing:
                sys.exit(f"{zpath.name} has no `_A` layer for {missing}")
            total = 0.0
            for crop in crops:
                arr = read_member(zf, members[f"spam2020_V2r2_global_{letter}_{crop}_A.tif"])
                save(arr, paths.mapspam(crop, suffix))
                total += float(np.nansum(arr)) if letter != "Y" else 0.0
        print(f"{stem:>15}: {len(crops)} crops -> {paths.H_MAPSPAM}"
              + (f"  (global total {total / 1e6:,.1f} M ha)" if letter != "Y" else ""))


if __name__ == "__main__":
    main()
