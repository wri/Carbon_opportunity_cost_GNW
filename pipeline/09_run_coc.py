"""
09 — The carbon opportunity cost calculation -> results/

Reads only harmonized/ (steps 01-08, or the published harmonized layers) and writes, per crop:
    results/per_ha/<CROP>_coc_perha_tco2_yr.tif         tCO2e per ha of the crop per year
    results/per_tonne/<CROP>_coc_per_tonne_tco2_t.tif   tCO2e per tonne of product
    results/total/<CROP>_coc_total_tco2_yr.tif          tCO2e per year in the cell
plus results/total_coc_tco2_yr.tif (all crops), results/qc/ and results/run.json. See coc/engine.py for
the model. ~5 min.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coc import engine  # noqa: E402

if __name__ == "__main__":
    engine.run()
