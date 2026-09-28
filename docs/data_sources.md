# Data sources

Every dataset the pipeline reads, what it is used for, how it is processed, and the terms it comes under.
The published release (results and harmonized layers) is licensed **CC BY 4.0**; each source keeps its own
terms, listed here, and must be cited when the release is used.

| Dataset | Version / period | Native resolution | Used for | Step | Terms |
|---|---|---|---|---|---|
| MapSPAM 2020 (IFPRI) | V2r2 (Dataverse V5), 2020, `_A` layers | 5 arc-min | Crop physical area, harvested area, yield; the grid | 01 | CC BY 4.0 under IFPRI's terms of use (see below) |
| Erb et al. (2018) | Extended Data Fig. 4, maps A–E | 5 arc-min | Native plant carbon | 02 | Published with the article; cite Erb et al. (2018) |
| GADM | 4.1, level 0 | vector | Countries, the COC tool's regions | 03 | Free for non-commercial use; **not redistributable**, so not mirrored in the release |
| COC tool workbook | `coc_calc_tool_v1_factors.xlsx` | tabular | Table A-1 regions, Raw sheet col F (= Table A-8) ag plant carbon | 03 | WRI |
| Cao et al. (2026) crop biomass | residue + yield dry matter, 29 crops, circa 2020 | 5 arc-min | Agricultural plant carbon | 04 | Shared by the authors (Cornell University); cite Cao et al. (2026) |
| OpenLandMap-soildb (Hengl et al. 2026) | `socd`, mean, 2015–2020, 0–30/30–60/60–100 cm | 120 m (16× overview read) | Agricultural soil carbon, and the base of native soil carbon | 05 | CC BY 4.0 |
| Dinerstein et al. (2017) Ecoregions2017 | 2017 | vector | Native biome for Table A-9 | 06 | CC BY 4.0 |
| COC tool Table A-9 | soil carbon loss factors | tabular | Native soil carbon (run backwards) | 07 | WRI; values in [coc/constants.py](../coc/constants.py) |
| WRI/GFW AFOLU organic-soils flux model | v1.0.1, run `ogh_mixed_f1_f15_f2_20260513`, 2016–2020 | 0.00025° (~30 m) | Drained agricultural organic soil and its CO2 + N2O emission factor | 08 | WRI; Global Forest Watch data are generally CC BY 4.0 (terms for this model to be confirmed) |
| IPCC (2019) Refinement, Vol. 4 Ch. 5 Table 5.3 | rubber Lmean | constant | Rubber agricultural plant carbon, 40.1 tC/ha | 09 | cite IPCC (2019) |

Full references are at the end of [method.md](method.md).

## Notes per source

**MapSPAM 2020 V2r2.** Downloaded from Harvard Dataverse (https://doi.org/10.7910/DVN/SWPENT) as three zips,
`spam2020V2r2_global_{physical_area,harvested_area,yield}.geotiff.zip`. Only the all-system `_A` layer of each
crop is read; values are copied unchanged, with MapSPAM's nodata marker replaced by NaN. IFPRI's terms of use
require that adaptations carry this statement, which applies to the release: *"This data was provided by the
International Food Policy Research Institute (IFPRI). IFPRI bears no responsibility for the analyses or
interpretations of the data presented here."*

**Erb et al. (2018).** Five potential-vegetation biomass maps in gC/m² (Extended Data Fig. 4, A–E); their mean
in tC/ha. The maps are already on the MapSPAM grid to within ~1e-13°.

**GADM 4.1.** Only the level-0 (country) polygons are read. GADM's license does not allow redistribution, so
the release does not include it: download `gadm_410_admin0.shp` from https://gadm.org to rebuild step 03. The
rasters derived from it (`harmonized/geography/`) are in the release, so steps 09–10 do not need it.

**COC tool workbook.** Read for three things: the Table A-1 country-to-region lists, the tool's crop items,
and column F of the "Raw LO and COC data" sheet (agricultural plant carbon per crop and geography). The
tool's cleaned factor table ([reference/coc_tool_factors_by_geography.csv](../reference/coc_tool_factors_by_geography.csv))
is included for comparison in the national tables.

**Cao et al. (2026).** Gridded crop residue and harvested-yield dry matter (t per cell), above and below
ground, for 29 of the 46 MapSPAM crops; the authors confirmed no further crops are available as grids. Their
underlying crop footprint is a MapSPAM-family layer, not identical to MapSPAM 2020 V2r2.

**OpenLandMap-soildb.** Streamed, not downloaded: step 05 reads the public cloud-optimized GeoTIFFs listed in
the OpenLandMap catalog (https://github.com/openlandmap/soildb). Soil organic carbon density is summed over
three depth layers into the 0–100 cm stock.

**Dinerstein et al. (2017).** `Ecoregions2017.shp`, field `BIOME_NUM`, the same source and grid the code
behind the COC tool uses.

**WRI/GFW organic-soils model.** Streamed from the public bucket `s3://gfw2-data`
(`climate/AFOLU_flux_model/organic_soils/outputs/version_1_0_1/`). Only the `combined_state` class tiles are
read; the per-class land use and emission factor come from
[reference/gfw_combined_state_lookup.csv](../reference/gfw_combined_state_lookup.csv), derived from the
model's own tables. The model's land-use labels for 2011–2020 were corrected in place on 26 August 2026;
v1.0.0 uses the corrected data. Its totals for the agricultural classes (22.004 Mha, 948.0 MtCO2e/yr) come
from the model's master zonal-statistics table.

## Reference tables in the repository

| File | What it is |
|---|---|
| [reference/coc_crop_concordance.csv](../reference/coc_crop_concordance.csv) | MapSPAM crop → COC tool item for agricultural plant carbon (`ag_plant`; `__cropland_mean__` = no tool item) and the Table A-7 row (`native_soil`, kept for reference, not used by v7.3), with a status and a note per crop |
| [reference/gfw_combined_state_lookup.csv](../reference/gfw_combined_state_lookup.csv) | GFW `combined_state` class → drainage class, climate, land use, whether it counts as agricultural, and its CO2 + N2O emission factor |
| [reference/coc_tool_factors_by_geography.csv](../reference/coc_tool_factors_by_geography.csv) | The COC tool's factors as one tidy table: 1,464 rows (153 crops × Global, 10 regions, 4 override countries), with `value_source` marking which values the tool copies from Global or a region |
| [reference/v1.0.0_manifest.csv](../reference/v1.0.0_manifest.csv) | Pixel hashes of every published layer, for [verify.py](../verify.py) |
