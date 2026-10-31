# Committed benchmark

These files are the offline and CI dataset. They are aggregates. They contain no owner names, mailing addresses, parcel identifiers, or household records.

| File | What it is |
| ---- | ---------- |
| `fixtures.json` | Eleven states and their counties: ACS 2019–2023 stock, prices, and tenure; Building Permits Survey annual averages for 2022–2024, reconciled so counties sum to the state; FHFA state house-price index; 2020–2024 population growth; 2024 gazetteer land area and county names. |
| `tier1_benchmarks.json` | Lot-size bins and land-use totals for Connecticut, Wisconsin, Utah, and Hawaii. Counts and sums only. |
| `transit_inventory.json` | Screened counts of rail stations, BRT stations, and frequent-bus route miles, plus the definition of a major transit stop. |
| `county_points.json` | Census 2024 gazetteer interior latitude and longitude for every county and planning region in the eleven states. Public domain. Used only to draw the map. |

`lab/` holds the Small Homes Policy Lab extracts, written by `python -m src.lab.acquire --write-sample`:

| File | What it is |
| ---- | ---------- |
| `lab/PA.json`, `lab/NH.json` | Per county: ACS 2020–2024 estimates with margins of error (housing units, 1-unit detached and attached, 1- and 2-bedroom median gross rent, median value), tract density bins, Building Permits Survey 2023–2025 units and valuation by structure size, HUD FY2026 FMR cross-check. Plus the ACS place rows named in `config/lab/evidence/`. |
| `lab/PA_counties.geo.json`, `lab/NH_counties.geo.json` | Simplified Census cb_2024 5m county outlines for the Lab map. |
| `lab/allegheny_lots.json` | WPRDC Allegheny County lot-area bins (counts only), Pittsburgh vs. rest of county. |

Regenerate the Census and FHFA portion with `bash scripts/get_data.sh` when the network is available. That script writes `data/cache/fixtures.json` and leaves this folder alone unless you pass `--write-sample`. If the download fails, the script exits 0 and the simulator keeps using this folder.

Connecticut's nine rows are Census planning regions (2022 geography), not the old eight counties. The 2019–2023 ACS and the 2024 gazetteer both use that geography.
