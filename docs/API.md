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
- Two or three reforms return HTTP 200. Eligible and feasible in that JSON are the sum of those reforms, and the note says lots may overlap. The likely range is not computed for that mix. The illustrative options use the fee cut, parking minimums, and ADU parking rule from every selected reform together, so the list order does not change `.options`.
- One reform, or all four, uses that scenario or the package.
- An id outside `adu`, `missing_middle`, `parking`, and `fees` returns HTTP 400 with `Unknown reform.` The id is not dropped and is not repeated in the body. The same 400 applies to the brief and the county CSV.
- A repeated id returns HTTP 400 with `Duplicate reform.` It is not counted twice, and it is not dropped. The same 400 applies to the brief and the county CSV.
- The four ids in any order are the package. A shorter unique list is a custom mix.

## `POST /api/lab/export`

`format` is `md`, `html`, or `csv`. `reforms` is the same list. For zero, two, or three reforms the county CSV leaves p10, p90, and the zoning columns blank and sets `range_role` to `Reference range (defaults) not computed for this mix`. Those cells are not filled with baseline numbers.

A two- or three-reform file does not use the columns `eligible` and `feasible`. It uses `eligible_sum_of_reforms` and `feasible_sum_of_reforms`, because adding those counts double-counts lots that appear in more than one reform. Each data row sets `basis` to `sum of per-reform counts; lots may overlap; not a joint count` and `central_basis` to `simple sum of standalone results, not modelled jointly`. `close_call_top_benchmark` is `not computed for mix`, not `no`. The file starts with that header row. There is no comment line above it. An empty selection leaves the count cells blank and sets `central_basis` to `no reforms selected`.
