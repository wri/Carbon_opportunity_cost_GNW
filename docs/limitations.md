# Limitations

The spatial method increases geographic detail, but it inherits the limitations of its input datasets, and
harmonizing them onto one grid adds constraints of its own. Read these before using the factors. The method
itself is in [method.md](method.md).

## Native soil carbon is an assumption, not an observation

The largest single caveat. The native stock is inferred as present-day soil carbon divided by (1 − *f*), so
the soil term carries no independent evidence about the native state, only Table A-9's assumption of
proportional loss. Two consequences follow:

- Table A-9's factors were calibrated against the COC tool's own native stocks (Table A-3, from LPJmL and
  Sanderman extractions), not against the OpenLandMap layer they are applied to here, whose cropland level
  is roughly half Sanderman's. The inferred native stock is correspondingly the lowest of the three
  constructions considered (about 81 tC/ha over cropland, against about 99 for LPJmL and 136 for Sanderman).
- The factor is applied to the full 0–100 cm stock, while the meta-analysis behind the positive factors
  (Beillouin et al. 2023) is predominantly a topsoil study and subsoil carbon changes far less than topsoil,
  so the absolute loss is likely overstated. Applying the factor to the topsoil only would need the 0–30 cm
  stock (OpenLandMap publishes it) and a one-line change in step 07.

## The agricultural soil layer is a cell mean, and peat inflates it

Carving the drained organic hectares out of the stock difference does not de-contaminate the average over
the rest of the cell, so the mineral part of a mixed cell is still costed against a soil value peat has
raised. The signal is measurable: averaged over cropped cells, soil carbon is about 66 tC/ha where the cell
holds no drained agricultural peat, 114 where it holds some, and 146 where more than half the cropped area
is peat. Exposure is about 236 MtCO2e/year, 1.4 percent of the global total, over the 53.6 Mha of mineral
cropland sharing a cell with drained agricultural peat; the true error is some fraction of that. Correcting
it needs the cell's *total* organic fraction, drained and undrained.

## The organic-soil cost is a lower bound

Off-site dissolved-organic-carbon CO2, methane and fire are published by the WRI/GFW model and all excluded;
off-site emissions alone would add roughly 1–3 tCO2e/ha/year on drained hectares. The model uses the IPCC
oil-palm emission factor, 40.9 tCO2e/ha/year, where the published COC tool documentation uses Conchedda and
Tubiello's 78.2, a factor of about 1.9 on the crop that dominates tropical peat. Drained organic soil under
grassland (about 4.7 Mha) is not costed, because the method has no pasture.

## Subsistence production is in scope

Including the subsistence system was needed to match the agricultural plant carbon denominator (see
[method.md](method.md)), but it puts low-yielding subsistence land, with disproportionately high per-tonne
factors, inside the reported factors. For corporate reporting the commercial-only scope may be more
appropriate. In the development runs, which used MapSPAM's internal release, leaving subsistence out lowered
the global total by about 3 GtCO2e/year. It cannot be reproduced from the public MapSPAM release, which does
not split rainfed production into high-input, low-input and subsistence.

## Some negative values remain

Negative COC covers 2.5 percent of costed cropland (−37 MtCO2e/year). It is almost entirely gone from drained
peat, where it did the most damage in earlier versions, but not from mineral soils; the middle of the United
States is the clearest case, where the inferred native stock is below the measured agricultural stock. Read
these as an artifact of the soil construction, not as a finding that cropping raised soil carbon.

## The agricultural plant pool has two soft spots

Cao et al.'s value is a calibrated proxy, not a measured stock: annual production divided by physical area
scales with cropping intensity, whereas a real stock saturates. Where more than two harvests share a hectare
the time-average exceeds what the land can hold at one time (about 20 percent of rice dry matter; capping the
intensity would move the global rice mean by 1.7 percent). Separately, the below-ground residue it includes
partly decomposes within the year into the soil carbon OpenLandMap measures. Both sides of the difference are
(plant including roots) + (soil), so this is not a simple double count, but any overlap inflates the
agricultural stock and biases COC downward by an unquantified amount. Cao et al.'s crop footprint is a
MapSPAM-family layer but not identical to MapSPAM 2020 V2r2; cells where the two disagree fall back to the
COC tool's value.

## The crop concordance is not one-to-one everywhere

Each MapSPAM crop is mapped to a COC tool item ([reference/coc_crop_concordance.csv](../reference/coc_crop_concordance.csv),
`status` and `note` columns). Where the tool's value is used for agricultural plant carbon, two mappings are
known to understate it: MapSPAM's temperate fruit includes apples and grapes, which the tool's "Other temperate
fruits" excludes (they carry 9.3 and 10.0 tC/ha against 6.8), and MapSPAM's tropical fruit includes mango,
which the tool's "Other tropical fruits" excludes (20.0 against 7.6). Blending them properly needs area shares
by fruit. Three crops have no tool item at all (REST, TOBA, RUBB): the first two take the mean of all tool
items, and rubber the IPCC value.

## Coverage

- **46 crops** only, each mapped to the corresponding COC tool crop item. Livestock, pasture, aquaculture and
  processed products are outside the spatial calculation.
- **Results exist only where every input exists.** The native plant layer has gaps over some small islands
  and OpenLandMap does not cover every cell in the crop footprint (it spans about 56°S to 76°N). Missing
  inputs stay missing rather than being filled, which is why 0.8 percent of the crop area in scope is not
  costed.
- **Countries**: the national tables cover the 157 countries of the tool's Table A-1 plus a curated
  supplement of 36, all sovereign states. Overseas territories (French Guiana, Réunion, ...) are left out by
  choice, and so are Aland and Northern Cyprus, which GADM separates from Finland and Cyprus (about
  0.06 Mha of cropland). The national tables recover 99.95 percent of the global total.

## Resolution

Harmonizing datasets of very different native resolutions onto one 5 arc-minute grid limits what can be
resolved. OpenLandMap is produced at 30 m, but crop distributions are known only at 5 arc-minutes, so every
crop in a cell gets the same soil carbon. The same holds for the organic-soil fraction. MapSPAM itself places
crops within statistical units by modelled suitability, so a single cell's crop mix is an allocation, not an
observation; aggregated results are more robust than individual cells.

## Streamed sources can change

Two inputs are read live from their publishers: OpenLandMap-soildb (step 05) and the WRI/GFW organic-soils
model (step 08). The GFW data has been corrected in place before, under the same path. Re-running those steps
reads whatever is published at the time; the harmonized layers published with the release are the exact ones
v1.0.0 used, and `verify.py` reports any difference.

## One unreconciled difference from the COC tool's own code

The code released with the COC tool takes native plant carbon from a single Erb et al. panel (Extended Data
Figure 4E), whereas this method uses the five-map mean. The two are not expected to differ greatly, but the
choice has not been reconciled.
