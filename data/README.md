# Data

Do not commit raw or large extracts. `.gitignore` ignores `data/` except this file and `data/sample/`.

## How to obtain the data

From a clean checkout, with or without a network:

```bash
bash scripts/get_data.sh
```

With a network, `python -m src.data.acquire` streams public files from `www2.census.gov` and `www.fhfa.gov` and writes `data/cache/fixtures.json`. It does not call the Census API, so `CENSUS_API_KEY` is optional and unused. If a download fails, the command exits 0 and the app keeps the committed benchmark in `data/sample/`.

The tier-1 lot-size bins and the transit inventory are screened aggregates already in `data/sample/`. Acquisition merges those files. It does not re-download parcel geometries. The same gazetteer download that supplies land area also writes county interior points to `data/cache/county_points.json`. Re-screening instructions and the query hosts are in [docs/DATA_PROVENANCE.md](../docs/DATA_PROVENANCE.md).

## Sample data

`data/sample/` is the benchmark tests, CI, and the web app run against. See [data/sample/README.md](sample/README.md). The files are a few hundred kilobytes of JSON. No CSV or parcel dump is committed.

## Provenance

Source, vintage, license, and cleaning for every series are in [docs/DATA_PROVENANCE.md](../docs/DATA_PROVENANCE.md). The challenge's state-by-state catalog is in [data/DATA_SOURCES.md](DATA_SOURCES.md).
