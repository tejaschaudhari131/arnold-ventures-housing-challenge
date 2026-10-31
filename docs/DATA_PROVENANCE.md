# Data Provenance

Stateframe uses public statistical series and aggregate GIS counts. The code license does not relicense the data. No raw parcel file, owner table, or household microdata is committed. The committed benchmark is `data/sample/fixtures.json`, `data/sample/tier1_benchmarks.json`, and `data/sample/transit_inventory.json`, written as aggregates on 2026-10-25. `bash scripts/get_data.sh` refreshes the Census and FHFA portion into `data/cache/` and falls back to the committed files if the network call fails.

# Dataset Inventory

| Dataset | Source | Version / vintage | Access date | License / terms | Category |
| ------- | ------ | ----------------- | ----------- | --------------- | -------- |
| ACS 2019–2023 5-year table-based summary file | U.S. Census Bureau, www2.census.gov, tables B25001, B25002, B25003, B25024, B25034, B25064, B25077, B19013, B08301 | 2019–2023 5-year | 2026-10-25 | Public domain, U.S. government work | Public |
| Building Permits Survey, state and county annual files | U.S. Census Bureau, www2.census.gov, `stYY12y.txt` and `coYY12y.txt` | Average of 2022, 2023, 2024 | 2026-10-25 | Public domain, U.S. government work | Public |
| Population estimates, NST-EST2024-ALLDATA | U.S. Census Bureau | July 1, 2020 to July 1, 2024 | 2026-10-25 | Public domain | Public |
| County gazetteer | U.S. Census Bureau, 2024 gazetteer | 2024 land area, names, and interior points (`INTPTLAT`, `INTPTLONG`) | 2026-10-25 | Public domain | Public |
| House Price Index, All-Transactions, states | Federal Housing Finance Agency, www.fhfa.gov, `hpi_at_state` workbook | Through 2025; workbook header dated March 31, 2026; index 2000=100 | 2026-10-25 | Public FHFA statistical release | Public |
| Connecticut CAMA and Parcel Layer | services3.arcgis.com, Connecticut_CAMA_and_Parcel_Layer | Statewide feature count and lot-size bins | 2026-10-25 | Connecticut open data; aggregates only stored here | State-provided |
| Wisconsin Statewide Parcels DB V1200 | services3.arcgis.com, Wisconsin_Statewide_Parcels_DB | 2026 vintage, improved residential class bins | 2026-10-25 | Wisconsin statewide parcel program; aggregates only | State-provided |
| Utah Housing Unit Inventory | services1.arcgis.com, HousingUnitInventory | Urban-county inventory, 702,461 records summarized | 2026-10-25 | Utah Geospatial Resource Center / SGID derivative; aggregates only | State-provided |
| Hawaii ParcelsZoning | geodata.hawaii.gov MapServer, parcel layer 25 and State Land Use layer 20 | Statewide TMK count and district acres | 2026-10-25 | Hawaii statewide GIS; aggregates only | State-provided |
| Major transit stop inventory | Screened from agency system maps and NTD descriptions (SEPTA, Port Authority, Metro-North, Shore Line East, Hartford Line, CTfastrak, The Hop, Milwaukee East-West BRT, TRAX, FrontRunner, MAX, WES, Skyline, Valley Metro, Metrorail, VRE, The Tide, Music City Star, RIPTA R-Line, MBTA Providence Line) | Compiled 2026-10-25 from 2024–2025 public descriptions | 2026-10-25 | Team-created counts of public facts; not a GTFS extract | Team-created |
| Legal-baseline shares | `config/assumptions.yaml` state blocks, with statute pointers (CT PA 21-29, NH RSA 674:72, OR HB 2001 / UGB assumption) | Model assumptions, low/central/high | 2026-10-25 | Team-created assumptions, not a dataset | Team-created |

The Census API at api.census.gov now returns an HTML "Missing Key" page without a key. Acquisition does not use that API. It streams the published summary files, which require no key. `CENSUS_API_KEY` in `.env.example` is documented and unused.

National Transit Database SODA endpoints returned HTTP 404 during this build. The transit file is therefore a screened count with a scale slider, not a silent substitute that pretends to be a live feed.

# Cleaning and Preparation

**ACS.** State rows are summary level 040 and county rows are summary level 050, kept only for the eleven challenge FIPS codes. Housing structure: 1-unit detached and attached, 2-unit, 3–4, and 5+ (the 5–9, 10–19, 20–49, and 50+ lines). Mobile homes are stored and excluded from the ADU stock. Pre-1940 share is the pre-1940 line of B25034 over the table total. Transit commute share is B08301 estimate column E010, "Public transportation (excluding taxicab)." Column E005 is the 2-person carpool line and is not used. A regression check refuses a Pennsylvania transit share outside 2.5 to 5.5 percent, which is where a carpool/transit mix-up would land. Suppressed county medians are filled from the state median and flagged `value_imputed`.

**Geography.** Connecticut is the nine planning regions in the 2019–2023 ACS and the 2024 gazetteer (FIPS 09110–09190), not the retired eight counties. County names come from the gazetteer. Land area is `ALAND_SQMI`. Interior points for the clickable map are the same file's `INTPTLAT` and `INTPTLONG`, stored only for the eleven challenge states in `data/sample/county_points.json` (about 65 KB). The browser draws a convex hull and a circle per county. It does not ship a TIGER shapefile. `scripts/get_data.sh` rewrites `data/cache/county_points.json` from the same gazetteer zip, and `--write-sample` can refresh the committed copy.

