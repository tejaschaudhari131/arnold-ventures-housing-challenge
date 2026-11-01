# Stateframe

A transparent, replicable simulator of state housing reforms for the [Arnold Ventures / The Turnout Housing Data and Technology Innovation Challenge](https://housingchallenge.turnout.rocks/).

Stateframe compares a calibrated baseline with five benchmark reforms, plus a combined package, over a five-year horizon. It covers all eleven states in the official data list: Pennsylvania, Connecticut, Wisconsin, Utah, Oregon, Hawaii, Arizona, Virginia, Tennessee, Rhode Island, and New Hampshire. The arithmetic is structural and inspectable. Assumptions live in `config/assumptions.yaml`. Equations live in `src/model/equations.py`. Nothing in the runtime is a machine-learning model.

**Authors:** Tejas Chaudhari (tchaudha@andrew.cmu.edu), Yoon Yik Ng (yoonyikn@andrew.cmu.edu), and Christopher Severns (cseverns@andrew.cmu.edu), Carnegie Mellon University.

**License:** [Apache-2.0](LICENSE).

## What you can do with it

- Compare baseline permits and completions with ADUs, missing middle, transit-oriented density, parking reform, and a 50 percent fee cut.
- Open a state on the map and drill into a county. The shapes are convex hulls of Census interior points, drawn in the browser from `data/sample/county_points.json`.
- Read a scenario card with the before, the after, and a plain-language sentence.
- Switch reforms on or off, or give one a weight below 100 percent, and see the combined package.
- Move any published assumption inside its low-to-high band and recalculate. Reset restores the published case and the full reform mix.
- See a close-call badge when a margin sits near the feasibility hurdle, when the increment is under 1 percent of baseline, or when a seeded p10–p90 band crosses zero.
- Open "Show the math" for the selected state and scenario, with the numbers substituted and tagged.
- Read a tornado chart and a seeded Monte Carlo band.
- Check that county rows sum to the state.
- Walk Pennsylvania from Allegheny County up to the state total, with observed inputs separated from imputations (`docs/CASE_STUDY_PA_ALLEGHENY.md`, and the case-study tab in the app).
- Open the [Small Homes Policy Lab](https://stateframe-housing.vercel.app/lab) at https://stateframe-housing.vercel.app/lab for a 67-county Pennsylvania comparison (New Hampshire is the portability test), with a Why drawer, close-call badges, and a downloadable brief.
- Run the tier-1 states through the incomplete-data estimator and see the error.
- Export CSV, JSON, and Markdown. Every numeric field in the CSV and JSON carries an observed, assumed, or calculated tag.

## How to read a number

| Tag | Meaning |
| --- | ------- |
| observed | A public measurement stored for that place |
| assumed | A published assumption or an imputation, not a measurement for that place |
| calculated | The equations in `src/model/equations.py` |

The same three tags appear as badges in the app, on each line of "Show the math," and as `*_provenance` columns in the CSV. Pennsylvania's lot screen is assumed. Connecticut's lot screen is calculated from observed bins.

## Command contract

From a clean checkout:

```bash
bash scripts/setup.sh    # creates .venv and installs pinned dependencies
bash scripts/test.sh     # compile, pytest, and ruff
bash scripts/run.sh      # web app at http://127.0.0.1:8080
bash scripts/get_data.sh # optional refresh; works offline (keeps data/sample)
```

The same three targets exist in the `Makefile` (`make setup`, `make test`, `make run`). CI (`.github/workflows/ci.yml`) runs `scripts/setup.sh` and `scripts/test.sh`. An optional `workflow_dispatch` job (`.github/workflows/lab-results.yml`) recomputes the Lab and checks the committed fingerprints.

Lab results, from a clean checkout after setup:

```bash
PYTHONPATH=. .venv/bin/python -m src.lab.check            # fingerprint check, a few seconds
PYTHONPATH=. .venv/bin/python -m src.lab.results          # full regeneration, about 7 minutes
PYTHONPATH=. .venv/bin/python -m src.lab.results --draws 20   # quicker smoke run, not the published envelope
PYTHONPATH=. .venv/bin/python -m src.lab.run --state PA --county Allegheny
bash scripts/run.sh                                       # then open http://127.0.0.1:8080/lab
```

`python -m src.lab.results` recomputes the 2,000-draw envelope and writes `data/cache/lab/`. On an 8-core machine that is about 7 minutes (Pennsylvania about 6 minutes, New Hampshire about 1 minute). `python -m src.lab.check` compares the committed fingerprints in `data/sample/lab/results_*.json` with a fresh hash of the inputs and exits nonzero on a mismatch. It does not rerun the envelope. `--draws` shortens a regeneration; those files will not match the published fingerprints.

Write the comparison files instead of starting the server:

```bash
bash scripts/run.sh report --out output
# output/comparison.csv, comparison.json, comparison.md
```

One state, from the command line after setup:

```bash
PYTHONPATH=. .venv/bin/python -m src.cli run --state PA --out output
```

`scripts/get_data.sh` streams Census ACS, Building Permits Survey, population estimates, the county gazetteer, and the FHFA state house-price index. It does not need an API key. If the download fails, or the acquirer exits for any other reason, it prints a fallback message and exits 0 so CI and offline checkouts keep using `data/sample/`.

### HUD Fair Market Rents are fetched by hand

`scripts/get_lab_data.sh` refreshes Census, gazetteer, and boundary files. It does not download HUD Fair Market Rents. `www.huduser.gov` answers the script's user agent with an HTTP 202 challenge page, and the script does not work around that. Download the FY2026 workbook by hand:

https://www.huduser.gov/portal/datasets/fmr/fmr2026/FY26_FMRs.xlsx

The committed extract used that workbook on 2026-10-31. Pass it with `python -m src.lab.acquire --hud-file FY26_FMRs.xlsx` if you refresh the sample. Fair Market Rents are an optional rent cross-check in the Why drawer. They are not a model input: Lab results stay the same when the field is missing.

## How the model is organized

| Path | Role |
| ---- | ---- |
| `config/assumptions.yaml` | Every default, with low / central / high and the state legal shares |
| `src/model/equations.py` | Closed forms (feasibility, hazards, elasticity, walkshed, largest remainder) |
| `src/model/engine.py` | County pro formas, summed to the state; scenario definitions |
| `src/model/sensitivity.py` | Tornado and seeded triangular Monte Carlo |
| `src/model/crossval.py` | Tier-1 extract versus the tier-2 imputation, and versus a state-median screen |
| `src/data/` | Schema, adapter, and the public-data acquisition script |
| `data/sample/` | Small committed benchmark so tests run with no network |
| `src/web/` | Standard-library server and the single-page app |
| `docs/MODEL_AND_ASSUMPTIONS.md` | Equations, calibration, and limits |
| `docs/POLICY_SCENARIO_COMPARISON.md` | Lab comparison (≤4 pages) and the eleven-state core table |
| `docs/SMALL_HOMES_LAB.md` | Lab method: hosts, options, uncertainty, core-engine gap |
| `docs/NH_PORTABILITY.md` | New Hampshire as the lower-data portability test |
| `docs/DATA_PROVENANCE.md` | Sources, vintages, cleaning, and privacy |
| `docs/DISCLOSURES.md` | AI use, prior work, datasets, dependencies, and external services |
| `docs/CASE_STUDY_PA_ALLEGHENY.md` | Allegheny County to Pennsylvania, with observed and imputed inputs separated |
| `docs/sbom.cdx.json` | CycloneDX bill of materials for the direct pins |
| `data/sample/county_points.json` | Census 2024 gazetteer interior points for the eleven states |

## Tests that lock the economics

- Zero policy change produces a zero increment on permits and completions.
- At a zero permit trend, five-year baseline permits are exactly five times the annual run-rate.
- County integer columns sum to the rounded state total.
- Package components sum to the package.
- A higher fee cut, a higher supply elasticity, a higher price, and a higher FAR each raise the outcome they are supposed to move.
- Overlap removes walkshed parcels from missing middle and from parking.
- Dependency licenses stay inside Apache-2.0, MIT, BSD, ISC, and PSF.

## Dependencies

Runtime: Python 3.11+ and PyYAML 6.0.2 (MIT). Tests: pytest 8.3.5 (MIT). Lint: ruff 0.14.2 (MIT). No copyleft packages. The license test fails the build if one appears.

## Prior work

The interaction ideas — a map with drill-down, before-and-after scenario cards, plain language beside the figures, assumption controls with a reset, close-call flags, and a one-page brief — were inspired by PlayHouse, an earlier Pittsburgh parcel explorer by Tejas Chaudhari ([repository](https://github.com/tejaschaudhari131/playhouse), [live site](https://playhouse-pittsburgh.vercel.app)). PlayHouse was written before the challenge coding window, it has no open-source license, and it is not part of this submission. No PlayHouse source, data, or visual asset was copied. Stateframe was written for this challenge and stays at state and county level, with the baseline and the five benchmark reforms. Details are in `docs/DISCLOSURES.md`.

## Security

No secrets are required and none are committed. `.env.example` documents an optional Census key that this pipeline does not use. The web server binds to localhost, refuses unknown routes, and clamps slider overrides to the published band. See `SECURITY.md` and `docs/REPO_SETUP_GUIDE.md` for the GitHub secret-scanning, Dependabot, and CodeQL toggles. The CodeQL workflow in this repo analyzes Python.
