# Carbon opportunity cost of crop production — data release v1.0.0

Global, gridded carbon opportunity cost (COC) of 46 crops on the MapSPAM 2020 5 arc-minute grid: the carbon
the land would hold in its native state but loses under agriculture, annualized over 30 years. Method
version 7.3. Code, method and documentation: https://github.com/wri/Carbon_opportunity_cost_GNW

Headline: 17.46 GtCO2e/yr over 1,274 Mha of cropland; 1.88 tCO2e per tonne of crop production.

## Layout

| Folder | Size | What it is |
|---|---:|---|
| `results/` | ~400 MB | Per crop: COC per hectare, per tonne and total (GeoTIFF); all-crop total; QC tables; crop × country and crop × region tables in the COC tool's format |
| `harmonized/` | ~160 MB | Every input on the grid: what the calculation reads (`run_pipeline.py --from 09`) |
| `raw/` | ~0.8 GB | The source datasets that may be redistributed, as used; GADM is not included (download it from https://gadm.org) |
| `MANIFEST.csv` | | Every file with its size and SHA-256 |

GeoTIFFs: EPSG:4326, 4,320 × 2,160, float32, NaN = no value. File-by-file descriptions:
[docs/outputs.md](https://github.com/wri/Carbon_opportunity_cost_GNW/blob/main/docs/outputs.md).

## Getting it

With the repository: `python fetch_data.py results` (or `harmonized`, `raw`), which checks every file against
`MANIFEST.csv`; then `python verify.py` checks a run against the release pixel by pixel.

## License

The results and harmonized layers are released under **CC BY 4.0**
(https://creativecommons.org/licenses/by/4.0/). Each source dataset keeps its own terms and must be cited:
see [docs/data_sources.md](https://github.com/wri/Carbon_opportunity_cost_GNW/blob/main/docs/data_sources.md).

This data was provided by the International Food Policy Research Institute (IFPRI). IFPRI bears no
responsibility for the analyses or interpretations of the data presented here.

## Limitations

Read [docs/limitations.md](https://github.com/wri/Carbon_opportunity_cost_GNW/blob/main/docs/limitations.md)
before use. In short: native soil carbon is inferred, not observed; the organic-soil cost is a lower bound;
subsistence production is in scope; results exist only where every input exists (99.2% of crop area).
