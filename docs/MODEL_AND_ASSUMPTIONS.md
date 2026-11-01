# Model and Assumptions Overview

Stateframe is a state-level housing policy simulator for the Arnold Ventures / The Turnout Housing Data and Technology Innovation Challenge. Authors: Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns, Carnegie Mellon University. License: Apache-2.0.

The model is a set of closed-form equations in `src/model/equations.py`, applied county by county in `src/model/engine.py`, with every default in `config/assumptions.yaml`. There is no fitted machine-learning model, no pretrained weight, and no lookup of a precomputed grid. The web app posts the current sliders to the same function the tests call.

## 1. Question and outcome

The question is: if a state adopted one of the five benchmark reforms, or the package of all five, how many additional homes would be permitted and completed over five years, relative to continuing the recent production run-rate?

For each state and scenario the engine reports:

- Permits issued over five years (the level, baseline plus the increment).
- Units completed and added to stock over five years.
- The increment over baseline, the annualized rate (increment divided by 5; for the baseline, the level divided by 5), and the percent lift of completions over baseline.

Net completions subtract a demolished home when a teardown or a transit-oriented rebuild replaces it. Permits count every unit in the new building, including replacements, and only when the reform is what induces the building. A transit reform that does not raise floor-area ratio induces nothing.

The official state total is the sum of county results. Feasibility is a curved function of the price-to-cost margin, so a pro forma at the state median is not the average of the county pro formas. The state-median screen exists only as a cross-check (`resolution="state"`).

## 2. Two-tier data architecture

All eleven challenge states run through one schema (`src/data/schema.py`) and one adapter (`src/data/adapters.py`). A new state is a JSON document with the same keys.

**Tier 1, statewide or urban-county parcel or land-use extract.** Connecticut (CAMA lot-size bins), Wisconsin (statewide residential parcel bins), Utah (Housing Unit Inventory mean lot size on urban counties), Hawaii (State Land Use district acres). Observed bins or the lognormal tail replace the imputed lot-feasibility share.

**Tier 2, Census and permits, with parcel fields imputed.** Pennsylvania, Oregon, Virginia, Arizona, Tennessee, Rhode Island, New Hampshire. Every county still has ACS prices, structure, tenure, and a Building Permits Survey cell reconciled to the state total. What is missing is a lot-size distribution and a statewide zoning layer. Pennsylvania's PASDA county portals (Allegheny, Philadelphia, Montgomery, and others) are the natural next adapter. This build does not invent parcel statistics for them. The completeness score records that gap: 0.35 ACS, 0.20 state permits, 0.15 county-permit coverage, 0.20 a tier-1 parcel or land-use observation, 0.10 lot-size bins. Connecticut and Wisconsin score 1.00. Utah scores 0.90 (mean lot, no bins). Hawaii scores 0.87. The tier-2 states score about 0.69 to 0.70, which is full Census and permit coverage and no parcel extract.

**Cross-validation.** On Connecticut, Wisconsin, Utah, and Hawaii the app can hide the parcel extract (`parcel_mode="imputed"`) and, separately, collapse counties to the state median. Section 10 reports the errors. The point of the mode is to show a policymaker how much the answer moves when the rich file is absent.

## 3. Baseline

Let \(B_s\) be the 2022–2024 average annual permits in segment \(s\) (single-family, 2–4 units, 5+ units). Over \(T = 5\) years at annual trend \(g\),

\[
H(g, T) = \begin{cases} T & \text{if } g = 0 \\ \dfrac{(1+g)^T - 1}{g} & \text{otherwise.} \end{cases}
\]

Central \(g\) is 0, so five-year permits equal \(5 \times\) the annual run-rate exactly. That identity is tested. Completions in a segment equal permits times a completion ratio (central 0.93 single-family, 0.90 small buildings, 0.84 multifamily, 0.92 ADUs). The ratios are a steady-pipeline identity: homes permitted just before the window finish during it, and homes permitted at the end of the window finish after it. What the ratio removes is cancellation and the longer multifamily schedule, not a construction-duration model of each project.

