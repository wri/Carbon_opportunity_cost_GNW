# Carbon opportunity cost of crop production — spatially explicit

Global, gridded **carbon opportunity cost (COC)** of 46 crops: the carbon that land would hold in its native
state but loses under agriculture, annualized over 30 years. Computed cell by cell on the MapSPAM
5 arc-minute grid (~9 km at the equator), rather than from the regional averages of the Excel COC tool.

> **Release status:** v1.0.0 in preparation. The data release (S3) and the full method documentation are
> not published yet; the sections marked *(pending)* below will be filled in before release.

## What it produces

For each crop, three rasters (GeoTIFF, EPSG:4326, 4320 x 2160, NaN = no value):

| file | unit | meaning |
|---|---|---|
| `per_ha/<CROP>_coc_perha_tco2_yr.tif` | tCO2e / ha / yr | cost of one hectare of the crop in that cell |
| `per_tonne/<CROP>_coc_per_tonne_tco2_t.tif` | tCO2e / t | cost per tonne of product |
| `total/<CROP>_coc_total_tco2_yr.tif` | tCO2e / yr | cost of all of the crop's area in the cell |

plus `total_coc_tco2_yr.tif` (all crops), `national/COC_factors_by_country.xlsx` (crop x country and crop x
region, in the COC tool's own table format, beside the tool's factors), and QC tables. Headline for v1.0.0:
**17.46 GtCO2e/yr** over 1,274 Mha of cropland, **1.88 tCO2e per tonne** of crop production.

## The model

Per crop and grid cell, with A = 30 years:

    dC   = (native plant + native soil) - (agricultural plant + agricultural soil)     [tC/ha]
    COCh = (44/12) x dC / A                                                             [tCO2e/ha/yr]
    COCt = COCh / yield                                                                 [tCO2e/t]

On drained agricultural organic (peat) soil the soil stock difference is replaced by the annual drainage
emission (on-site CO2 + N2O), keeping the plant term; see [coc/engine.py](coc/engine.py).

| pool | source |
|---|---|
| native plant carbon | Erb et al. (2018), mean of five potential-vegetation maps |
| native soil carbon | COC tool Table A-9 loss factors run backwards on the measured soil stock, by native biome (Dinerstein et al. 2017) and annual vs perennial crop |
| agricultural plant carbon | Cao et al. (2026) crop biomass for 29 crops; IPCC (2019) for rubber; COC tool (Table A-8) for the rest |
| agricultural soil carbon | OpenLandMap-soildb, 0-100 cm, 2015-2020 (Hengl et al. 2026) |
| crop area, yield | MapSPAM 2020 V2r2, all production systems (IFPRI) |
| drained organic soils | WRI/GFW AFOLU organic-soils flux model v1.0.1, 2016-2020 |

## Three ways to use it

1. **Use the results.** Download `results/` from the data release *(pending)*. No code needed.
2. **Re-run or change the calculation.** Download `harmonized/` (~160 MB: every input already on the grid)
   and run steps 09-10 (~5 min). Change a pool by replacing its layer or editing [coc/engine.py](coc/engine.py).
3. **Rebuild everything from the source datasets.** Put the sources in `raw/` (below) and run all ten
   steps (~70 min, nearly all of it step 08; steps 05 and 08 stream from the internet).

## Quickstart

Python 3.11. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Data goes in `data/` inside the repository by default (`data/raw/`, `data/harmonized/`, `data/results/`).
To keep it elsewhere, set `COC_DATA_ROOT` or put `data_root = "..."` in an untracked `config.local.toml`
(see [config.toml](config.toml)). Then:

```bash
python run_pipeline.py --from 09     # from harmonized/ (level 2)
python run_pipeline.py               # from raw/ (level 3)
python verify.py                     # does my run reproduce v1.0.0? (pixel by pixel)
```

`verify.py` compares every layer and table against [reference/v1.0.0_manifest.csv](reference/v1.0.0_manifest.csv).
With the pinned requirements v1.0.0 reproduces bit for bit. If a re-run of step 05 or 08 differs, the
streamed source has most likely changed since the release.

