"""
The MapSPAM 5 arc-minute grid every layer sits on, and the read/write helpers that enforce it.

The transform is MapSPAM 2020 V2r2's own, copied to the last bit: its pixel size is 0.0833333333333144,
not exactly 1/12, and its top edge is 90.00000000000004. Every harmonized layer carries it, and cell
areas computed from it feed the peat fraction, so rounding it to 1/12 would change results in the last
digits. rd() tolerates ~1e-6 of float wobble in a file's transform, and anything more is an error.
"""
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio.crs import CRS

TW, TH = 4320, 2160
TT = Affine(0.0833333333333144, 0.0, -180.0, 0.0, -0.0833333333333144, 90.00000000000004)
CRS_4326 = CRS.from_epsg(4326)
PROFILE = {"driver": "GTiff", "width": TW, "height": TH, "count": 1, "crs": CRS_4326, "transform": TT,
           "tiled": True, "blockxsize": 128, "blockysize": 128, "interleave": "band"}


def rd(path):
    "Band 1 as float32, nodata -> NaN, asserting the grid."
    with rasterio.open(path) as d:
        assert (d.width, d.height) == (TW, TH), f"size mismatch {path}"
        assert max(abs(a - b) for a, b in zip(tuple(d.transform)[:6], tuple(TT)[:6])) < 1e-6, \
            f"transform mismatch {path}"
        return d.read(1, masked=True).astype("float32").filled(np.nan)


def save(arr, path, dtype="float32", nodata=float("nan"), tags=None):
    "Write one band on the grid, deflate-compressed. Float layers use NaN as nodata."
    p = {**PROFILE, "dtype": dtype, "nodata": nodata, "compress": "deflate"}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **p) as dst:
        dst.write(arr.astype(dtype), 1)
        if tags:
            dst.update_tags(**tags)


def cell_area_ha():
    "Area of each grid cell in hectares, on the authalic sphere (R = 6371007.181 m)."
    R = 6371007.181
    lat1 = np.deg2rad(TT.f + np.arange(TH) * TT.e)          # north edge of each row
    lat2 = np.deg2rad(TT.f + (np.arange(TH) + 1) * TT.e)    # south edge
    return ((R ** 2 * np.deg2rad(TT.a) * (np.sin(lat1) - np.sin(lat2)) / 1e4)[:, None]
            * np.ones((1, TW))).astype("float64")