The Lab baseline (111,016) and the core baseline (108,950) use the same completion shares (0.93/0.90/0.84) and the same 5-year window. The Lab uses the 2023-2025 permit average and the core uses 2022-2024. That moves Pennsylvania by +1,988, mostly from 5+ unit permits (+2,170). The Lab also adds a +78 host adjustment for already-legal homes.

County permit cells are reconciled to the state Building Permits Survey total. Counties present in the county file keep their counts. Any residual is spread to non-reporting counties by housing-unit weight. If the reporting counties already exceed the state, they are scaled down. After reconciliation, county permits sum to the state total.

## 4. Shared building blocks

All of these are functions in `src/model/equations.py`.

**Margin.** \((V - C) / C\). A non-positive cost returns a large negative margin only when value is also negative; a zero cost with non-negative value returns 0.

**Feasibility share.** \(\Phi((m - m^\star) / \sigma)\), where \(\Phi\) is the standard normal CDF via `math.erf`, \(m^\star\) is the hurdle (central 0), and \(\sigma\) is cross-site dispersion of the margin (central 0.22). A site at a zero margin is a coin flip. The normal CDF is a distribution of sites, not a statistical fit to a particular state's historical response.

**Homeowner or merchant value.** Gross rent capitalization is \(\text{rent} \times 12 \times (1 - \text{opex}) / \text{cap rate}\). Sale value per unit is \((\text{median value} / 1{,}800) \times \text{premium} \times \text{unit size}\), with central premium 1.10.

**Cost shock on an existing pipeline.** \(dQ = Q \cdot \varepsilon \cdot (\text{savings} / \text{cost base})\), central \(\varepsilon = 0.80\) (band 0.35 to 1.60). Land is not in the cost base. Land is the residual the pro forma already tests.

**Integer counties.** Hamilton's largest-remainder method turns county weights into integers that sum exactly to the rounded state total. The county table in the app is that allocation. Adding the column recovers the state.

**Context.** A county is urban above 1,500 homes per square mile or a transit-commute share of 6 percent, suburban above 200 homes per square mile, and rural otherwise (core engine; the Lab uses 2,000 per config/lab/assumptions.yaml:27). Parking minimums, market ratios, and the surface-versus-structured mix depend on that label.

## 5. Scenario 1 — accessory dwelling units

The benchmark allows one detached or semi-detached ADU of at least 600 square feet on a lot with an existing single-family building, with no additional parking.

Eligible homes =

\[
(\text{detached} + 0.35 \times \text{attached}) \times \text{geography} \times (1 - \text{already legal}) \times \text{tenure} \times \text{lot feasibility}.
\]

Tenure weights owners at 0.90 and landlords at 0.40 of the occupied mix. Lot feasibility is the share of lots of at least 5,000 square feet (semi-detached). Where bins exist, the share interpolates inside the cutoff bin. Utah has a mean (22,218 square feet) and no bins, so the share is the lognormal tail at \(\sigma_{\ln} = 0.70\). Tier-2 states use the imputed share 0.89, the midpoint of the Connecticut and Wisconsin screens. The central prototype is 800 square feet, not the 600 square foot minimum.

Cost is hard cost per square foot (central $250) times the state's single-family cost index, plus 12 percent soft cost, plus a $6,000 fee. Parking cost is $0 because the benchmark includes the waiver. Value is the maximum of the homeowner gross yield (rent scaled by 0.85, cap rate 4.5 percent, no operating-expense ratio, no developer profit) and the sale value of the square feet.

Annual adoption hazard is \(\min(0.06,\ 0.004 \times e^{1.2 \times \text{margin}})\). The five-year share is \(1 - e^{-\text{hazard} \times 5}\). Permits are eligible homes times that share, then capped at 4.5 percent of eligible homes so the central hazard does not silently hit a ceiling. The high hazard band does hit it in some states. Completions apply the 0.92 ADU ratio.

Already-legal shares, central: Pennsylvania 0.15, Connecticut 0.75 (Public Act 21-29; the result is the residual gap), Wisconsin 0.10, Utah 0.35, Oregon 0.70, Hawaii 0.40, Arizona 0.25, Virginia 0.20, Tennessee 0.15, Rhode Island 0.30, New Hampshire 0.45 (RSA 674:72). These are assumptions with low/high bands, not a measurement of each ordinance.

