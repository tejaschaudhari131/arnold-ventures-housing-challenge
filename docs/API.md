# HTTP API

The app is a fixed set of routes on the standard-library server (`src/web/server.py`). Nothing the client sends is joined onto a filesystem path.

## `POST /api/sensitivity` and `POST /api/crossval`

`draws` is optional.

- Omit `draws` and the server uses its default (80 for sensitivity, 40 for cross-check).
- A JSON integer inside the allowed range is used as given. Sensitivity allows 20–400. Cross-check allows 20–200.
- `draws: null` is not the default. It returns HTTP 400 with `draws must be an integer from 20 to 400.` on sensitivity, and `from 20 to 200` on cross-check.
- The same 400 is returned for non-integers and for strings that are not ASCII digits. That includes `²`, Arabic-Indic `٢٠`, `""`, `" 20"`, `"1e2"`, and `true`. The body does not repeat the rejected value.

## `POST /api/lab/why`

`scenario` may be one published Lab scenario, or `selection` together with `reforms`, a list of `adu`, `missing_middle`, `parking`, and `fees`.

- An empty list returns HTTP 200 and `empty: true`. Extra homes are 0. It does not explain the baseline as if a reform were selected.
- Two or three reforms return HTTP 200. Eligible and feasible are the sum of those reforms. The likely range is not computed for that mix.
- One reform, or all four, uses that scenario or the package.

## `POST /api/lab/export`

`format` is `md`, `html`, or `csv`. `reforms` is the same list. For zero, two, or three reforms the county CSV leaves p10, p90, and the zoning columns blank and sets `range_role` to `Reference range (defaults) not computed for this mix`. Those cells are not filled with baseline numbers.
