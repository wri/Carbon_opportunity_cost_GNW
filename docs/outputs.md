# Outputs

What the calculation writes to `results/` (and publishes in the data release), and how to read it. The model
behind the numbers is in [method.md](method.md).

## Grid and format

Every raster is a single-band GeoTIFF on the MapSPAM 2020 grid:

| | |
|---|---|
| CRS | EPSG:4326 (WGS 84, geographic) |
| Size | 4,320 columns × 2,160 rows |
| Cell | 5 arc-minutes (about 9 km at the equator); exact size 0.0833333333333144° |
| Origin | top-left −180°, 90.00000000000004° (MapSPAM's own transform, kept to the last bit) |
| Data type | float32; `geo_key` uint8, `country_key` int32, biome layers int16 |
| No data | NaN for float layers (0 for the integer keys) |
| Compression | deflate, 128 × 128 tiles |

Cell areas vary with latitude, so never average cell values over an area: weight by physical area or
production as described below.

## `results/`

| Path | Unit | What it is |
|---|---|---|
| `per_ha/<CROP>_coc_perha_tco2_yr.tif` | tCO2e / ha / yr | COC of one hectare of the crop in the cell (Equation 1, or 6 on drained peat). Defined wherever the inputs overlap, **whether or not the crop is grown there**, so outside the crop's footprint it is a counterfactual: what a hectare *would* cost |
| `per_tonne/<CROP>_coc_per_tonne_tco2_t.tif` | tCO2e / t | COC per tonne of product (Equation 2); only where the crop has a positive yield |
| `total/<CROP>_coc_total_tco2_yr.tif` | tCO2e / yr | COC of all of the crop's physical area in the cell (Equation 3); only where the crop is grown |
| `total_coc_tco2_yr.tif` | tCO2e / yr | Sum of `total/` over the 46 crops. Cells no crop reaches are NaN, not 0 |
| `qc/coc_per_crop_summary.csv` | | One row per crop: see below |
| `qc/coc_coverage.csv` | | The global headline figures |
| `national/COC_factors_by_country.xlsx` | | Crop × country and crop × region tables beside the COC tool's factors: see below |
| `national/coc_by_crop_country.csv`, `coc_by_crop_region.csv` | | The workbook's two result sheets as CSV |
| `run.json` | | When the run was made, which layer fed which part of the model, and the headline results |

`<CROP>` is the MapSPAM crop code (table at the end).

### `qc/coc_per_crop_summary.csv`

| Column | Meaning |
|---|---|
| `spam_code`, `spam_name` | MapSPAM crop |
| `status` | How the crop maps onto a COC tool item ([reference/coc_crop_concordance.csv](../reference/coc_crop_concordance.csv), with a note per crop): `ok` a direct match; `JUDGMENT` a considered but imperfect match (CITR, ONIO, RICE, TEMF, TOMA, TROF, VEGE); `WEAK` a proxy item (OPUL, ORTS); `ADDED` no direct counterpart, mapped by a project decision (OFIB, REST, RUBB, TOBA). See [limitations.md](limitations.md) |
| `mean_stock_dC_tc_ha`, `mean_coc_tco2_ha_yr`, `mean_yield_t_ha` | Unweighted means over the cells where the crop is grown. Descriptive only; use the weighted figures |
| `coc_per_tonne_tco2_t` | Production-weighted: total COC ÷ total production, over cells where both are defined |
| `total_coc_MtCO2_yr`, `total_production_Mt_yr` | Global totals |
| `n_valid_cells` | Cells with a total COC |
| `area_ha`, `area_costed_ha`, `pct_area_costed` | Physical area, and the part of it where every input exists and a cost is computed |
| `peat_area_costed_ha` | Costed area on drained agricultural organic soil (the organic-soil carve-out) |

### `national/COC_factors_by_country.xlsx`

Four sheets, all with the COC tool's own ten columns:

| Sheet | Rows |
|---|---|
| `COC_factors_by_geography` | The COC tool's own factors (Global, 10 regions, 4 override countries), for comparison |
| `COC by crop-country` | Ours: one row per tool crop item × country (43 × 164 = 4,315 rows), plus `global_production_share` |
| `COC by crop-region` | Ours: Global + the 10 Table A-1 regions |
| `COC aligned to tool rows` | Ours, on exactly the rows and in the order of the first sheet, so the two can be compared cell by cell |

| Column | Meaning |
|---|---|
| `crop` | COC tool item name. MapSPAM crops that map to the same item are combined: Coffee = arabica + robusta, Millet = small + pearl, Seed Cotton = cotton + other fibre. REST, RUBB and TOBA have no tool item and keep their MapSPAM name |
| `geography` | Country (country sheet), or Global / region |
| `native_plant_tC_ha`, `native_soil_tC_ha`, `ag_plant_tC_ha`, `ag_soil_tC_ha` | The four carbon stocks, physical-area-weighted, tC/ha |
| `coc_per_ha_tC_ha` | The carbon-stock difference in **tC/ha, not annualized and not CO2** (the tool's convention). On drained peat it is the stock-*equivalent* of the flux-based cost, so there the four stock columns no longer add up to it |
| `yield_t_per_ha_yr` | Total production ÷ total harvested area |
| `land_use_ha_per_t_yr` | 1 ÷ yield |
| `coc_per_tonne_tCO2e` | Total annual COC ÷ total production, tCO2e/t, A = 30 years |
| `global_production_share` | (country sheet only) the country's share of the crop's global production; sums to 1 per crop |

Regions contain their override country (Brazil is part of South America, and so on), as in the tool.

## `harmonized/` (the inputs, also published)

| Path | Unit | Built by |
|---|---|---|
| `mapspam/<CROP>_physical_area_ha.tif` | ha per cell | step 01 |
| `mapspam/<CROP>_harvested_area_ha.tif` | ha per cell | step 01 |
| `mapspam/<CROP>_yield_kg_ha.tif` | kg / ha | step 01 |
| `native_plant_carbon_tc_ha.tif` | tC / ha | step 02 |
| `geography/geo_key.tif`, `country_key.tif`, `country_key.csv`, `qc/` | codes | step 03 |
| `ag_plant_tool/<item>_ag_plant_tc_ha.tif`, `qc/` | tC / ha | step 03 |
| `ag_plant_cornell/<CROP>_ag_plant_tc_ha.tif`, `manifest.csv` | tC / ha | step 04 |
| `soc_openlandmap_0-100cm_tc_ha.tif` | tC / ha | step 05 |
| `biome/dinerstein_biome_num.tif`, `a9_native_class.tif`, `qc.csv` | codes | step 06 |
| `native_soil_a9_reverse/native_soil_{annual,perennial}_tc_ha.tif`, `qc.csv` | tC / ha | step 07 |
| `gfw_peat/gfw_peat_ag_frac.tif` | fraction of the cell | step 08 |
| `gfw_peat/gfw_peat_ag_ef_tco2e_ha_yr.tif`, `qc.json` | tCO2e per drained ha per yr | step 08 |

`geo_key` codes: 1 CAS Central Asia, 2 EAS East Asia, 3 EUR Europe, 4 MEA Middle East & N. Africa, 5 NAM North
America, 6 OCE Oceania, 7 RUS Russia, 8 SAM South America, 9 SAS South Asia, 10 SSA Sub-Saharan Africa;
11 Brazil, 12 China, 13 India, 14 United States; 0 outside every listed country. `country_key.csv` decodes
`country_key.tif`.

## The 46 crops

Totals and per-tonne factors are v1.0.0 results. *Ag plant* is the source of agricultural plant carbon (see
[method.md](method.md)); *A-9 column* is the Table A-9 column used for native soil.

| Code | MapSPAM crop | COC tool item | A-9 column | Ag plant | Total COC (MtCO2e/yr) | tCO2e/t |
|---|---|---|---|---|---:|---:|
| `BANA` | Banana | Banana | perennial | Cao et al. | 92.4 | 0.78 |
| `BARL` | Barley | Barley | annual | Cao et al. | 505.5 | 3.30 |
| `BEAN` | Bean | Common beans | annual | Cao et al. | 413.4 | 15.47 |
| `CASS` | Cassava | Cassava | annual | Cao et al. | 429.7 | 1.43 |
| `CHIC` | Chickpea | Chickpeas | annual | Cao et al. | 131.0 | 8.73 |
| `CITR` | Citrus | Orange | perennial | COC tool | 148.2 | 0.95 |
| `CNUT` | Coconut | Coconut | perennial | COC tool | 231.7 | 3.88 |
| `COCO` | Cocoa | Cocoa | perennial | COC tool | 180.6 | 32.47 |
| `COFF` | Arabica Coffee | Coffee | perennial | COC tool | 117.7 | 19.86 |
| `COTT` | Cotton | Seed Cotton | annual | Cao et al. | 276.7 | 3.63 |
| `COWP` | Cowpea | Cow peas | annual | Cao et al. | 117.3 | 13.28 |
| `GROU` | Groundnut | Peanut (pods) | annual | Cao et al. | 341.5 | 6.59 |
| `LENT` | Lentil | Lentils | annual | Cao et al. | 49.5 | 8.37 |
| `MAIZ` | Maize | Maize | annual | Cao et al. | 2,425.4 | 2.08 |
| `MILL` | Small Millet | Millet | annual | Cao et al. | 54.2 | 6.68 |
| `OCER` | Other Cereals | Other cereals | annual | Cao et al. | 344.2 | 5.21 |
| `OFIB` | Other Fibre | Seed Cotton | annual | Cao et al. | 55.7 | 12.59 |
| `OILP` | Oil palm | Oil palm | perennial | COC tool | 989.8 | 2.40 |
| `ONIO` | Onion | Onion | annual | COC tool | 62.1 | 0.58 |
| `OOIL` | Other Oil Crops | Other oil/prot field crops | annual | Cao et al. | 166.6 | 5.43 |
| `OPUL` | Other Pulses | Peas | annual | Cao et al. | 173.7 | 6.72 |
| `ORTS` | Other Roots | Other below-ground vegetables | annual | Cao et al. | 36.5 | 1.81 |
| `PIGE` | Pigeon Pea | Pigeon peas | annual | Cao et al. | 67.6 | 13.66 |
| `PLNT` | Plantain | Plantain | perennial | COC tool | 92.6 | 2.07 |
| `PMIL` | Pearl Millet | Millet | annual | Cao et al. | 144.6 | 6.76 |
| `POTA` | Potato | White potato | annual | Cao et al. | 253.5 | 0.69 |
| `RAPE` | Rapeseed | Rapeseed | annual | Cao et al. | 451.0 | 6.26 |
| `RCOF` | Robusta Coffee | Coffee | perennial | COC tool | 95.2 | 22.03 |
| `REST` | Rest of Crops | — | annual | mean of all tool items | 299.1 | 8.36 |
| `RICE` | Rice | Rice (unprocessed) | annual | Cao et al. | 2,076.6 | 2.73 |
| `RUBB` | Rubber | — | perennial | IPCC 2019 | 309.0 | 22.14 |
| `SESA` | Sesame | Sesame | annual | Cao et al. | 136.3 | 20.76 |
| `SORG` | Sorghum | Sorghum | annual | Cao et al. | 304.5 | 5.18 |
| `SOYB` | Soybean | Soybean | annual | Cao et al. | 1,630.9 | 4.61 |
| `SUGB` | Sugarbeet | Sugarbeet | annual | Cao et al. | 62.1 | 0.23 |
| `SUGC` | Sugarcane | Sugarcane | annual | Cao et al. | 440.4 | 0.24 |
| `SUNF` | Sunflower | Sunflower | annual | Cao et al. | 267.5 | 4.89 |
| `SWPO` | Sweet Potato | Sweet potato | annual | Cao et al. | 112.9 | 1.30 |
| `TEAS` | Tea | Tea | perennial | COC tool | 95.1 | 3.51 |
| `TEMF` | Temperate Fruit | Other temperate fruits | perennial | COC tool | 274.9 | 0.95 |
| `TOBA` | Tobacco | — | annual | mean of all tool items | 51.3 | 8.52 |
| `TOMA` | Tomato | Tomato | annual | COC tool | 53.0 | 0.29 |
| `TROF` | Tropical Fruit | Other tropical fruits | perennial | COC tool | 261.0 | 0.96 |
| `VEGE` | Other Vegetables | Other above-ground vegetables | annual | COC tool | 667.0 | 0.80 |
| `WHEA` | Wheat | Wheat | annual | Cao et al. | 1,860.4 | 2.45 |
| `YAMS` | Yams | Yams | annual | COC tool | 111.9 | 1.49 |

For the 29 crops marked *Cao et al.*, the COC tool's value is still used in any cell where Cao et al. have no
value (see [limitations.md](limitations.md)).