## 6. Scenario 2 — missing middle

Parcels now limited to one house may hold 2 to 6 units, up to 3 stories. The benchmark says setbacks and lot coverage do not further constrain that building, so lot size is not a second screen here.

Two pathways:

1. **Teardown** of an obsolete slice of the pre-1940 stock (central 20 percent of that stock, times the legal gap). Opportunity cost is 40 percent of the county median, not the whole house. Revenue is the sale or rent value of an expected 4 units of 1,050 square feet at $225 per square foot Type V-B, indexed, plus soft costs, a $25,000 fee, mandated parking, demolition, and a 15 percent profit on hard plus soft. Net units per parcel are expected units minus one. In most counties this margin is negative. The model says so.

2. **Conversion** keeps the house and adds 1.5 units of 900 square feet at $165,000 per unit before the cost index. The eligible pool is 14 percent of single-family homes in the legal gap, minus parcels already counted as teardowns. This is where near-term units come from.

Both pathways are paced by a cumulative hazard (central annual pace 0.08). Completions use the small-building ratio. A county absorption cap then binds: net merchant completions cannot exceed the maximum of (baseline county completions × absorption ratio) and (housing stock × 0.002 × absorption ratio). Central absorption ratio is 0.75. Standalone, missing middle may use the whole cap. In the package it shares the cap with transit-oriented rebuilds.

## 7. Scenario 3 — transit-oriented density

Major transit stops are defined in `data/sample/transit_inventory.json` and justified as follows. A major stop is a local fixed-guideway station (heavy rail, light rail, commuter rail, streetcar) or a bus-rapid-transit station, or a stop on a bus corridor with scheduled headway of 15 minutes or better. Intercity Amtrak-only stops are excluded. New Hampshire has zero rail and zero BRT stations under that definition, so its transit scenario is about 8 completions. Downeaster stops are intercity and are not reclassified to manufacture a result.

Walkshed area is

\[
\left(n_{\text{rail+BRT}}\pi r^2 + \text{bus miles} \times 2 b\right) \times (1 - \text{overlap}).
\]

Central \(r = 0.50\) miles and \(b = 0.25\) miles. Both are sliders, so the 0.25-mile and 0.50-mile cases are both in the published band. Overlap is a screened factor (0.42 in Pennsylvania, 0.05 in New Hampshire), not a geometric union of polygons. Homes in the shed equal area times 4,500 units per square mile, allocated across counties by transit-commute share times housing units, and capped at each county's stock. `tod_station_scale` (central 1.0) is the inventory uncertainty.

Eighteen percent of walkshed homes are redevelopment candidates. The replacement building uses a podium cost of $325 per square foot times the multifamily cost index, a $40,000 fee, parking at 0.25 spaces (the reduced transit ratio, not the citywide minimum), and a 12 percent transit price premium. Net new units per rebuilt home are \(\text{FAR}_{\text{policy}} / \text{FAR}_{\text{existing}} - 1\). Central FAR goes from 1.3 to 3.5. If that ratio is 1, rebuilt homes are zero: the reform did not change the envelope. Gross permits, when the envelope does rise, are rebuilt homes times (net per home + 1), because replacements are permitted too. Completions are the net times the multifamily ratio, then the absorption cap.

## 8. Scenario 4 — parking

The mandate falls to a market ratio that is still below the mandate and depends on context. Central minimums are 1.25 urban, 1.75 suburban, 2.00 rural. Central market ratios are 0.70, 1.25, and 1.70. The market ratio is capped at the minimum, so a slider cannot invent a mandate that is looser than the market.

Space cost is a surface stall (central $8,500) times the cost index, except in urban counties, where 60 percent of stalls are structured at $35,000. Underground ($55,000) is in the file as a high-cost reference and is not the central urban mix. Savings per unit are \((p_{\min} - p_{\text{mkt}}) \times\) space cost. That saving shifts the baseline pipeline through the supply elasticity. A second channel unlocks units on footprint-constrained sites: freed area is spaces saved times 325 square feet, divided by the area the market-parking project still needs, times the constrained share (0.45 urban, 0.18 suburban, 0.05 rural; single-family uses a quarter of that share, small buildings 60 percent). The yield fraction is capped at 1.5.

