"""
The COC tool's country/region scheme on the MapSPAM grid.

The tool states its factors per crop for Global, 10 regions and 4 override countries (Brazil, China,
India, United States). Table A-1 of the tool lists which countries make up each region. This module
turns that into rasters:

  geo_key      uint8, the tool geography (1-10 region, 11-14 override country) covering each cell's
               centre, 0 outside every listed country. Used to paint the tool's tabular factors.
  country_key  int32, one code per country, for aggregating results back to national level.

Countries come from GADM 4.1 ADM0 (`GID_0` is the ISO3 code): the 157 in Table A-1, matched by name
via pycountry, plus a curated SUPPLEMENT of 36 sovereign countries with cropland that Table A-1 omits.
The build is strict: any country that fails to resolve aborts it, because an unresolved country would
silently become a hole in every crop layer.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pycountry
from rasterio.features import rasterize
from shapely import union_all
from shapely.validation import make_valid

from coc import paths
from coc.grid import TH, TT, TW

# GADM carves nine disputed zones out of India/China/Pakistan as their own GID_0 codes, so their
# cropland (~3.4 Mha, mostly Jammu & Kashmir) would otherwise fall outside every country. Each is
# folded into the country GADM ITSELF names in that unit's COUNTRY column, re-checked at load time.
GADM_DISPUTED_PARENT = {
    "Z01": "IND", "Z02": "CHN", "Z03": "CHN", "Z04": "IND", "Z05": "IND",
    "Z06": "PAK", "Z07": "IND", "Z08": "CHN", "Z09": "IND",
}

# COC tool workbook layout
SHEET_RAW = "Raw LO and COC data"
SHEET_TABLEA1 = "Table A-1"
COL_REGION, COL_ITEM = 1, 2        # Raw sheet: B = REGION, C = ITEM; F (5) = agricultural plant carbon
DATA_START_ROW = 5                 # rows 0-4 are the multi-row header + notes
GEOKEY_NODATA = 0

# region code -> (short label, REGION string exactly as it appears in the Raw sheet)
REGIONS = {
    1: ("CAS", "Central Asia"),
    2: ("EAS", "East Asia"),
    3: ("EUR", "Europe"),
    4: ("MEA", "Middle East & N. Africa"),
    5: ("NAM", "North America"),
    6: ("OCE", "Oceania"),
    7: ("RUS", "Russia"),
    8: ("SAM", "South America"),
    9: ("SAS", "South Asia"),
    10: ("SSA", "Sub-Saharan Africa"),
}
# override country code -> (label, REGION string, ISO3, parent-region REGION string)
OVERRIDES = {
    11: ("Brazil", "Brazil", "BRA", "South America"),
    12: ("China", "China", "CHN", "East Asia"),
    13: ("India", "India", "IND", "South Asia"),
    14: ("United States", "United States", "USA", "North America"),
}
GLOBAL_NAME = "Global"
HDR_CODE_TO_REGION = {"CAS": 1, "EAS": 2, "EUR": 3, "MEA": 4, "NAM": 5,
                      "OCE": 6, "RUS": 7, "SAM": 8, "SAS": 9, "SSA": 10}
OVERRIDE_ISO3 = {"BRA": 11, "CHN": 12, "IND": 13, "USA": 14}
VALID_REGION_VALUES = ({GLOBAL_NAME}
                       | {v[1] for v in REGIONS.values()}
                       | {v[1] for v in OVERRIDES.values()})

# Table A-1 names pycountry does not resolve directly.
NAME_ALIAS_ISO3 = {
    "Palestine": "PSE",
    "Turkey": "TUR",
    "Democratic Republic of the Congo": "COD",
}

# SUPPLEMENT — sovereign countries with cropland that Table A-1 omits, assigned to a COC region.
#   - Pacific islands -> East Asia, following the tool's own placement of Papua New Guinea there.
#   - Djibouti -> Sub-Saharan Africa, with its Horn-of-Africa neighbours.
#   - Hong Kong and Macau have no GADM ADM0 unit and inherit China from China's polygon.
#   - Overseas territories (French Guiana, Reunion, ...), Aland and Northern Cyprus are left out by
#     choice (sovereign states only): ~0.06 Mha of cropland stays unassigned.
# GADM serves Kosovo as "XKO".
SUPPLEMENT_ISO3_REGION = {
    "ISL": 3, "LUX": 3, "MLT": 3, "MNE": 3, "XKO": 3,
    "TWN": 2, "BRN": 2,
    "FJI": 2, "SLB": 2, "VUT": 2, "WSM": 2, "TON": 2,
    "KIR": 2, "FSM": 2, "MHL": 2, "PLW": 2, "TUV": 2, "NRU": 2,
    "BTN": 9, "MDV": 9,
    "GUY": 8, "SUR": 8, "BLZ": 8,
    "BHS": 8, "BRB": 8, "ATG": 8, "DMA": 8, "GRD": 8, "KNA": 8, "LCA": 8, "VCT": 8,
    "DJI": 10, "COM": 10, "CPV": 10, "STP": 10, "SYC": 10,
}
SUPPLEMENT_NAMES = {
    "ISL": "Iceland", "LUX": "Luxembourg", "MLT": "Malta", "MNE": "Montenegro",
    "XKO": "Kosovo",
    "TWN": "Taiwan", "BRN": "Brunei",
    "FJI": "Fiji", "SLB": "Solomon Islands", "VUT": "Vanuatu", "WSM": "Samoa",
    "TON": "Tonga", "KIR": "Kiribati", "FSM": "Micronesia (Fed. States of)",
    "MHL": "Marshall Islands", "PLW": "Palau", "TUV": "Tuvalu", "NRU": "Nauru",
    "BTN": "Bhutan", "MDV": "Maldives",
    "GUY": "Guyana", "SUR": "Suriname", "BLZ": "Belize", "BHS": "Bahamas",
    "BRB": "Barbados", "ATG": "Antigua and Barbuda", "DMA": "Dominica",
    "GRD": "Grenada", "KNA": "Saint Kitts and Nevis", "LCA": "Saint Lucia",
    "VCT": "Saint Vincent and the Grenadines",
    "DJI": "Djibouti", "COM": "Comoros", "CPV": "Cabo Verde",
    "STP": "Sao Tome and Principe", "SYC": "Seychelles",
}


def norm(s) -> str:
    "Lowercase, strip diacritics/punctuation, expand '&', collapse whitespace."
    if s is None:
        return ""
    s = str(s).replace("&", " and ")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def slugify(name: str) -> str:
    "Filename slug from an item name: 'Rice (unprocessed)' -> 'rice_unprocessed'."
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def code_maps():
    "(code -> short label, code -> REGION string as spelled in the Raw sheet) for codes 1-14."
    code_to_label = {c: lab for c, (lab, _r) in REGIONS.items()}
    code_to_label.update({c: lab for c, (lab, _r, _i, _p) in OVERRIDES.items()})
    region_value_by_code = {c: r for c, (_lab, r) in REGIONS.items()}
    region_value_by_code.update({c: r for c, (_lab, r, _i, _p) in OVERRIDES.items()})
    return code_to_label, region_value_by_code


def _sql_in(codes) -> str:
    return "GID_0 IN (" + ",".join(f"'{c}'" for c in sorted(codes)) + ")"


def _to_wgs84(g):
    if g.crs is None:
        return g.set_crs(4326)
    return g if str(g.crs) == "EPSG:4326" else g.to_crs(4326)


def parse_tableA1_region_table(xlsx: Path) -> pd.DataFrame:
    "[region_code, region_label, country_name], one row per Table A-1 country (one column per region)."
    df = pd.read_excel(xlsx, sheet_name=SHEET_TABLEA1, header=None, engine="openpyxl")
    hdr_row = None
    for i in range(len(df)):
        if any("(CAS)" in str(x) for x in df.iloc[i].tolist() if x is not None):
            hdr_row = i
            break
    if hdr_row is None:
        sys.exit("Could not find the region-header row in Table A-1")
    col_region_code = {}
    for j in range(df.shape[1]):
        m = re.search(r"\(([A-Z]{3})\)", str(df.iat[hdr_row, j]))
        if m and m.group(1) in HDR_CODE_TO_REGION:
            col_region_code[j] = HDR_CODE_TO_REGION[m.group(1)]
    rows = []
    for j, rc in col_region_code.items():
        for i in range(hdr_row + 1, len(df)):
            cell = df.iat[i, j]
            if cell is None or (isinstance(cell, float) and pd.isna(cell)):
                continue
            name = str(cell).strip()
            if name:
                rows.append({"region_code": rc, "region_label": REGIONS[rc][0], "country_name": name})
    return pd.DataFrame(rows)


def resolve_iso3(name: str):
    "Country name -> (ISO3, method): hand-curated alias, then exact pycountry lookup, then fuzzy."
    if name in NAME_ALIAS_ISO3:
        return NAME_ALIAS_ISO3[name], "alias"
    try:
        return pycountry.countries.lookup(name).alpha_3, "pycountry.lookup"
    except LookupError:
        pass
    try:
        res = pycountry.countries.search_fuzzy(name)
        if res:
            return res[0].alpha_3, "pycountry.fuzzy"
    except LookupError:
        pass
    return None, "FAILED"


def load_gadm_adm0(iso3s):
    "({ISO3: geometry}, {ISO3: GID_0 units assembled}, [ISO3s GADM lacks]), disputed zones folded in."
    if not paths.GADM_ADM0.exists():
        sys.exit(f"GADM ADM0 shapefile not found: {paths.GADM_ADM0}")
    wanted = set(iso3s)
    zones = {z: p for z, p in GADM_DISPUTED_PARENT.items() if p in wanted}
    g = _to_wgs84(gpd.read_file(paths.GADM_ADM0, engine="pyogrio", where=_sql_in(wanted | set(zones))))

    by_code = {}
    for gid, country, geom in zip(g["GID_0"], g["COUNTRY"], g.geometry):
        if geom is None or geom.is_empty:
            continue
        by_code[gid] = (country, geom if geom.is_valid else make_valid(geom))

    parts = {iso: [by_code[iso][1]] for iso in wanted if iso in by_code}
    for z, parent in zones.items():
        if z not in by_code or parent not in parts:
            continue
        label = by_code[z][0]
        if resolve_iso3(label)[0] != parent:
            sys.exit(f"GADM unit {z} is labelled '{label}', not {parent} — "
                     f"re-check GADM_DISPUTED_PARENT before proceeding.")
        parts[parent].append(by_code[z][1])

    geoms, units = {}, {}
    for iso, ps in parts.items():
        geom = ps[0] if len(ps) == 1 else union_all(ps)
        if geom is None or geom.is_empty:
            continue
        geoms[iso] = geom if geom.is_valid else make_valid(geom)
        units[iso] = [iso] + sorted(z for z, p in zones.items() if p == iso and z in by_code)
    return geoms, units, sorted(wanted - set(by_code))


def build_geography(xlsx: Path = None):
    """(gdf, table, failures): the 157 Table A-1 countries + the supplement, each with its GADM polygon,
    COC region and geo_code (the region, or 11-14 for the override countries)."""
    xlsx = xlsx or paths.COC_TOOL_XLSX
    rt = parse_tableA1_region_table(xlsx)
    rt["iso3_fixed"] = None
    print(f"Table A-1: parsed {len(rt)} countries")
    supp = pd.DataFrame([
        {"region_code": rc, "region_label": REGIONS[rc][0],
         "country_name": SUPPLEMENT_NAMES.get(iso, iso), "iso3_fixed": iso}
        for iso, rc in SUPPLEMENT_ISO3_REGION.items()
    ])
    rt = pd.concat([rt, supp], ignore_index=True)
    print(f"Supplement: added {len(supp)} sovereign countries not in Table A-1")

    resolved, failed_iso = [], []
    for _, r in rt.iterrows():
        name, rc = r["country_name"], int(r["region_code"])
        fixed = r.get("iso3_fixed")
        if isinstance(fixed, str) and fixed:
            iso3, method = fixed, "supplement"
        else:
            iso3, method = resolve_iso3(name)
        if not iso3:
            failed_iso.append({"country_name": name, "region_label": REGIONS[rc][0]})
        resolved.append((name, rc, iso3, method))

    geoms, units, absent = load_gadm_adm0({i for _n, _rc, i, _m in resolved if i})
    print(f"GADM ADM0: matched {len(geoms)} of {len(rt)} countries")

    recs, missing_in_gadm, no_geometry = [], [], []
    for name, rc, iso3, method in resolved:
        gadm_units = ";".join(units.get(iso3, [])) if iso3 else None
        base = {"region_code": rc, "region_label": REGIONS[rc][0], "country_name": name,
                "iso3": iso3, "iso_method": method, "gadm_units": gadm_units}
        if not iso3:
            recs.append({**base, "geometry": None})
            continue
        if iso3 in absent:
            missing_in_gadm.append({"country_name": name, "iso3": iso3, "gadm_file": paths.GADM_ADM0.name})
            recs.append({**base, "geometry": None})
            continue
        geom = geoms.get(iso3)
        if geom is None:
            no_geometry.append({"country_name": name, "iso3": iso3, "gadm_units": gadm_units})
            recs.append({**base, "geometry": None})
            continue
        recs.append({**base, "geometry": geom})

    df = pd.DataFrame(recs)
    with_geom = df[df["geometry"].notna()]
    dup_iso = with_geom["iso3"].value_counts()
    duplicates = []
    for iso3, n in dup_iso[dup_iso > 1].items():
        regions_hit = sorted(with_geom.loc[with_geom.iso3 == iso3, "region_label"].unique())
        duplicates.append({"iso3": iso3, "count": int(n), "regions": ",".join(regions_hit),
                           "names": ";".join(with_geom.loc[with_geom.iso3 == iso3, "country_name"])})

    gdf = gpd.GeoDataFrame(with_geom.copy(), geometry="geometry", crs="EPSG:4326")
    gdf["geo_code"] = gdf["region_code"]
    ov = gdf["iso3"].map(OVERRIDE_ISO3)
    gdf.loc[ov.notna(), "geo_code"] = ov[ov.notna()].astype(int)
    gdf["is_override"] = gdf["geo_code"] >= 11

    failures = {"failed_iso": failed_iso, "missing_in_gadm": missing_in_gadm,
                "no_geometry": no_geometry, "duplicates": duplicates}
    return gdf, df, failures


def _burn(gdf, column, dtype):
    "Rasterize polygons by cell centre, largest first (GADM ADM0 is a clean partition, so order is moot)."
    items = [(geom, int(code)) for geom, code in zip(gdf.geometry, gdf[column])
             if geom is not None and not geom.is_empty]
    items.sort(key=lambda gc: gc[0].area, reverse=True)
    return rasterize(items, out_shape=(TH, TW), transform=TT, fill=GEOKEY_NODATA,
                     all_touched=False, dtype=dtype), len(items)


def rasterize_geo_key(gdf):
    "geo_key (uint8): the COC geography code 1-14 covering each cell's centre, 0 where none does."
    return _burn(gdf, "geo_code", "uint8")


def rasterize_country_key(gdf):
    "(country_key int32, table): a unique code 1..N per country, in build_geography order."
    gdf = gdf.reset_index(drop=True)
    gdf["country_key"] = np.arange(1, len(gdf) + 1)
    key, _ = _burn(gdf, "country_key", "int32")
    table = gdf[["country_key", "country_name", "iso3", "region_code", "region_label", "geo_code"]]
    return key, table


def value_vector(row_lookup):
    """(vals[15] float32, status{code: present|from_parent|from_global|missing}) for one crop.

    The Raw sheet is sparse, so each code is filled by a fallback chain:
        region (1-10):   own region value -> Global -> missing
        override (11-14): own country value -> its parent region -> Global -> missing
    Index 0 stays NaN, so vals[geo_key] paints cells outside every country as NaN.
    """
    vals = np.full(15, np.nan, dtype="float32")
    status = {}
    g = row_lookup.get(GLOBAL_NAME)
    for code, (_label, rname) in REGIONS.items():
        if rname in row_lookup:
            vals[code] = row_lookup[rname]; status[code] = "present"
        elif g is not None:
            vals[code] = g; status[code] = "from_global"
        else:
            status[code] = "missing"
    for code, (_label, rname, _iso3, parent) in OVERRIDES.items():
        if rname in row_lookup:
            vals[code] = row_lookup[rname]; status[code] = "present"
        elif parent in row_lookup:
            vals[code] = row_lookup[parent]; status[code] = "from_parent"
        elif g is not None:
            vals[code] = g; status[code] = "from_global"
        else:
            status[code] = "missing"
    return vals, status


def write_geo_qc(df, gdf, failures, qc_dir: Path):
    "The country -> region table and the four strict-fail logs (written even when empty)."
    code_to_label, _ = code_maps()
    qc_dir = Path(qc_dir)
    qc_dir.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    out["geo_code"] = out["iso3"].map(dict(zip(gdf["iso3"], gdf["geo_code"])))
    out["geo_label"] = out["geo_code"].map(code_to_label)
    out["is_override"] = out["geo_code"].apply(lambda c: bool(c) and c >= 11)
    out["has_geometry"] = out["geometry"].notna()
    out.drop(columns=["geometry"]).to_csv(qc_dir / "country_region_table.csv", index=False, encoding="utf-8")
    pd.DataFrame(failures["failed_iso"], columns=["country_name", "region_label"]) \
        .to_csv(qc_dir / "failed_iso_mappings.csv", index=False, encoding="utf-8")
    pd.DataFrame(failures["missing_in_gadm"], columns=["country_name", "iso3", "gadm_file"]) \
        .to_csv(qc_dir / "missing_gadm_units.csv", index=False, encoding="utf-8")
    pd.DataFrame(failures["duplicates"], columns=["iso3", "count", "regions", "names"]) \
        .to_csv(qc_dir / "duplicate_countries.csv", index=False, encoding="utf-8")
    pd.DataFrame(failures["no_geometry"], columns=["country_name", "iso3", "gadm_units"]) \
        .to_csv(qc_dir / "countries_without_geometry.csv", index=False, encoding="utf-8")
