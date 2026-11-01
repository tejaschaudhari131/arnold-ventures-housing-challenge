# Pennsylvania incomplete-data case study: Allegheny County

Prepared for the Arnold Ventures / The Turnout Housing Data and Technology Innovation Challenge by Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns, Carnegie Mellon University.

This note is the incomplete-data case. Pennsylvania has no statewide parcel extract in Stateframe. Allegheny County shows how a county pro forma becomes the state total, and which inputs are observed, assumed, or calculated. The figures below are produced by `src/model/case_study.py` from `data/sample/` and `config/assumptions.yaml`. Re-run the tests to confirm they still match the engine.

PlayHouse, an earlier Pittsburgh parcel explorer, is not a source for this case study. No PlayHouse code, parcel extract, or asset is used. The inputs are public series from the challenge data list.

## 1. One county, then the state

Pennsylvania is a tier-2 state in Stateframe. The public inputs are the American Community Survey, the Building Permits Survey, population estimates, the county gazetteer, and the FHFA house-price index. There is no statewide parcel extract, so lot size is imputed. Allegheny County (604,558 homes, observed) is the county this note walks. The other 66 counties use the same equations. The state total is their sum. The on-screen equation trace still opens on the largest county, which is Philadelphia, because that is where the most homes are. This walkthrough does not use a Pittsburgh parcel file.

Pennsylvania is tier 2 (observed classification in the benchmark). The legal screening note is an assumption: Zoning remains primarily municipal. Statewide ADU or middle-housing preemption is limited, so most single-family parcels are treated as not yet entitled to the benchmark reforms.

## 2. Observed inputs for Allegheny County

Housing units, structure mix, median value ($216,700, observed), median rent ($1,111, observed), income, the pre-1940 share, and the transit-commute share come from ACS 2019–2023 summary tables. Annual permits come from the Building Permits Survey for 2022–2024, about 3,121 units a year (calculated from observed segments) after the county file is reconciled to the state file. Land area and the interior point on the map come from the 2024 Census gazetteer. The state price path comes from the FHFA index. None of these is a modeled household.

| Figure | Value | Tag | Source |
| ------ | ----: | --- | ------ |
| Housing units | 604,558 | observed | ACS 2019–2023 B25001 |
| Single-family detached | 372,149 | observed | ACS 2019–2023 B25024 |
| Single-family attached | 61,508 | observed | ACS 2019–2023 B25024 |
| Median home value | $216,700 | observed | ACS 2019–2023 B25077 |
| Median gross rent | $1,111 | observed | ACS 2019–2023 B25064 |
| Median household income | $76,393 | observed | ACS 2019–2023 B19013 |
| Pre-1940 share of units | 28.2% | observed | ACS 2019–2023 B25034 |
| Public-transit commute share | 6.2% | observed | ACS 2019–2023 B08301 |
| Land area | 730.0 sq mi | observed | Census 2024 county gazetteer |
| Annual single-family permits | 1,297.0 | observed | BPS 2022–2024, reconciled to the state |
| Annual 2-unit permits | 6.7 | observed | BPS 2022–2024, reconciled to the state |
| Annual 3–4 unit permits | 12.7 | observed | BPS 2022–2024, reconciled to the state |
| Annual 5+ unit permits | 1,804.7 | observed | BPS 2022–2024, reconciled to the state |
| Counties in the state sum | 67 | observed | Census geography for Pennsylvania |

County permit segments are the Building Permits Survey. They are scaled so the counties add up to the state permit file. That cleaning step is documented in `docs/DATA_PROVENANCE.md`. The segments stay tagged observed because they are the survey, reconciled, not a policy scenario.

## 3. Assumed, because a parcel extract is not in the model

The lot screen is 89 percent (assumed) in the central case. That number is an assumption: the midpoint of the Connecticut and Wisconsin screening shares, not a measurement of Allegheny lots. The model also assumes that about 15 percent of single-family lots already have the benchmark ADU right, because Pennsylvania has not preempted local zoning. The fee scenario uses a $50,000 stack and a 50 percent cut. Those are challenge comparability assumptions. Construction cost per square foot, the supply elasticity, and the feasibility hurdle are assumptions too. Move the lot-share slider to see only the ADU path change.

| Figure | Central value | Tag | Why it is not a measurement |
| ------ | ------------: | --- | --------------------------- |
| Share of lots that can hold an ADU | 89% | assumed | No Pennsylvania lot-size bins. The central value is the tier-1 screening imputation. |
| Share of lots already allowed an ADU | 15% | assumed | Statewide preemption is limited. This is a legal screen, not an ordinance census. |
| Share of lots already allowed missing middle | 5% | assumed | Same legal screen. |
| Geographically eligible share of the single-family stock | 100% | assumed | No urban-growth or sewer boundary is ingested for Pennsylvania. |
| ADU hard cost | $250 per sq ft | assumed | National cost assumption, indexed by the state's permit valuation. |
| ADU size | 800 sq ft | assumed | Benchmark size. |
| Fee stack in the fee scenario | $50,000 | assumed | Challenge comparability case. Not Allegheny County's fee schedule. |
| Fee cut | 50% | assumed | The benchmark cut. |
| Supply elasticity | 0.80 | assumed | Turns a cost saving into extra baseline permits. |
| Feasibility hurdle | 0.00 | assumed | A site clears when residual margin exceeds this. Central is zero. |