## 9. Scenario 5 — fees

The challenge comparison case sets baseline fees at $50,000 per unit and cuts them by 50 percent, a $25,000 direct reduction. The cut applies to the baseline pipeline in every segment. The denominator of the percent cost change is hard cost plus soft cost plus mandated parking plus the $50,000 stack, so states are comparable even though the zoning pro formas use lower segment fees ($6,000 ADU, $15,000 single-family, $25,000 missing middle, $40,000 podium). The $50,000 figure is not a claim that any of these states charges $50,000 today. The reduction fraction slider runs from 25 percent to 75 percent. A zero cut is the neutral-policy identity, not a slider position.

## 10. Package, overlap, and the cross-check

The package applies the fee cut inside the zoning pro formas and lets missing-middle parking fall to the market ratio. It then removes double-counted parcels, county by county:

- Transit-oriented rebuilds keep the walkshed.
- Missing middle is scaled by the share of homes outside the walkshed.
- ADUs are scaled by the single-family homes not consumed by those two pathways.
- Parking yield inside the walkshed is dropped, because the podium pro forma already used the reduced parking ratio.
- The fee increment on the baseline pipeline is kept. Those projects were legal without the zoning reforms.

Missing middle and transit then share one absorption cap. The five components sum to the package. Because the zoning pro formas get cheaper under the fee and parking pieces, the package can exceed the sum of the five reforms run alone. That is synergy inside a project, not the same parcel counted twice. The identity test checks the component sum. A separate test of the overlap rule, with packaged economics equal to standalone economics, checks that missing middle and parking fall when the walkshed is non-empty.

**Neutral policy.** Setting already-legal shares to 1, policy FAR equal to existing FAR, market parking equal to the minimum, the fee cut to 0, and the transit parking ratio equal to the urban minimum produces an increment of exactly 0 on permits and completions. Tested on Pennsylvania.

**Tier-1 versus tier-2, central case, five-year incremental completions.**

| State | Screen | ADUs | Missing middle | TOD | Package |
| ----- | ------ | ---: | -------------: | --: | ------: |
| CT | Full | 3,077 | 4,813 | 2,514 | 11,033 |
| CT | Hidden parcels | 2,856 (−7.2%) | 4,813 (0) | 2,514 (0) | 10,812 (−2.0%) |
| CT | State median | 2,694 (−12%) | 1,524 (−68%) | 359 (−86%) | 7,446 (−33%) |
| WI | Full | 15,846 | 1,798 | 56 | 25,445 |
| WI | Hidden parcels | 16,002 (+1.0%) | 1,798 | 56 | 25,602 (+0.6%) |
| WI | State median | 16,246 | 693 (−61%) | 24 (−56%) | 23,420 (−8%) |
| UT | Full | 8,576 | 10,300 | 1,091 | 27,809 |
| UT | Hidden parcels | 7,929 (−7.5%) | 10,300 | 1,091 | 27,161 (−2.3%) |
| UT | State median | 7,850 (−8.5%) | 8,787 (−15%) | 459 (−58%) | 24,828 (−11%) |
| HI | Full | 2,378 | 5,425 | 118 | 8,958 |
| HI | Hidden parcels | 2,557 (+7.5%) | 5,834 (+7.5%) | 118 | 9,558 (+6.7%) |
| HI | State median | 2,636 (+11%) | 5,459 (+0.6%) | 77 (−35%) | 9,171 (+2.4%) |

Hiding Hawaii's land-use wall sets the geography-eligible share to 1.0 (the tier-2 default) instead of 0.93. That is why ADUs and missing middle rise there, and why the Monte Carlo band is not wider (0.93× the full band). Connecticut's band widens by 1.07× and Wisconsin's by 1.26× when the extract is hidden and the feasibility dispersion is scaled by the tier-2 multiplier 1.35. The practical recommendation: do not wait for a statewide parcel file to rank these reforms. County ACS prices and county permits already carry the variation that moves missing middle and transit. Lot-size microdata moves the ADU pathway by a few percent inside this five-year stock model.

## 11. Calibration anchors

