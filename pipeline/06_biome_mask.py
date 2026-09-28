"""
06 — Native ecosystem of each cell: Dinerstein et al. (2017) ecoregions -> harmonized/biome/

    biome/dinerstein_biome_num.tif    the 14 biomes (BIOME_NUM)
    biome/a9_native_class.tif         collapsed to the six native-ecosystem rows of COC tool Table A-9
    biome/qc.csv                      cropland area in each class, and in each judgement call below

Why this source: the code behind the COC tool (Wirsenius et al. 2025, create_regions_raster.R, Zenodo
10.5281/zenodo.15305575) builds its biome raster from exactly this shapefile and field, on this grid.
Table A-9 is keyed to the NATIVE ecosystem, so a potential-vegetation map is the right kind of layer; a
land-cover map would just say "cropland".

The 14 -> 6 collapse is ours (the authors' happens inside an Excel model that is not released):

    A-9 row                                     Dinerstein BIOME_NUM
    1 Tropical forest                           1, 2, 3   (+14 mangroves *)
    2 Temperate forest                          4, 5      (+6 boreal *)
    3 Tropical/temperate shrubland & grassland   7, 8      (+9 flooded grassland *)
    4 Montane and other grassland               10        (+11 tundra *)
    5 Mediterranean forest and shrub (dryland)  12
    6 Desert                                    13

  * judgement calls. A-9 has no boreal row (boreal -> temperate forest is the consequential one: Russia,
    Canada, the Nordics); flooded grassland is a grassland; tundra fits only "montane AND OTHER
    grassland"; mangrove is tropical forested wetland. Together they carry ~2.4% of cropland.

Cells whose centre falls in no ecoregion (small islands, coasts) are filled by a second all_touched pass.
"""
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from rasterio.features import rasterize

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coc import paths  # noqa: E402
from coc.engine import load_concordance  # noqa: E402
from coc.grid import TH, TT, TW, rd, save  # noqa: E402

BIOME_NAMES = {
    1: "Tropical & Subtropical Moist Broadleaf Forests", 2: "Tropical & Subtropical Dry Broadleaf Forests",
    3: "Tropical & Subtropical Coniferous Forests", 4: "Temperate Broadleaf & Mixed Forests",
    5: "Temperate Conifer Forests", 6: "Boreal Forests/Taiga",
    7: "Tropical & Subtropical Grasslands, Savannas & Shrublands",
    8: "Temperate Grasslands, Savannas & Shrublands", 9: "Flooded Grasslands & Savannas",
    10: "Montane Grasslands & Shrublands", 11: "Tundra", 12: "Mediterranean Forests, Woodlands & Scrub",
    13: "Deserts & Xeric Shrublands", 14: "Mangroves",
}
A9_CLASSES = {1: "Tropical forest", 2: "Temperate forest", 3: "Tropical and temperate shrubland and grassland",
              4: "Montane and other grassland", 5: "Mediterranean forest and shrub (dryland)", 6: "Desert"}
BIOME_TO_A9 = {1: 1, 2: 1, 3: 1, 14: 1, 4: 2, 5: 2, 6: 2, 7: 3, 8: 3, 9: 3, 10: 4, 11: 4, 12: 5, 13: 6}
AMBIGUOUS = {6: "boreal -> temperate forest (no boreal row in A-9)",
             9: "flooded grassland -> shrubland/grassland",
             11: "tundra -> montane AND OTHER grassland",
             14: "mangrove -> tropical forest (no row in A-9)"}


def main():
    if not paths.DINERSTEIN_SHP.exists():
        sys.exit(f"{paths.DINERSTEIN_SHP} not found — see README for Ecoregions2017")
    g = gpd.read_file(paths.DINERSTEIN_SHP, columns=["BIOME_NUM"])
    g = g[g.geometry.notna() & ~g.geometry.is_empty]
    g["BIOME_NUM"] = pd.to_numeric(g["BIOME_NUM"], errors="coerce")
    g = g[g["BIOME_NUM"].between(1, 14)]
    shapes = [(geom, int(b)) for geom, b in zip(g.geometry, g["BIOME_NUM"])]
    biome = rasterize(shapes, out_shape=(TH, TW), transform=TT, fill=0, dtype="int16", all_touched=False)
    touched = rasterize(shapes, out_shape=(TH, TW), transform=TT, fill=0, dtype="int16", all_touched=True)
    gap = (biome == 0) & (touched > 0)
    biome[gap] = touched[gap]
    a9 = np.zeros_like(biome)
    for b, c in BIOME_TO_A9.items():
        a9[biome == b] = c
    save(biome, paths.H_BIOME / "dinerstein_biome_num.tif", dtype="int16", nodata=0)
    save(a9, paths.H_BIOME / "a9_native_class.tif", dtype="int16", nodata=0)

    # QC: how much cropland each class and each judgement call carries
    crop = np.zeros((TH, TW), "float64")
    for r in load_concordance():
        crop += np.nan_to_num(rd(paths.mapspam(r["spam_code"], "physical_area_ha")))
    total = crop.sum()
    rows = [{"level": "dinerstein_biome", "code": b, "name": BIOME_NAMES[b], "a9_class": A9_CLASSES[BIOME_TO_A9[b]],
             "cropland_Mha": round(float(crop[biome == b].sum()) / 1e6, 3),
             "pct_of_cropland": round(100 * float(crop[biome == b].sum()) / total, 3),
             "ambiguous": AMBIGUOUS.get(b, "")} for b in sorted(BIOME_NAMES)]
    rows += [{"level": "a9_class", "code": c, "name": A9_CLASSES[c], "a9_class": A9_CLASSES[c],
              "cropland_Mha": round(float(crop[a9 == c].sum()) / 1e6, 3),
              "pct_of_cropland": round(100 * float(crop[a9 == c].sum()) / total, 3), "ambiguous": ""}
             for c in sorted(A9_CLASSES)]
    rows.append({"level": "a9_class", "code": 0, "name": "UNCLASSIFIED (no ecoregion)", "a9_class": "",
                 "cropland_Mha": round(float(crop[a9 == 0].sum()) / 1e6, 3),
                 "pct_of_cropland": round(100 * float(crop[a9 == 0].sum()) / total, 3), "ambiguous": ""})
    pd.DataFrame(rows).to_csv(paths.H_BIOME / "qc.csv", index=False, encoding="utf-8")
    amb = sum(r["pct_of_cropland"] for r in rows if r["ambiguous"])
    print(f"biome mask: {int((biome > 0).sum()):,} cells; judgement calls carry {amb:.2f}% of cropland "
          f"-> {paths.H_BIOME}")


if __name__ == "__main__":
    main()
