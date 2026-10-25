# Disclosures

Prepared for the Arnold Ventures / The Turnout Housing Data and Technology Innovation Challenge by Tejas Chaudhari (tchaudha@andrew.cmu.edu), Yoon Yik Ng (yoonyikn@andrew.cmu.edu), and Christopher Severns (cseverns@andrew.cmu.edu), Carnegie Mellon University.

# AI-Assisted Code Generation

The simulator was drafted with Cursor's cloud agent (Grok) acting under the authors' specification: equations, data pulls, tests, the web client, and these documents. The authors are responsible for the equations, the committed figures, and the Apache-2.0 license on the output. Cursor's terms, as used for this challenge submission, permit the authors to own and openly license the generated source. No prompt, weight, or hidden chain is required to run, test, or modify Stateframe. A reviewer can recompute every published integer from `bash scripts/test.sh` and the files in `config/` and `data/sample/`.

Incidental use of the same assistant for wording in this disclosure is noted here.

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

`SECURITY.md` and `docs/REPO_SETUP_GUIDE.md` describe the dashboard toggles for secret scanning, Dependabot alerts, and CodeQL. This repository commits `.github/workflows/codeql.yml` (Python) and `.github/dependabot.yml` (pip and GitHub Actions). The HTTP server binds to 127.0.0.1 by default, caps JSON bodies at 64 KB, uses a fixed route map, and clamps assumption overrides to the published band. Parcel queries are not allowed to request owner or mailing fields.

# Other

No noncommercial, research-only, or field-of-use restriction is added on top of Apache-2.0. Data terms remain with the data producers, as described in `docs/DATA_PROVENANCE.md`.
