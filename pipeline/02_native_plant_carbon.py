"""
02 — Native plant carbon: Erb et al. (2018) five-map mean -> harmonized/native_plant_carbon_tc_ha.tif

Erb et al. (2018, Nature 553:73) publish five global maps of potential vegetation carbon, i.e. what
the land would hold without human use (Extended Data Fig. 4, maps A-E, gC/m2, above + below ground).
Their per-cell mean, converted to tC/ha (/100), is the native plant carbon of every crop's cell.

The maps are already on the MapSPAM 5 arc-min grid (cell-coincident to ~1e-13 deg), so the
nearest-neighbour step onto the grid is an exact re-registration, not a resample.
"""
import sys
from pathlib import Path

import numpy as np
import rioxarray as rxr
import xarray as xr
from rasterio.enums import Resampling

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coc import paths  # noqa: E402
from coc.grid import save  # noqa: E402

ERB_MAPS = ["A", "B", "C", "D", "E"]


def main():
    maps = {}
    for k in ERB_MAPS:
        p = paths.ERB_DIR / f"ExtDat_Fig4{k}_gcm.tif"
        if not p.exists():
            sys.exit(f"{p} not found — see README for the Erb et al. (2018) download")
        maps[k] = (rxr.open_rasterio(p, masked=True).squeeze("band", drop=True) / 100.0).astype("float32")

    # Map E's coordinates differ from A's by a float epsilon; snap every map onto A's before stacking,
    # or xr.concat outer-joins them into a misaligned ~2x grid.
    ref = maps["A"]
    aligned = [da.assign_coords(x=ref.x.values, y=ref.y.values) for da in maps.values()]
    mean = xr.concat(aligned, dim="map").mean("map", skipna=True)
    mean.rio.write_crs(ref.rio.crs, inplace=True)

    # Register onto the MapSPAM grid, using a harmonized MapSPAM layer (step 01) as the template.
    template_path = sorted(paths.H_MAPSPAM.glob("*_physical_area_ha.tif"))[0]
    template = rxr.open_rasterio(template_path, masked=True).squeeze("band", drop=True)
    on_grid = mean.rio.reproject_match(template, resampling=Resampling.nearest)

    arr = on_grid.values.astype("float32")
    save(arr, paths.H_NATIVE_PLANT, tags={"units": "tC/ha", "source": "Erb et al. 2018, mean of maps A-E"})
    print(f"native plant carbon: mean {np.nanmean(arr):.2f} tC/ha over {int(np.isfinite(arr).sum()):,} cells "
          f"-> {paths.H_NATIVE_PLANT}")


if __name__ == "__main__":
    main()
