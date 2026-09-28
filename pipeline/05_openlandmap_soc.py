"""
05 — Present-day soil organic carbon, 0-100 cm: OpenLandMap -> harmonized/soc_openlandmap_0-100cm_tc_ha.tif

OpenLandMap soil organic carbon DENSITY (`socd`, kg/m3, mean prediction, epoch 2015-2020, 120 m) for the
three standard layers 0-30, 30-60 and 60-100 cm, summed into the carbon stock of the top metre:

    stock [t/ha] = sum over layers of  socd [kg/m3] x thickness [m] x 10

This is the agricultural soil carbon of every crop (measured, present-day), and through step 07 the
base the native soil carbon is inferred from.

Streamed, nothing downloaded: the COGs are public at s3.opengeohub.org and are read over HTTPS with
GDAL /vsicurl/. The 120 m -> 5 arc-min aggregation reads the 16x overview of each COG (never the full
array) and AVERAGE-resamples it onto the grid; a plain out_shape read would let GDAL pick the ~64x
overview, barely finer than the target, and lose coastal cells. The product spans about -56 to 76
degrees latitude; cells outside that band, and cells missing any of the three layers, are nodata.

Because the source is streamed, a re-run reads whatever OpenLandMap serves at the time. The v1.0.0
layer is published in harmonized/ so results never depend on that. Needs network access; ~1 min
(it reads only the 16x overviews, a few hundred MB).
"""
import io
import os
import ssl
import sys
import urllib.request
from pathlib import Path

import certifi
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject
from rasterio.windows import Window
from rasterio.windows import transform as window_transform

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coc import paths  # noqa: E402
from coc.grid import CRS_4326, TH, TT, TW, save  # noqa: E402

CATALOG_URL = "https://raw.githubusercontent.com/openlandmap/soildb/main/tables/OpenLandMap_soildb_COGS.csv"
PROPERTY, TYPE, YEAR, RES = "socd", "mean", "2015-2020", "120m"
DEPTHS = ["0..30cm", "30..60cm", "60..100cm"]
OV_LEVEL = 3                        # overviews are [2, 4, 8, 16, ...]; index 3 is the 16x one

# TLS through certifi (some Python builds do not use the system store), and GDAL tuned for remote COGs.
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("CURL_CA_BUNDLE", certifi.where())
os.environ.setdefault("GDAL_HTTP_CAINFO", certifi.where())
os.environ.update({"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif",
                   "GDAL_HTTP_MULTIRANGE": "YES", "GDAL_HTTP_VERSION": "2", "VSI_CACHE": "TRUE",
                   "VSI_CACHE_SIZE": "536870912", "GDAL_HTTP_MAX_RETRY": "3", "GDAL_HTTP_RETRY_DELAY": "1"})


def thickness_m(depth_label):
    top, bot = (float(x) for x in depth_label.replace("cm", "").split(".."))
    return (bot - top) / 100.0


def socd_to_t_ha(socd_kgm3, thickness):
    return socd_kgm3 * thickness * 10.0


def load_layers():
    "The three depth layers' catalog rows (S3 URL + DN scaler), strictly one row per depth."
    ctx = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(CATALOG_URL, context=ctx) as resp:
        cat = pd.read_csv(io.BytesIO(resp.read()))
    cat.columns = [c.strip() for c in cat.columns]
    s3col = next(c for c in cat.columns if c.lower().replace(" ", "").startswith("s3"))
    layers = {}
    for d in DEPTHS:
        m = cat[(cat["property"] == PROPERTY) & (cat["type"] == TYPE) & (cat["year_interval"] == YEAR)
                & (cat["Resolution"] == RES) & (cat["depth_interval"] == d)]
        if len(m) != 1:
            raise ValueError(f"expected exactly 1 catalog layer for {PROPERTY}/{TYPE}/{YEAR}/{RES}/{d}, got {len(m)}")
        layers[d] = (m.iloc[0][s3col], float(m.iloc[0]["scaler"]))
    return layers


def main():
    layers = load_layers()
    with rasterio.open(f"/vsicurl/{layers['0..30cm'][0]}") as s0:
        b, ovs = s0.bounds, s0.overviews(1)
    # the product covers a latitude band; its edges must fall on grid-cell edges
    assert all(abs(v * 12 - round(v * 12)) < 1e-6 for v in (b.left, b.top, b.bottom)), "socd off the grid"
    assert ovs[OV_LEVEL] == 16, f"overview index {OV_LEVEL} is {ovs[OV_LEVEL]}x, expected 16x"
    band_h = round((b.top - b.bottom) * 12)
    row0 = round((90 - b.top) * 12)
    band_t = window_transform(Window(0, row0, TW, band_h), TT)

    stock = None
    for d in DEPTHS:
        url, scaler = layers[d]
        with rasterio.open(f"/vsicurl/{url}", OVERVIEW_LEVEL=OV_LEVEL) as src:
            ov = src.read(1).astype("float32")
            ov_t, ov_crs = src.transform, src.crs
            nod = float(src.nodata) if src.nodata is not None else 32767.0
        dn_raw = np.full((band_h, TW), nod, "float32")
        reproject(ov, dn_raw, src_transform=ov_t, src_crs=ov_crs, dst_transform=band_t, dst_crs=CRS_4326,
                  src_nodata=nod, dst_nodata=nod, resampling=Resampling.average)
        dn = np.where(dn_raw == nod, np.nan, dn_raw * scaler)      # kg/m3; scaler applied once
        contrib = socd_to_t_ha(dn, thickness_m(d))
        stock = contrib if stock is None else stock + contrib      # NaN in any layer -> NaN total
        print(f"  {d:>10}: mean density {np.nanmean(dn):.2f} kg/m3")

    out = np.full((TH, TW), np.nan, "float32")
    out[row0:row0 + band_h, :] = stock
    save(out, paths.H_SOC, tags={"units": "tC/ha", "depth": "0-100 cm",
                                 "source": f"OpenLandMap {PROPERTY} {TYPE} {YEAR} {RES}, 16x overview averaged"})
    print(f"SOC stock 0-100 cm: {100 * np.isfinite(out).mean():.1f}% of cells, mean {np.nanmean(out):.1f} tC/ha "
          f"-> {paths.H_SOC}")


if __name__ == "__main__":
    main()
