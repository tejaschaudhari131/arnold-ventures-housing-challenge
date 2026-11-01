# Defect register

Reproduced against main `8952914` unless noted. Prod checks are from `https://stateframe-housing.vercel.app` at `308e336`.

Status words: reproducing, fixed on main, fixed here, only on PR #22 (now merged, so fixed on main), still open.

| ID | Severity | Where | Status on prod `308e336` | Status on main `8952914` before this branch | Status on this branch |
| --- | --- | --- | --- | --- | --- |
| 1 | High | Screening export | Reproducing | Reproducing | Fixed here |
| 2 | High | Lab recompute ranges | Reproducing | Reproducing | Fixed here |
| 3 | High | Lab URL | Reproducing | Reproducing | Fixed here |
| 4 | High | Lab packages | Reproducing | Reproducing | Still open (Phase 4) |
| 5 | Medium | Docs link | Reproducing (HTTP 404; page linked to GitHub) | Reproducing | Fixed here |
| 6 | High | Two engines | Reproducing | Reproducing | Still open (Phase 4) |
| 7 | Medium | Sensitivity | Reproducing | Reproducing | Fixed here |
| 8 | High | Acquisition | Was reproducing at `a8f1bac` | Fixed on main (PR #21) | Still fixed; redirect check added |
| 9 | Medium | Capacity labels | Reproducing | Partly fixed on main (PR #22 labels) | Basis label added. Economics still open |
| 10 | Medium | SBOM | Reproducing | Reproducing | Fixed here |
| X1 | High | Lab brief and county CSV | Reproducing | Reproducing | Fixed here |

## 1. Export ignores the custom mix

- Impact: a policymaker can download a different package from the one on screen.
- Steps: turn ADU off. The package headline is 27,243. Download JSON.
- Expected: the file's package completions match the screen.
- Observed on prod and on main: the client sent only `state` and `format` (`app.js` download). The server reran defaults, so the file said about 74,114.
- Location: `src/web/static/app.js` download; `App.export`; `src/export/report.py` `simulate_many`.
- Fix: POST the active overrides and reform mix. Default GET export is unchanged.
- Regression: `tests/test_phase1_behavior.py::test_custom_export_matches_the_on_screen_scenario`.
- Owner: this branch.

## 2. Lab recompute shows dashes

- Impact: after one assumption change the likely range looks missing, and a false Outcome uncertain badge appears.
- Steps: set `hazard_homeowner_feasible` to 0.0062 and recompute.
- Expected: a real conditional p10/p90, or an explicit reference or unavailable state. Never a dash. No Outcome uncertain badge from a missing range.
- Observed: `_layer_row` omitted p10/p90. `integer(undefined)` rendered an em dash. `row.p10 > 0` was false, so the badge appeared.
- Location: `src/lab/explain.py` recompute; `src/web/static/lab.js` `describeRange`, `outcomeBadgeHtml`.
- Fix: attach the locked p10/p90 with `interval_status: "reference"` and the label `Reference range (defaults)`. Hide the outcome badge for that reference.
- Regression: `test_lab_recompute_labels_the_reference_range_and_the_brief`.
- Owner: this branch. A conditional recompute of the 2,000-draw envelope is Phase 5.

## 3. Lab URL drops overrides and empty selections

- Impact: reload restores about 6,404 (missing middle) instead of the shared view.
- Steps: clear every reform, or set an override, then copy the URL into a clean load.
- Expected: empty stays empty and the increment is 0. Overrides come back.
- Observed: `parseUrl` treated an empty `on` as missing and added missing middle. Overrides were not written.
- Location: `src/web/static/lab.js` `parseUrl`, `writeUrl`, `loadAll`.
- Fix: `on=none` is empty. `ov=name:value` round-trips and triggers recompute.
- Regression: `node tests/js/lab_roundtrip.mjs` via `test_lab_url_round_trip_keeps_an_empty_selection`.
- Owner: this branch.

## 4. Packages are sums

- Impact: ADU+MM is described as about 12,021 when the joint legalization run is 8,543.9.
- Steps: turn on ADU and missing middle only. Read `package_decomposition` on the PA Lab state.
- Expected: a resolver over every subset, with uncertainty for that selection.
- Observed: `legalization_resolved` 8,543.9 vs `legalization_if_summed` 12,021.0. The UI says "simple sum, not modeled".
- Location: `src/lab/engine.py` `package_decomposition`; `src/web/static/lab.js` partial-package branch.
- Fix: not in this PR. Phase 4. Recorded in `tests/fixtures/characterization.json` with `"defect": 4`.
- Owner: Phase 4.

## 5. Methods doc 404

- Impact: the methods link does not open on Vercel.
- Steps: `GET /docs/SMALL_HOMES_LAB.md` and `GET /docs/DATA_PROVENANCE.md`.
- Expected: the markdown, not `{"error":"Not found"}`.
- Observed on prod `308e336`: HTTP 404. The rendered Lab page pointed at GitHub. Confirmed with curl on 2026-11-01.
- Location: `src/web/server.py` route map; `vercel.json` `includeFiles`; `lab.html`.
- Fix: serve `docs/*.md` as text. The Lab link is `/docs/SMALL_HOMES_LAB.md`.
- Regression: `test_bad_requests_are_400_and_do_not_echo_input` and `test_completion_ratio_slider_changes_the_headline` (provenance doc).
- Owner: this branch.

## 6. The engines are not interchangeable

- Impact: a reader can treat 46,261 and 5,617 as the same ADU answer.
- Steps: compare screening PA ADU incremental completions with Lab PA ADU central, and the baselines.
- Expected: one explained residual, or two labeled profiles.
- Observed: screening ADU about 46,261.1 vs Lab 5,617.3. Baselines about 108,950.1 vs 111,060.9. A $6k Lab fee is not the whole gap (already stated on the page).
- Location: `src/model/engine.py` and `src/lab/engine.py`. Narrative is in `docs/SMALL_HOMES_LAB.md`.
- Fix: not in this PR. Phase 4 reconciliation report. Do not retune either model here.
- Owner: Phase 4.

## 7. Sensitivity ignores the current scenario

- Impact: the tornado can answer a different question than the headline.
- Steps: open Sensitivity. The request used `scenarioId`, which starts as `adu`, and did not send overrides or the reform mix.
- Expected: the active package, including overrides and the reform mix.
- Observed: hardcoded path through scenario `adu` / 80 draws.
- Location: `src/web/static/app.js`; `App.sensitivity`; `src/model/sensitivity.py`.
- Fix: the request sends `scenario: "combined"`, the active overrides, and the reform mix. The completion-ratio slider is wired through `simulate()`. Moving multifamily `completion_ratio_mf` from 0.70 to 0.93 changes both the baseline and the package headline (103,874 vs 112,214 baseline; 73,105 vs 74,763 package, rounded).
- Regression: `test_sensitivity_uses_the_current_reform_mix` and `test_completion_ratio_slider_changes_the_headline`.
- Owner: this branch.

## 8. Acquisition unpack and fallback

- Impact: a gazetteer refresh crashed and the shell kept going only for exit code 2.
- Steps: three-county gazetteer fixture; `land, points = load_land()` after `_bind_names`.
- Expected: a `(land, points)` pair, and any failure leaves `data/sample/` in place.
- Observed at `a8f1bac`: `load_land_with_names` returned only the land dict. `scripts/get_data.sh` treated only exit 2 as fallback.
- Location: `src/data/acquire.py`, `scripts/get_data.sh`.
- Fix on main: PR #21. `tests/test_acquire_fallback.py` covers the unpack, exit 2, and any nonzero shell exit.
- This branch: downloads must be HTTPS and the host is checked again after a redirect (`src/data/safe_url.py`).
- Owner: PR #21 for the unpack; this branch for the redirect contract.

## 9. Capacity accounting and labels

- Impact: "capacity" was read as the same kind of number on every row.
- Steps: read `capacity_completions` on the PA baseline row and on a reform row.
- Expected: a label, or one meaning. Do not change incremental results in this phase.
- Observed now: baseline capacity is the five-year level (about 108,950). Reform capacity is an increment. Package capacity is about 75,780.7 against package incremental completions of about 74,114.5. PR #22 shows uncapped potential and the binding absorption cap. Hawaii's absorption cap is about 0.14, which the UI was rounding to "cap is 0".
- Location: `src/model/engine.py` `_scenario_shell`; `src/web/static/app.js` cap note.
- Fix here: `capacity_completions_basis` is `level` or `increment`. The cap sentence is hidden when the cap rounds to 0. No incremental number changes.
- Economics of why package capacity and the capped total differ: Phase 4.
- Regression: `tests/test_characterization.py`.
- Owner: labels here; economics Phase 4.

## 10. SBOM covers only direct pins

- Impact: transitive dev packages were invisible to the license check.
- Steps: read `docs/sbom.cdx.json` and `tests/test_licenses.py` on main.
- Expected: a resolved app SBOM and a resolved dev SBOM, with licenses.
- Observed: PyYAML, pytest, and ruff only.
- Fix: `src/sbom.py` walks the installed tree. PyYAML is `required`. pytest, ruff, pluggy, iniconfig, and packaging are `optional`.
- Regression: `tests/test_licenses.py`, `tests/test_lab_docs.py`.
- Owner: this branch.

## X1. Brief and county CSV mix live centrals with a stale range

- Impact: the brief can show a central outside its unlabeled range, and the "flips if" text can describe a different ranking.
- Steps: recompute PA with `hazard_homeowner_feasible=0.0062`. Export the brief and the county CSV.
- Expected: conditional ranges, or the words "reference range at default settings", and ranking text that matches the live order.
- Observed: missing middle central about +13,298 with locked range 1,942–10,871. 24 of 469 CSV rows had the central outside the range. Allegheny missing middle 876.9 vs 84.1–841.7.
- Location: `brief_markdown`, `county_csv`.
- Fix: the range column is labeled `Reference range (defaults)` when the run is live. The live order is stated separately from the default-settings switches. CSV column `range_role` is `reference_at_default_settings`.
- Regression: `test_lab_recompute_labels_the_reference_range_and_the_brief`.
- Owner: this branch.

## Security items

| ID | Observed | Fix | Test |
| --- | --- | --- | --- |
| S1 | NaN override on `/api/simulate` returned 500 (`float('nan')` passed the band check) | 400, finite required | `test_bad_requests_are_400_and_do_not_echo_input` |
| S2 | Lab clamped NaN/Inf | 400 | same |
| S3 | `draws` of a non-number or a non-finite value, and a non-numeric Content-Length, returned 500 | 400 | same |
| S4 | No CSP or Permissions-Policy | Both headers. Styles may be inline because the pages set `style` from `innerHTML`. Scripts are same-origin only | same |
| S5 | Redirects were not re-checked | HTTPS plus allowlist on the initial URL and on redirects | `test_downloads_reject_http_and_off_list_redirects` |
| S6 | Unknown county on `/api/lab/why` returned 500 | 400, and the name is not echoed | bad-request test |
| S7 | CSV could carry a formula | `csv_cell` quotes `=`, `+`, `-`, `@` text that is not a plain number | `test_csv_formula_cells_are_quoted_and_numbers_stay_numbers` |
| S9 | `lab-results.yml` interpolated `inputs.states` into the shell | Passed as `LAB_STATES` and quoted. Unknown codes exit without echoing the raw value | workflow file |
| Stamp | Footer could show `garbage`, ignore the stamp SHA, or use HEAD's date for an unknown SHA | Dates must be real `YYYY-MM-DD`. Stamp SHA is used when env and git are absent. An unknown SHA does not inherit HEAD's date | `tests/test_version_stamp.py` |
| Health | No model version | `model_version` `1.0.0`, `model_date` `2026-10-25` (fixture access date) | `tests/test_http.py` |

## Browser follow-ups in this branch

| Item | Fix |
| --- | --- |
| Header overflow at 768px and white tour text on the page background | `.sf-top` wraps. The tour button keeps a navy fill and white text. |
| Sticky total covers the skip link | Skip-link z-index 40, and on the Lab it sits below the bar. |
| Zero reforms showed 2–6 homes on the map, table, and county line | Empty selection is 0. Two reforms show the simple sum of both, labeled not modeled. |
| NH fee note kept PA figures | The note is replaced from `/api/adu-compare?state=` for the state on screen. |
| Lab brief omitted the selection | The POST sends `reforms` and `overrides`. |
| Raw fetch errors | Plain sentence and a Retry button. |
| Try Pennsylvania while PA is showing | The button is hidden. |
| Slider labels rounding 0.9875 to 1 | Two or three fraction digits for non-integers under 10. |
| Table and Chart tabs | Only `aria-selected` is set, and only the open tab is true. |
| Tour covered the map caption | The tour sits on the left, under the legend's stacking order. |

## Proposed Phase 4 plan (not started)

1. Define a package as one scenario spec over a subset of reforms, not a sum of standalone runs.
2. Run every non-empty subset (16 for the four Lab bills; 32 if approval is included) with the same draws, and aggregate counties inside each draw.
3. Publish an ordered decomposition that sums to the package, with the empty package equal to 0.
4. Write a reconciliation report for screening vs Lab: vintage, hosts, fee, uptake, timing, and the residual. Keep two profiles until a component is actually the same equation.
5. Only then decide whether package capacity and the capped total need an economics change. Until then the basis label and PR #22's uncapped-potential wording stand.