Accessed 2026-10-25. National unit-weighted Building Permits Survey value, 2022–2024 average: $297,175 single-family and $150,337 multifamily (5+). State cost indexes are the state's unit value divided by that anchor, shrunk toward 1 when the cell has fewer than 800 units, and clamped to [0.55, 2.40]. Hawaii's multifamily index remains about 2.25 because the cell is not thin enough to shrink away a genuinely high valuation. FHFA All-Transactions index, 2000 = 100, latest year 2025 in the workbook dated March 31, 2026. Population growth is the annualized Census PEP change from July 1, 2020 to July 1, 2024.

Illustrative anchors: Pennsylvania median value $240,500, rent $1,162, transit commute 3.9 percent, pre-1940 share 25 percent, 67 counties. Connecticut median $343,200, nine planning regions (2022 geography; Western Connecticut's median is far above the state). Virginia 133 county equivalents, multifamily cost index 0.75. These are in the fixture file, not typed into the equations.

## 12. Uncertainty

Sliders are the `ui: true` parameters plus the three legal shares. Each has a published low, central, and high. Overrides outside the band are clamped. The tornado sets one slider to low, then high, and records the swing in the selected outcome. The Monte Carlo draws every slider from a triangle (mode = central, support = the band) with seed 20261014. Config sets 250 draws for the CLI (`config/assumptions.yaml`). The web app uses 80. The UI cross-check uses 40. `src/model/crossval.py` defaults to 60. Repeating the seed repeats the percentiles. The band is a sensitivity statement about the published ranges. It is not a forecast interval from historical forecast errors.

Parameters that move the package most, in the central case, are the ADU adoption hazard, the price shock, the construction-cost shock, and the missing-middle conversion cost. In Virginia and Hawaii the conversion-cost and price swings are the same order of magnitude as the central result. That is the model telling you the five-year total is a tail of feasible projects, not a count of zoned capacity.

## 13. What this model cannot tell you

Each scenario carries its own list in the app. The common limits:

- It does not predict which parcel, owner, or lender acts. The hazard rates stand in for that behavior, and they dominate the ADU result.
- It does not draw setbacks, slope, septic, or historic status. Physical feasibility is a lot-size screen, and missing middle follows the benchmark in assuming setbacks do not bind.
- It does not clear infrastructure, school capacity, or political opposition. The pace hazard is a construction speed, not a hearing calendar.
- It does not feed prices back to an equilibrium. The absorption cap is the only demand-side brake.
- It does not know the rent an ADU achieves or whether the unit houses a family member instead of a tenant.
- It does not treat station counts as a parcel-to-stop join. `tod_station_scale` is the honest knob.
- It does not measure today's fee schedule. Scenario 5 is the $50,000 comparison case.
- Where a reform is already partly law, the result is the residual gap, not the effect of the earlier statute.

A zero policy change produces a zero increment. Higher fee cuts, higher supply elasticity, higher prices, and a higher allowed FAR (when the absorption cap is not doing the work) raise the corresponding outcome. Those properties are tested in `tests/`.

## 14. Adding a state

Supply a state object and a list of counties with the keys in `REQUIRED_STATE_KEYS` and `REQUIRED_COUNTY_KEYS`. Set the tier. Optionally attach a `tier1` object with `lot_bins_sqft` or `mean_lot_sqft` or `urban_land_share`. Add a transit-inventory row and a legal-share block in `config/assumptions.yaml`. Run `validate_state`. The engine does not branch on the state postal code except to read those inputs. Parcel adapters must call `assert_no_pii` and must not request owner or mailing fields.

## 15. Small Homes Policy Lab

The Lab is a county-level comparison of small-home reforms in Pennsylvania (all 67 counties) with New Hampshire as a portability test. It is documented in [SMALL_HOMES_LAB.md](SMALL_HOMES_LAB.md) and configured in `config/lab/`. It resolves competing options lot by lot, keeps unknown zoning unknown, and reports ACS sampling error separately from the assumption envelope. The Lab and the core engine answer different questions and use different hosts and uptake assumptions, so their ADU totals differ; section 9 of the Lab method explains the gap. New Hampshire is the portability test (`docs/NH_PORTABILITY.md`). The four-page comparison is `docs/POLICY_SCENARIO_COMPARISON.md`.