**Permits.** State file dollar values are in thousands; county file dollar values are in dollars. Units are averaged over 2022, 2023, and 2024. A county missing from one year's file contributes nothing that year, and the divisor is still three, so a one-year reporter is not scaled up. Segments are 1-unit, 2-unit, 3–4, and 5+. County segments are then reconciled to the state segment total (see the model overview). The national unit value is the unit-weighted mean across states in the state file: $297,175 single-family and $150,337 multifamily. State cost indexes are state unit value over that anchor, shrunk toward 1 below 800 units, clamped to [0.55, 2.40].

**FHFA.** The published URL ends in `.csv` and the body is an xlsx workbook. It is parsed with the Python standard library (`zipfile` and `ElementTree`). Column B is the state abbreviation, column D is the year, column H is the 2000=100 index. The series must contain 2020. The latest year in this vintage is 2025.

**Population.** Annualized four-year rate from POPESTIMATE2020 to POPESTIMATE2024.

**Connecticut parcels.** Feature count 1,320,686. `Land_Acres` is integer-rounded and was not used for bins. Bins use `Shape__Area`, which has square-foot magnitude. Single-family use codes 101, 1010, 101.0, and 107: 569,165 lots in seven bins from under 5,000 square feet to over 2 acres. The zone field is a municipal code, not a normalized zone class, so the model uses current use for the lot screen and does not pretend the layer is a zoning ordinance.

**Wisconsin parcels.** Improved residential class (PROPCLASS 1), 1,188,351 lots in acre bins converted to square feet. Class 1 is not pure single-family. Eligible homes are capped at the ACS single-family stock.

**Utah.** 702,461 inventory records. Single-family: 637,533 records, 688,521 units, mean 0.512 acres (22,218 square feet). Multifamily: 64,928 records, 372,859 units. Covered units 1,061,380 in urban counties. The service rejected percentile `outStatistics`, so there are no bins; the lognormal tail is the documented substitute. Coverage is urban counties, not every rural SGID parcel.

**Hawaii.** 384,035 TMK parcels. No normalized zoning class on layer 25. State Land Use acres: Urban 204,062, Agricultural 1,885,399, Conservation 2,022,333, Rural 10,459. Urban land share 0.0495. The model does not apply that 5 percent to the housing stock. Almost all homes sit in the urban district. `geography_eligible_share` (central 0.93) is the assumed stock share, and the tier-2 screen sets it to 1.0 when the wall is hidden.

**Transit counts (rail / BRT / frequent-bus miles / overlap).** Pennsylvania 290 / 24 / 70 / 0.42. Connecticut 52 / 11 / 18 / 0.28. Wisconsin 18 / 19 / 12 / 0.20. Utah 72 / 8 / 22 / 0.30. Oregon 100 / 8 / 40 / 0.38. Hawaii 9 / 0 / 15 / 0.15. Arizona 56 / 6 / 25 / 0.25. Virginia 56 / 10 / 30 / 0.33. Tennessee 18 / 6 / 14 / 0.12. Rhode Island 3 / 6 / 10 / 0.10. New Hampshire 0 / 0 / 4 / 0.05.

**Pennsylvania tier-2 note.** All 67 counties have ACS prices and reconciled permits. That is the county calibration. No embedded parcel measurement is included for Allegheny, Philadelphia, or Montgomery. A later adapter can point at PASDA and must pass `assert_no_pii`. Completeness stays at 0.70 until that extract exists.

# Known Limitations

- ACS 2019–2023 is a five-year pool centered before the latest permit year. Prices and the permit run-rate are not the same vintage. The price-shock and cost-index sliders are the bridge.
- Permit valuations are not construction-cost indices. They are what applicants stated. The FHFA index is a price index, not a cost index. Both are labeled as such.
- Connecticut planning regions and the old county names will not match a user who still thinks in the eight-county map.
- Hawaii's multifamily permit valuation is high and the cell survived shrinkage. Transit-oriented projects there mostly do not pencil. That is a data fact the model refuses to clamp away.
- Transit counts will drift as lines open (Honolulu Skyline later segments are excluded on purpose) or as headways change. Move `tod_station_scale`.
- Oregon's urban-growth-boundary share is an assumption (central 0.86), not an ingested boundary.
- Utah's lot distribution is a mean plus a lognormal assumption.
- The acquisition allowlist is www2.census.gov, www.fhfa.gov, services3.arcgis.com, services1.arcgis.com, and geodata.hawaii.gov. Any other host is rejected.

# Restricted, Sensitive, or Personal Data

No dataset of individuals, households, owners, or mailing addresses is used or stored. Parcel services were queried for counts, sums, and lot-size bins. The adapter refuses records that contain owner, co-owner, mailing address, or account-number fields (`FORBIDDEN_PARCEL_FIELDS`). The committed JSON cannot be walked back to a person. County medians are Census published cells, already aggregated. No restricted-use Census file, no state wage file, and no brokerage listing feed is used.
