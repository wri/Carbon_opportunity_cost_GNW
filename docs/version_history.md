# Version history

Version 7.3 (this release) is the last of sixteen versions built during development in 2026. Each changed one
input from its parent where possible, so the difference between two adjacent versions can be attributed to
that input; the principles that emerged are in [method.md](method.md). Only version 7.3 is published. The
development code and data are not part of this repository.

All versions use A = 30 years. *Scope* is the MapSPAM production systems included: IHL = irrigated, rainfed
high-input and rainfed low-input; IHLS adds subsistence (all systems). Totals are from the development runs,
which used MapSPAM's internal release.

| Version | Change | Scope | GtCO2e/yr | tCO2e/t |
|---|---|---|---:|---:|
| v0 | Baseline: native soil from COC tool Table A-7; the other pools from the tool's factors | IHL | 14.14 | 1.66 |
| v1 | Native soil from the tool's own Raw-sheet values (col E): all four pools as in the tool, except gridded native plant carbon | IHL | 14.35 | 1.69 |
| v2 | v1 + agricultural soil from OpenLandMap | IHL | 16.46 | 1.94 |
| v3 | v1 + agricultural plant carbon from Cao et al. (IPCC for rubber) | IHL | 14.26 | 1.68 |
| v4 | v1 + native soil from the LPJmL model | IHL | 13.57 | 1.64 |
| v5 | v2 + v3 + v4 at once | IHL | 15.63 | 1.90 |
| v1.2 – v5.2 | v1 – v5 with subsistence in scope | IHLS | 16.60 – 20.21 | 1.84 – 2.18 |
| v5.3 | v5.2 with oil palm, rubber and coconut area moved onto observed plantation maps (SDPT, Descals et al.), keeping each first-level administrative unit's total | IHLS | 19.35 | 2.14 |
| v5.4 | v5.2 with organic soils carved out and priced with one flat IPCC factor on PEATMAP extent | IHLS | 20.14 | 2.23 |
| v6.2 | v5.2 with both soil pools from one model run (Sanderman et al. 2017) | IHLS | 15.65 | 1.69 |
| v7.2 | v5.2 with native soil from Table A-9 run backwards on OpenLandMap | IHLS | 16.90 | 1.82 |
| **v7.3** | **v7.2 with organic soils carved out and priced from the WRI/GFW model** | **IHLS** | **17.46** | **1.88** |

## Why version 7.3

- **Soil pairing (v2, v5, v6.2, v7.2).** Differencing a native-soil product against an independently calibrated
  agricultural-soil product (v2, v5) mostly measured their level offset: the soil term went negative over about
  a fifth of cropland and gave drained peat a carbon credit. One model differenced against itself (v6.2) fixed
  the sign but left almost no soil term. Running Table A-9 backwards on the measured stock (v7.2) is
  self-consistent and keeps a soil term of realistic size, at the cost of native soil no longer being observed.
- **Scope (the `.2` versions).** Cao et al.'s biomass covers all production, so its density needs all-system
  area; subsistence therefore came into scope.
- **Organic soils (v5.4, v7.3).** A peat map with one flat factor fixed the sign but charged crops for forestry
  and settlement drainage, used a tropical factor worldwide, and covered CO2 only. The WRI/GFW model supplies
  drained, land-use-filtered extent and stratified CO2 + N2O factors.
- **Crop area (v5.3).** Moving three plantation crops onto observed maps changed the total by +0.08 percent,
  but the coconut map is a closed-canopy detector that under-detects open-canopy groves, so it was not carried
  forward.

## v1.0.0 and the development build

The development runs summed MapSPAM's four production-system layers from its internal release. The public
release ships the all-system layer (`_A`) instead, which is pixel-identical between the two releases but
differs from the sum of the system layers by 0.0005 percent of global area (an inconsistency inside MapSPAM).
v1.0.0 reads the public `_A` layers, so anyone can reproduce it. Against the development build of version 7.3
it moves the global total by −0.0006 percent (17.4620 → 17.4619 GtCO2e/yr), no crop by more than 0.06 percent,
and no country with more than 1 MtCO2e/yr by more than 0.13 percent. Per-hectare values are identical except on
drained agricultural peat, where the peat share is taken relative to crop area.
