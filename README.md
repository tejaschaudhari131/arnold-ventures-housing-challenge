# Stateframe

A transparent, replicable simulator of state housing reforms for the [Arnold Ventures / The Turnout Housing Data and Technology Innovation Challenge](https://housingchallenge.turnout.rocks/).

Stateframe compares a calibrated baseline with five benchmark reforms, plus a combined package, over a five-year horizon. It covers all eleven states in the official data list: Pennsylvania, Connecticut, Wisconsin, Utah, Oregon, Hawaii, Arizona, Virginia, Tennessee, Rhode Island, and New Hampshire. The arithmetic is structural and inspectable. Assumptions live in `config/assumptions.yaml`. Equations live in `src/model/equations.py`. Nothing in the runtime is a machine-learning model.

**Authors:** Tejas Chaudhari (tchaudha@andrew.cmu.edu), Yoon Yik Ng (yoonyikn@andrew.cmu.edu), and Christopher Severns (cseverns@andrew.cmu.edu), Carnegie Mellon University.

**License:** [Apache-2.0](LICENSE).

## What you can do with it

- Compare baseline permits and completions with ADUs, missing middle, transit-oriented density, parking reform, and a 50 percent fee cut.
- Move any published assumption inside its low-to-high band and recalculate.
- Open "Show the math" for the selected state and scenario, with the numbers substituted.
- Read a tornado chart and a seeded Monte Carlo band.
- Check that county rows sum to the state.
- Run the tier-1 states through the incomplete-data estimator and see the error.
- Export CSV, JSON, and Markdown.

## Command contract

From a clean checkout:

```bash
bash scripts/setup.sh    # creates .venv and installs pinned dependencies
bash scripts/test.sh     # compile, pytest, and ruff
bash scripts/run.sh      # web app at http://127.0.0.1:8080
bash scripts/get_data.sh # optional refresh; works offline (keeps data/sample)
```

The same three targets exist in the `Makefile` (`make setup`, `make test`, `make run`). CI (`.github/workflows/ci.yml`) runs `scripts/setup.sh` and `scripts/test.sh`.

Write the comparison files instead of starting the server:

```bash
bash scripts/run.sh report --out output
# output/comparison.csv, comparison.json, comparison.md
```

One state, from the command line after setup:

```bash
PYTHONPATH=. .venv/bin/python -m src.cli run --state PA --out output
```

`scripts/get_data.sh` streams Census ACS, Building Permits Survey, population estimates, the county gazetteer, and the FHFA state house-price index. It does not need an API key. If the download fails, it prints a fallback message and exits 0 so CI and offline checkouts keep using `data/sample/`.

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
| `docs/POLICY_SCENARIO_COMPARISON.md` | The eleven-state results table and how to read it |
| `docs/DATA_PROVENANCE.md` | Sources, vintages, cleaning, and privacy |
| `docs/DISCLOSURES.md` | AI use, dependencies, and external services |
| `docs/sbom.cdx.json` | CycloneDX bill of materials for the direct pins |

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

## Security

No secrets are required and none are committed. `.env.example` documents an optional Census key that this pipeline does not use. The web server binds to localhost, refuses unknown routes, and clamps slider overrides to the published band. See `SECURITY.md` and `docs/REPO_SETUP_GUIDE.md` for the GitHub secret-scanning, Dependabot, and CodeQL toggles. The CodeQL workflow in this repo analyzes Python.
