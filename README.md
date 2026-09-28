# Carbon opportunity cost of crop production — spatially explicit

Global, gridded **carbon opportunity cost (COC)** of 46 crops: the carbon that land would hold in its native
state but loses under agriculture, annualized over 30 years. Computed cell by cell on the MapSPAM
5 arc-minute grid (~9 km at the equator), rather than from the regional averages of WRI's COC calculation
tool. Release **v1.0.0** (method version 7.3).

Headline: **17.46 GtCO2e/yr** over 1,274 Mha of cropland, **1.88 tCO2e per tonne** of crop production.

| Document | |
|---|---|
| [docs/method.md](docs/method.md) | The method: equations, how each source was chosen, results, illustrative maps |
| [docs/limitations.md](docs/limitations.md) | What to keep in mind before using the numbers |
| [docs/outputs.md](docs/outputs.md) | Every output file and column, and the 46 crops |
| [docs/data_sources.md](docs/data_sources.md) | Every input dataset, how it is processed, and its terms |
| [docs/version_history.md](docs/version_history.md) | The sixteen development versions and why 7.3 |

## What it produces

For each crop, three rasters (GeoTIFF, EPSG:4326, 4,320 × 2,160, NaN = no value):

| File | Unit | Meaning |
|---|---|---|
| `per_ha/<CROP>_coc_perha_tco2_yr.tif` | tCO2e / ha / yr | cost of one hectare of the crop in that cell |
| `per_tonne/<CROP>_coc_per_tonne_tco2_t.tif` | tCO2e / t | cost per tonne of product |
| `total/<CROP>_coc_total_tco2_yr.tif` | tCO2e / yr | cost of all of the crop's area in the cell |

plus `total_coc_tco2_yr.tif` (all crops), `national/COC_factors_by_country.xlsx` (crop × country and crop ×
region, in the COC tool's own table format, beside the tool's factors) and QC tables.

## The model

Per crop and grid cell, with A = 30 years:

    dC   = (native plant + native soil) - (agricultural plant + agricultural soil)     [tC/ha]
    COCh = (44/12) x dC / A                                                             [tCO2e/ha/yr]
    COCt = COCh / yield                                                                 [tCO2e/t]

On drained agricultural organic (peat) soil the soil stock difference is replaced by the annual drainage
emission (on-site CO2 + N2O), keeping the plant term. See [docs/method.md](docs/method.md) and
[coc/engine.py](coc/engine.py).

| Pool | Source |
|---|---|
| native plant carbon | Erb et al. (2018), mean of five potential-vegetation maps |
| native soil carbon | COC tool Table A-9 loss factors run backwards on the measured soil stock, by native biome (Dinerstein et al. 2017) and annual vs perennial crop |
| agricultural plant carbon | Cao et al. (2026) crop biomass for 29 crops; IPCC (2019) for rubber; COC tool (Table A-8) for the rest |
| agricultural soil carbon | OpenLandMap-soildb, 0–100 cm, 2015–2020 (Hengl et al. 2026) |
| crop area, yield | MapSPAM 2020 V2r2, all production systems (IFPRI) |
| drained organic soils | WRI/GFW AFOLU organic-soils flux model v1.0.1, 2016–2020 |

## Data

The data release is at **`s3://wri-lcl-lea/Carbon_opportunity_cost/v1.0.0/`**
(`https://wri-lcl-lea.s3.amazonaws.com/Carbon_opportunity_cost/v1.0.0/`), with a `MANIFEST.csv` of every
file and its SHA-256 and a data card (`README.md`). Access currently needs AWS credentials for that bucket.

```
<data_root>/
  results/        outputs                                     ~400 MB
  harmonized/     every input on the grid (steps 09-10 read only this)   ~160 MB
  raw/            source datasets as used, except GADM          ~0.8 GB
```

## Three ways to use it

1. **Use the results.** `python fetch_data.py results`, or copy `results/` from the bucket. No calculation
   needed.
2. **Re-run or change the calculation.** `python fetch_data.py harmonized`, then
   `python run_pipeline.py --from 09` (~3 min). Change a pool by replacing its layer or editing
   [coc/engine.py](coc/engine.py); every numeric assumption is in [coc/constants.py](coc/constants.py).
3. **Rebuild everything from the source datasets.** `python fetch_data.py raw`, add GADM 4.1 level 0
   (`raw/gadm41/gadm_410_admin0.shp`, from https://gadm.org), and run all ten steps (~70 min, nearly all of it
   step 08; steps 05 and 08 stream from the internet).

## Quickstart

Python 3.11. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Data goes in `data/` inside the repository by default. To keep it elsewhere, set `COC_DATA_ROOT` or put
`data_root = "..."` in an untracked `config.local.toml` (see [config.toml](config.toml)). Then:

```bash
python fetch_data.py harmonized      # --profile NAME to pick AWS credentials
python run_pipeline.py --from 09     # the calculation + national tables
python verify.py                     # does my run reproduce v1.0.0? (pixel by pixel)
```

`verify.py` compares every layer and table against [reference/v1.0.0_manifest.csv](reference/v1.0.0_manifest.csv).
With the pinned requirements, v1.0.0 reproduces bit for bit, from `harmonized/` and from `raw/` alike. If a
re-run of step 05 or 08 differs, the streamed source has most likely changed since the release.

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
docs/                method, limitations, outputs, data sources, version history
fetch_data.py        downloads a tier of the data release, checking every file
verify.py            checks a run against the release
tools/publish_data.py  maintainers: uploads a data release
```

## License and citation

Code: [MIT](LICENSE). Data (results and harmonized layers): [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Each source dataset keeps its own terms and should be cited: see [docs/data_sources.md](docs/data_sources.md).
This data was provided by the International Food Policy Research Institute (IFPRI). IFPRI bears no
responsibility for the analyses or interpretations of the data presented here.

A citation for this release will be added.
