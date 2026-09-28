"""
Every file location the pipeline uses, derived from one data root (config.toml, config.local.toml or
COC_DATA_ROOT, last wins).

Three tiers, matching the S3 release:
  raw/         source datasets as downloaded. Only the pipeline/0x steps read these.
  harmonized/  every input on the MapSPAM grid. The calculation (coc.engine) reads nothing else.
  results/     what the calculation writes.
Small reference tables that are part of the method, not data, live in the repo under reference/.
"""
import os
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONFIG = tomllib.loads((REPO / "config.toml").read_text(encoding="utf-8"))
if (REPO / "config.local.toml").exists():          # untracked, per-machine overrides
    CONFIG.update(tomllib.loads((REPO / "config.local.toml").read_text(encoding="utf-8")))
RELEASE = CONFIG["release"]
DATA_ROOT = Path(os.environ.get("COC_DATA_ROOT") or (REPO / CONFIG["data_root"])).resolve()

RAW = DATA_ROOT / "raw"
HARMONIZED = DATA_ROOT / "harmonized"
RESULTS = DATA_ROOT / "results"

# --- reference tables (tracked in git) ---
REFERENCE = REPO / "reference"
CONCORDANCE = REFERENCE / "coc_crop_concordance.csv"            # SPAM crop -> COC tool item
GFW_LOOKUP = REFERENCE / "gfw_combined_state_lookup.csv"        # GFW organic-soil class -> land use, EF
TOOL_FACTORS = REFERENCE / "coc_tool_factors_by_geography.csv"  # the COC tool's own factors, tidy

# --- raw inputs ---
MAPSPAM_ZIPS = RAW / "mapspam_2020v2r2"          # the public Dataverse GeoTIFF zips
ERB_DIR = RAW / "erb2018"                         # ExtDat_Fig4{A..E}_gcm.tif
CORNELL_RESIDUE = RAW / "cornell_biomass" / "Crop_Residue_Total_DM_Mg"
CORNELL_YIELD = RAW / "cornell_biomass" / "Crop_Yield_Total_DM_Mg"
GADM_ADM0 = RAW / "gadm41" / "gadm_410_admin0.shp"
DINERSTEIN_SHP = RAW / "dinerstein2017" / "Ecoregions2017.shp"
COC_TOOL_XLSX = RAW / "coc_tool" / "coc_calc_tool_v1_factors.xlsx"

# --- harmonized inputs (one folder or file per pipeline step) ---
H_MAPSPAM = HARMONIZED / "mapspam"                              # 01
H_NATIVE_PLANT = HARMONIZED / "native_plant_carbon_tc_ha.tif"   # 02
H_GEOGRAPHY = HARMONIZED / "geography"                          # 03
H_AG_PLANT_TOOL = HARMONIZED / "ag_plant_tool"                  # 03
H_AG_PLANT_CORNELL = HARMONIZED / "ag_plant_cornell"            # 04
H_SOC = HARMONIZED / "soc_openlandmap_0-100cm_tc_ha.tif"        # 05
H_BIOME = HARMONIZED / "biome"                                  # 06
H_NATIVE_SOIL = HARMONIZED / "native_soil_a9_reverse"           # 07
H_GFW_PEAT = HARMONIZED / "gfw_peat"                            # 08


def mapspam(crop, variable):
    "A harmonized MapSPAM layer: variable is physical_area_ha, harvested_area_ha or yield_kg_ha."
    return H_MAPSPAM / f"{crop}_{variable}.tif"
