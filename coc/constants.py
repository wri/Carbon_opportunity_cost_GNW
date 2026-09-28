"""
Every numeric assumption of the method in one place, with where it comes from.
"""

CO2_PER_C = 44.0 / 12.0            # tC -> tCO2
YIELD_KG_TO_T = 1.0 / 1000.0       # MapSPAM yield is kg/ha
ANNUALIZATION_YEARS = 30           # stock loss spread over 30 years: the COC tool's basis

# Rubber is the one tree crop with no COC tool factor (no Table A-8 row), so without this it would take
# the all-crop mean of the tool's ag-plant values (~4.2 tC/ha), about a tenth of its real standing
# stock. IPCC 2019 Refinement Vol 4 Ch 5 Table 5.3: rubber Lmean = 40.1 tC/ha (time-averaged,
# +/-15%, 27-year cycle; Blagodatsky, Xu & Cadisch 2016). Above-ground only, like the Table A-8 rows
# that supply the other tree crops.
IPCC_RUBBER_AGB_TC_HA = 40.1

# Cornell biomass -> agricultural plant carbon (pipeline/04).
CARBON_FRACTION_DM = 0.47          # tC per t dry matter, IPCC default
TIME_AVERAGE = 0.5                 # peak standing stock -> time-averaged stock
MAX_DM_DENSITY_T_HA = 100.0        # above this, a cell is a footprint mismatch, not data (~4x sugarcane)

# COC tool Table A-9: fraction of native soil carbon lost on conversion to agriculture, by native
# ecosystem (the codes of harmonized/biome/a9_native_class.tif). Negative = a gain (irrigated
# drylands, Wang et al. 2023). Run BACKWARDS here: native = measured / (1 - f). pipeline/07.
A9_LOSS_ANNUAL = {1: 0.25, 2: 0.30, 3: 0.20, 4: 0.15, 5: -0.40, 6: -0.80}
# "Permanent tree and bush crops (assume 20% lower C loss vs. annual non-grass crops)". The dryland
# rows are stated identically in both columns, so the 20% reduction applies only where f > 0.
A9_LOSS_PERENNIAL = {k: (round(v * 0.8, 4) if v > 0 else v) for k, v in A9_LOSS_ANNUAL.items()}
A9_CLASS_NAMES = {1: "Tropical forest", 2: "Temperate forest",
                  3: "Tropical and temperate shrubland and grassland",
                  4: "Montane and other grassland",
                  5: "Mediterranean forest and shrub (dryland)", 6: "Desert"}

# SPAM crops that take Table A-9's "permanent tree and bush crops" column; everything else is annual.
# OOIL and REST are mixed baskets (olive and tree nuts beside annual oilseeds) and stay annual, the
# majority case. Sugarcane is a ratooned grass, not a tree or bush, and stays annual too.
PERENNIAL_CODES = frozenset({
    "BANA", "CITR", "CNUT", "COCO", "COFF", "OILP",
    "PLNT", "RCOF", "RUBB", "TEAS", "TEMF", "TROF",
})