## Repository layout

```
coc/                 the package
  engine.py            the calculation (step 09)
  national.py          aggregation to crop x country / region (step 10)
  geography.py         the COC tool's regions and countries on the grid
  grid.py              the MapSPAM grid, read/write helpers
  constants.py         every numeric assumption, with its source
  paths.py             every file location, from config.toml
pipeline/            one script per step, run in order by run_pipeline.py
  01_prepare_mapspam.py            MapSPAM area + yield
  02_native_plant_carbon.py        Erb et al.
  03_geography_and_tool_factors.py GADM countries, COC tool regions, tool ag-plant values
  04_cornell_ag_plant.py           Cao et al. biomass -> ag plant carbon
  05_openlandmap_soc.py            OpenLandMap SOC 0-100 cm (streamed)
  06_biome_mask.py                 Dinerstein ecoregions -> Table A-9 classes
  07_a9_reverse_native_soil.py     native soil carbon
  08_gfw_peat_flux.py              drained agricultural peat + emission factor (streamed)
  09_run_coc.py                    the calculation
  10_national_factors.py           national and regional tables
reference/           small tables that are part of the method (crop concordance, GFW class lookup,
                     the COC tool's factors), and the v1.0.0 manifest verify.py checks against
verify.py            checks a run against the release
```

## Data layout and sources

```
<data_root>/
  raw/            source datasets as downloaded       (level 3 only)
  harmonized/     every input on the grid              (what steps 09-10 read)
  results/        outputs
```

| `raw/` folder | dataset | where to get it | step |
|---|---|---|---|
| `mapspam_2020v2r2/` | MapSPAM 2020 V2r2 GeoTIFFs: `spam2020V2r2_global_{physical_area,harvested_area,yield}.geotiff.zip` | IFPRI, Harvard Dataverse, https://doi.org/10.7910/DVN/SWPENT | 01 |
| `erb2018/` | `ExtDat_Fig4{A..E}_gcm.tif` | Erb et al. 2018, Nature 553:73, https://doi.org/10.1038/nature25138 (Extended Data Fig. 4) | 02 |
| `gadm41/` | `gadm_410_admin0.shp` (GADM 4.1, level 0) | https://gadm.org (not redistributable; download it yourself) | 03 |
| `coc_tool/` | `coc_calc_tool_v1_factors.xlsx` | WRI COC tool *(pending)* | 03 |
| `cornell_biomass/` | `Crop_{Residue,Yield}_Total_DM_Mg/` | Cao et al. 2026, Nat. Clim. Change, https://doi.org/10.1038/s41558-026-02558-4 *(access pending)* | 04 |
| — | OpenLandMap-soildb `socd` (streamed) | Hengl et al. 2026, ESSD 18:989, https://doi.org/10.5194/essd-18-989-2026 | 05 |
| `dinerstein2017/` | `Ecoregions2017.shp` | Dinerstein et al. 2017, BioScience 67:534, https://doi.org/10.1093/biosci/bix014 | 06 |
| — | GFW organic-soils model, `combined_state` tiles (streamed) | `s3://gfw2-data/climate/AFOLU_flux_model/organic_soils/` (public) | 08 |

Steps 05 and 08 read their sources live, so a re-run gets whatever is published at the time. The GFW data
has been corrected in place before without changing its path. The published `harmonized/` layers are the
exact ones v1.0.0 used.

## Limitations

*(pending: docs/limitations.md.)* The most important: native soil is inferred from present-day soil carbon
and a biome loss factor, not observed; the organic-soil term is a lower bound (no CH4, off-site carbon or
fire); MapSPAM places crops by modelled suitability within statistical units; results cover only cells where
every input exists (99.2% of the crop area).

## License and citation

Code: [MIT](LICENSE). Data: the license of the published layers, and the citation, are *(pending)*; each
source dataset keeps its own terms (see the table above).
