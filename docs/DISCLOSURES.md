# Disclosures

Prepared for the Arnold Ventures / The Turnout Housing Data and Technology Innovation Challenge by Tejas Chaudhari (tchaudha@andrew.cmu.edu), Yoon Yik Ng (yoonyikn@andrew.cmu.edu), and Christopher Severns (cseverns@andrew.cmu.edu), Carnegie Mellon University.

# Prior work

PlayHouse is an earlier Pittsburgh parcel explorer by Tejas Chaudhari. The repository is [github.com/tejaschaudhari131/playhouse](https://github.com/tejaschaudhari131/playhouse). A deployment is at [playhouse-pittsburgh.vercel.app](https://playhouse-pittsburgh.vercel.app). It was written before the Registration and Coding Periods of this challenge, it has no open-source license, and it operates at city and parcel scale. It is not this submission, and it cannot be submitted under Rules §7a and §7c.

Stateframe borrows interaction ideas from that project only: a map a person can click, before-and-after numbers, plain language next to a result, controls that reset, a flag when a result is close, and a one-page brief. Yoon Yik Ng and Christopher Severns are co-authors of Stateframe. No PlayHouse source file, stylesheet, image, icon, 3D asset, or parcel extract was copied, forked, or vendored. The map in this repository is generated in the browser from Census gazetteer interior points in `data/sample/county_points.json`. The scenario arithmetic is the county pro forma in `src/model/`.

# AI-Assisted Code Generation

Cursor cloud agents and Grok Bot assistants drafted code, tests, the web client, and documentation under the authors' specification. The authors are responsible for the equations, the committed figures, and the Apache-2.0 license on the output. Cursor's terms, as used for this challenge submission, permit the authors to own and openly license the generated source. No prompt, weight, or hidden chain is required to run, test, or modify Stateframe. A reviewer can recompute every published integer from `bash scripts/test.sh` and the files in `config/` and `data/sample/`.

The same assistants were used for wording in this disclosure. The running application does not call a model API.

# Pretrained Models, Weights, and Embeddings

None. The runtime path is closed-form arithmetic in `src/model/equations.py` plus the Python standard library and PyYAML. The normal CDF is `math.erf`. There is no scikit-learn, PyTorch, TensorFlow, ONNX, embeddings file, or remote inference call.

| Model / asset | Source | License / terms | Restrictions |
| ------------- | ------ | --------------- | ------------ |
| None | — | — | No pretrained model is shipped or called |

# External APIs and Hosted Services

The installed app runs offline on `data/sample/`. Live refresh is optional.

| Service | Used for | Required to run? | Terms |
| ------- | -------- | ---------------- | ----- |
| www2.census.gov summary files | ACS, BPS, PEP, gazetteer | No. Fallback is the committed benchmark | Public domain data, no key |
| www.fhfa.gov state HPI workbook | State house-price index | No. Same fallback | Public statistical release |
| api.census.gov | Not called. The API now requires a key and is avoided on purpose | No | Optional `CENSUS_API_KEY` is unused |
| ArcGIS / Hawaii GIS feature services | One-time aggregate counts stored in `tier1_benchmarks.json` | No | Public open-data services; only aggregates are stored |
| National Transit Database SODA | Attempted; endpoints returned 404. Not a runtime dependency | No | Replaced by the screened inventory |

No paid API, no authentication token, and no service whose disappearance changes a result the tests already locked. `scripts/get_data.sh` exits 0 when the network fails and leaves the sample benchmark in place.

# Datasets

Every series below is public and is on the challenge data list, except the team-created legal screens and the screened transit counts, which are assumptions or compilations of public facts rather than a redistributed dataset. The code license does not relicense the data. Full vintages, cleaning, and the privacy rule are in `docs/DATA_PROVENANCE.md`.

| Dataset | License or terms | Where it appears |
| ------- | ---------------- | ---------------- |
| ACS 2019–2023 5-year summary file (Census) | Public domain, U.S. government work | `data/sample/fixtures.json` |
| Building Permits Survey, 2022–2024 state and county files (Census) | Public domain, U.S. government work | `data/sample/fixtures.json` |
| Population estimates NST-EST2024 (Census) | Public domain, U.S. government work | `data/sample/fixtures.json` |
| County gazetteer, 2024, land area and interior points (Census) | Public domain, U.S. government work | `data/sample/fixtures.json` and `data/sample/county_points.json` |
| FHFA All-Transactions state house-price index | Public FHFA statistical release | `data/sample/fixtures.json` |
| Connecticut CAMA and parcel aggregates | Connecticut open data; counts and lot-size bins only | `data/sample/tier1_benchmarks.json` |
| Wisconsin Statewide Parcels, improved residential class bins | Wisconsin statewide parcel program; aggregates only | `data/sample/tier1_benchmarks.json` |
| Utah Housing Unit Inventory aggregates | Utah Geospatial Resource Center / SGID derivative; aggregates only | `data/sample/tier1_benchmarks.json` |
| Hawaii parcel count and State Land Use acres | Hawaii statewide GIS; aggregates only | `data/sample/tier1_benchmarks.json` |
| Major transit stop inventory | Team-compiled counts of public system facts, not a GTFS extract | `data/sample/transit_inventory.json` |
| Legal-baseline shares | Team assumptions in `config/assumptions.yaml`, not a dataset | `config/assumptions.yaml` |
| ACS 2020–2024 5-year (Lab) | Public domain, U.S. government work | `data/sample/lab/{PA,NH}.json` |
| Census cartographic boundaries, counties 2024 (Lab) | Public domain; simplified in-repo | `data/sample/lab/{PA,NH}_counties.geo.json` |
| WPRDC Allegheny assessments, lot-area bins only | CC0 1.0; 2012 base-year land values | `data/sample/lab/allegheny_lots.json` |
| HUD FY2026 FMR workbook (optional Lab context) | Public domain; not a model input | committed extract, vintage labeled |
| Lab zoning evidence | Team summaries of public law with source URLs | `config/lab/evidence/{PA,NH}.yaml` |

No raw parcel geometry, owner table, or household microdata is committed. `scripts/get_data.sh` refreshes the Census and FHFA portion, including gazetteer interior points, and falls back to `data/sample/` when the network is unavailable.

# Dependency Licenses

Direct dependencies are pinned in `requirements.txt`. `tests/test_licenses.py` reads installed metadata and fails if a pin is missing from the allowlist or if the license text contains GPL, LGPL, AGPL, MPL, EUPL, CC0, or SSPL. Transitive test dependencies (pulled only because pytest depends on them) are listed for completeness. None are imported by `src/`.

| Dependency | License | Runtime or dev-only | Notes |
| ---------- | ------- | ------------------- | ----- |
| PyYAML 6.0.2 | MIT | Runtime | `yaml.safe_load` only |
| pytest 8.3.5 | MIT | Dev | Test runner |
| ruff 0.14.2 | MIT | Dev | Linter invoked by `scripts/test.sh` when the venv exists |
| pluggy (pytest) | MIT | Dev, transitive | Not imported by the app |
| iniconfig (pytest) | MIT | Dev, transitive | Not imported by the app |
| packaging (pytest) | Apache-2.0 or BSD | Dev, transitive | Not imported by the app |

The web client has no npm dependencies, no chart library, and no remote font. Python's standard library serves HTTP. There is no Flask, FastAPI, numpy, pandas, or copyleft package.

A CycloneDX bill of materials for the direct pins is `docs/sbom.cdx.json`. GitHub's dependency graph, once Dependabot is enabled from the repository settings (the `dependabot.yml` file is already in the repo), is the upstream source of truth for alerts. No license exception is requested.

# Security settings

`SECURITY.md` and `docs/REPO_SETUP_GUIDE.md` describe the dashboard toggles for secret scanning, Dependabot alerts, and CodeQL. This repository commits `.github/workflows/codeql.yml` (Python) and `.github/dependabot.yml` (pip and GitHub Actions). The HTTP server binds to 127.0.0.1 by default, caps JSON bodies at 64 KB, uses a fixed route map (`STATIC_FILES` plus `/api/...`), and clamps assumption overrides to the published band. Responses send `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and `Referrer-Policy: no-referrer`. Parcel and WPRDC queries are not allowed to request owner or mailing fields. On Vercel, `GET /api/lab/results` reads committed files only (`allow_compute=False`). Lab acquisition reaches only www2.census.gov, data.wprdc.org, and www.huduser.gov.

Dependabot has opened version-bump pull requests #2–#5 (pytest, PyYAML, setuptools, ruff). They are left unmerged so the locked pins, the SBOM, and the license test stay on the versions this write-up names.

# Other

No noncommercial, research-only, or field-of-use restriction is added on top of Apache-2.0. Data terms remain with the data producers, as described in `docs/DATA_PROVENANCE.md`.