Lot-screen note from the engine: Imputed from the tier-1 screening share. This state has no lot-size extract in the model.

## 4. Calculated county results

Under current rules, Allegheny's rounded five-year baseline is 14,239 completions (calculated). On top of that, the standalone reforms add about 2,894 ADU completions (calculated), 255 missing-middle completions (calculated), 33 transit-oriented completions (calculated), 430 from parking reform (calculated), and 249 from the fee cut (calculated). The package, after overlap, is 4,081 net completions (calculated). Each of those reform figures is calculated. The prices and the stock underneath them are observed. The lot screen and the fee stack underneath them are assumed. Allegheny's margins are not sitting on the feasibility hurdle in the central case.

Integer units use largest-remainder rounding. Tags on this table are calculated.

| Pathway | Allegheny County | Pennsylvania |
| ------- | ---------------: | -----------: |
| Core baseline completions, 5 years | 14,239 | 113,269 |
| ADUs, net | 2,894 | 30,213 |
| Missing middle, net | 255 | 9,613 |
| Transit-oriented density, net | 33 | 612 |
| Parking reform, net | 430 | 1,458 |
| Fee reduction, net | 249 | 1,524 |
| Package, net | 4,081 | 46,219 |

Lab at the Handbook's $50,000 fee: +2,742. Lab at a $6,000 fee: +5,652. Core at a $6,000 fee: +30,213. The same $6,000 fee does not match because the Lab is a county-level model and the core uses a different adoption and valuation model. The Lab's Pennsylvania ADU increment (+2,742) applies the Handbook's $50,000 per-home fee to ADUs. The core Stateframe engine uses its own $6,000 ADU fee and reports +30,213. Walking the Lab toward the core: value the ADU the way a homeowner does — 4.5 percent cap rate, no operating share, rent × 0.85 (+14,392); then drop adoption and build lags (+22,481), within about 26 percent of the core. The Lab numbers answer the Handbook scenarios (Handbook $50,000 per-home fees, county-level model). The core numbers are an eleven-state screening model with a $6,000 ADU fee. Pennsylvania package: Lab +13,285, core +46,219. See the Lab at https://stateframe-housing.vercel.app/lab and the core engine at https://stateframe-housing.vercel.app/. The Lab baseline (113,305) and the core baseline (113,269) differ by +36. Pennsylvania's core permits are the same 2023-2025 county files as the Lab. The Lab pipeline uses the same never-complete shares as the core (0.93/0.90/0.90), including completion_ratio_mf for 5+ homes, so the pipeline baselines match. The residual after the host term is +0. The Lab also adds a +36 host adjustment for already-legal homes the permit window cannot contain yet.

Plain language for the state package:

Combined package adds about 46,219 (calculated) net completions in Pennsylvania over five years, 40.8 percent (calculated) above the baseline of 113,269 (calculated). After the reform, five-year completions are about 159,488 (calculated). The worked example is Philadelphia County. The package removes overlap among the reforms that are switched on. It is not the sum of the five standalone totals. Best use is chosen at county level: inside a transit walkshed the county takes the larger of the TOD path and the path without that TOD claim.

## 5. The sum is the result

Largest-remainder rounding forces the county integers to add up to the rounded state total. Baseline completions: the counties sum to 113,269, and the rounded state total is 113,269. Package net completions: the counties sum to 46,219, and the rounded state total is 46,219. Allegheny County is 8.8 percent of that package. The unrounded state package is 46,219 net completions over five years. A single pro forma at Pennsylvania's median price would not reproduce that total, because feasibility is curved. That is why the official result is the sum.

Counties sum to the rounded state total: true.

## 6. What is still missing

A public lot-size extract for Pennsylvania would retag the lot screen from assumed to calculated-from-observed-bins, the way Connecticut and Wisconsin already work. It would not replace the ACS prices, the permit run-rate, or the rule that counties sum to the state. It would also not turn the $50,000 fee stack into a measurement. Until that extract is in the benchmark, completeness stays below the tier-1 states and this page is the incomplete-data case: the same equations, with the missing field labeled instead of invented.

## Provenance

| Tag | Meaning |
| --- | ------- |
| observed | Measured in a public dataset from the official data list and stored for this place. |
| assumed | A published assumption or an imputation. It is not a measurement for this place. |
| calculated | Arithmetic in src/model/equations.py, using observed inputs and published assumptions. |

Sources, all on the official data list: ACS 2019–2023 5-year summary file; Building Permits Survey annual state and county files, 2022–2024; Census population estimates NST-EST2024; Census 2024 county gazetteer; FHFA All-Transactions state house-price index. Licenses and vintages are in `docs/DATA_PROVENANCE.md`.
