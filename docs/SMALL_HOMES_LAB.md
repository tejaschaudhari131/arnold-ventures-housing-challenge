# Small Homes Policy Lab — method

The Lab compares small-home reforms across all 67 Pennsylvania counties, with New Hampshire as a portability test. It sits beside the Stateframe core engine: it shares the repository, license, test harness, and web server, but has its own configuration (`config/lab/`), data extracts (`data/sample/lab/`), and code (`src/lab/`). Run it with `python -m src.lab.run --state PA [--county Allegheny]`.

## 1. Outcome

**Net new homes completed inside the five-year window** (2027–2031), counted when finished. A rebuild that demolishes one house and finishes four counts +3. Each scenario is reported as Baseline plus an increment.

For each county and scenario the Lab reports three numbers:

| Output | Meaning |
| ------ | ------- |
| Eligible capacity | Homes that become legal and physically fit on a lot: Σ H × max d over options that are legal and fit |
| Feasible capacity | Of those, homes on lots whose pro forma clears the hurdle: Σ H × F × d |
| Delivery | Expected completions in five years: N = Σ H × F × p(T) × d × completion. ADU hazard is the all-lots rate divided by judgmental F_CA, and delivery uses the same F as the other options. completion is the screening ratio for the chosen option. |

## 2. Hosts

A host group *j* is a county × context × host type, split further by lot size and legal status.

- **H, observed.** ACS 2020–2024 B25024 1-unit detached and 1-unit attached homes, with their margins of error. Mobile homes and multi-unit buildings are not hosts.
- **Context, calculated.** Urban, suburban, or rural, from each tract's housing units per square mile of land. Urban is 2,000 or more and suburban is 200 or more; both thresholds are assumed. County totals are the control; tracts only set the shares.
- **Lot size, assumed.** Lognormal, with a median by host type and context and σ = 0.6. Allegheny County uses the observed WPRDC lot-area bins instead: Pittsburgh lots for urban hosts and the rest of the county for suburban and rural hosts.

## 3. Options and pro formas

Each lot takes **at most one** option.

| Option | Homes added d | Value V | Cost C | Lot area needed | Hurdle, uptake |
| ------ | ------------- | ------- | ------ | --------------- | -------------- |
| `adu` | 1 | 1-BR rent | ADU sq ft × $/sq ft × (1 + soft) + fee + spaces × surface cost | house footprint + ADU footprint + 400 sq ft yard + spaces × 325 | owner, homeowner hazard |
| `mm2` keep the house, add a home | 1 | 2-BR rent | conversion cost × (1 + soft) + fee + spaces × surface cost | house footprint + half the new home's floor area + spaces × 325 | owner, feasible-lot homeowner hazard |
| `mm4` rebuild as 4 | 3 | 4 × 2-BR rent | 4 × (950 sq ft × $/sq ft × (1 + soft) + fee) + spaces × cost per space + median value × teardown factor + demolition | 4 × 950 / 3 stories + surface spaces × 325 | developer, developer hazard |
| `mm6` rebuild as 6 | 5 | 6 × 2-BR rent | the same formula with 6 homes | 6 × 950 / 3 + surface spaces × 325 | developer, developer hazard |

The terms in the table are defined as follows:

- **Rent and value.** Rents are ACS B25031 county medians (observed). Value is rent × new-home premium × 12 × (1 − operating share) / cap rate (calculated).
- **Margin.** m = V/C − 1, and the excess margin is x = m − hurdle.
- **Missing middle envelope.** Setbacks and lot coverage do not bind, per the Handbook. Parking minimums still apply unless a scenario removes them.
- **Parking provided.** Builders provide max(minimum, market ratio) per home under a mandate, and the market ratio without one.
- **Urban rebuilds.** Half of the spaces are tucked under the building; tucked spaces cost more but use no lot area.

## 4. Resolution, feasibility, timing

- **Lot slices.** Lots in a host group are split at each option's required area. In every slice, the lot takes the fitting legal option with the largest excess margin, with ties going to the option that adds more homes.
- **Feasibility.** Each lot's own margin is the group margin plus a lot-specific shock with spread σ (central 0.25). The shock is common across options, so the same option is best for the whole slice and **F = Φ(x_best / σ)**.
- **Timing.** **p(T) = 1 − exp(−λ × max(0, T − legal lag − build lag))**, with T = 5.
  - The legal lag is 1 year for a reform adopted at the start of the window. For a rule enacted shortly before the window it is whatever remains of that year; Pittsburgh's ordinance (2026-10-29), for example, has 0.82 years left.
  - λ for ADUs is the 2017–21 mean of California HCD APR ADU permits divided by the DOF E-5 single-detached stock (0.15% a year on all lots), divided by F_CA. F_CA is judgmental, central 0.5, shown range 0.3 to 0.7. Delivery then multiplies by F = Φ(x/σ), the same share as the other options, and by the screening completion ratio (ADU 0.92, mm2 and mm4 0.90, mm6 0.90). mm2 uses hazard_homeowner / F_CA and still multiplies by F. Developers rebuilding a lot use half that feasible-lot rate, still times F. Sourced from HCD APR / CA DOF E-5. The Census 93% completion citation is not a Census abandonment rate; it is assumed.
- **Transition between options.** A newly legal option can beat one that is already legal, for example 2–6 homes on a Pittsburgh lot where ADUs are already allowed. Lots keep building the incumbent option until the new option's legal lag ends. After that, lots are split by a common shock: the overlap (lots that pencil for both) stays with the ADU; mm2 takes only the lots that work for mm2 but not for an ADU, take = max(0, Φ(x_mm/σ) − Φ(x_ADU/σ)). Legalizing a better option therefore never strands lots that were already building.
- **Why the package is not a sum.** Separate scenarios each assume a lot can do their one option. The package lets every option compete for the same lot, so a lot that would add an ADU under one reform and a second home under another adds only one of them.

## 5. Legal status: unknown is never zero

- **Observed rules.** `config/lab/evidence/{PA,NH}.yaml` records observed rules: Philadelphia's ADU limits, Pittsburgh's 2026 ADU ordinance, New Hampshire's RSA 674:72 and SB 284.
- **Unknown lots.** Every other lot is **unknown**. An unknown lot is split into two partitions: "prohibited today" with prior probability π, and "allowed today" with 1 − π. The priors are π = 0.85 for the benchmark ADU and π = 0.90 for 2–6 homes. New Hampshire attached hosts (the RSA 674:72 townhouse exception) use π = 0.30 instead (band 0.10–0.60). ASSUMPTION, widened range. Treating unknown as zero would erase the reform's effect; treating it as allowed would erase the baseline.
- **Owner occupancy.** New Hampshire towns may require the host to be owner-occupied (179 of 227 zoned jurisdictions, OPD 2024). The Lab has no owner-occupancy friction, so that 0.79 share is not applied as an extra multiplier.
- **Evidence coverage.** This is the stock-weighted share of hosts with an observed status:
  - PA: 13% for ADUs (Philadelphia and Pittsburgh) and 0% for 2–6 homes.
  - NH: 92% for ADUs and 0% for 2–6 homes.

## 6. Baseline and increments

**Pipeline baseline.** The 2023–2025 Building Permits Survey county average, by structure size, × 5 years × an assumed completion share. Shares are 0.93 for 1-unit, 0.90 for 2–4, and `completion_ratio_mf` (0.90) for 5+. Census does not publish an abandonment rate, so those shares are labeled assumed. The lot path uses the same screening ratios (ADU 0.92, 2–4 0.90, 5+ 0.90).

For Pennsylvania the Lab pipeline baseline equals the core screening baseline (113,269). The published Lab baseline is higher by the host adjustment for homes the permit window cannot contain yet. New Hampshire matches the same way on the pipeline; its headline baseline also includes the host adjustment and the parking-cap response.

**Baseline adjustments.** Homes the permit window cannot contain yet are added to Baseline:

- **Pittsburgh ADUs**, from the host model.
- **New Hampshire's 1-space parking cap**, from the pipeline model.

A rule is "post-window" if its effective date plus the adoption lag falls after December 31, 2025.

**Host terms.** L0 is today's legal set and L0_pre the part that was already legal during the permit window. L1 is the legal set under the scenario. e0 and e1 are today's and the scenario's economics.

- baseline adjustment = N(L0, e0) − N(L0_pre, e0)
- scenario increment = N(L1, e1) − N(L0_pre, e1) − baseline adjustment

Options already legal and flowing during the window are in the permit data, so they are not counted twice. Lots that were already allowed during the window contribute zero to a legalization reform.

**Pipeline terms.** Fee, parking, and approval changes reach already-legal projects through a threshold model:

- **Feasible share.** Today a share F0 = 0.5 of candidate projects clears the developer hurdle h. A saving s per home moves the marginal project's margin by (1 + h) × s / C, so the new share is F1 = Φ(Φ⁻¹(F0) + (1 + h) × s / C / σ_p).
- **Cost per home.** C comes from the observed BPS valuation per home: C = (valuation × (1 + soft) + fee + spaces × cost per space) / (1 − land share).
- **Elasticity check.** The implied cost elasticity is φ(z0) / F0 × (1 + h) / σ_p. F0 is fixed at 0.5 (it is not identified separately from σ_p). Central σ_p = 0.52 gives ε ≈ 1.75, the Saiz 2010 metro-level mean (QJE 125(3), https://doi.org/10.1162/qjec.2010.125.3.1253). The envelope draws ε ~ triangular(0.25, 1.75, 3.0) and sets σ_p = 0.918/ε. A probit cannot reach ε = 0; that case is a separate sensitivity row. ASSUMPTION, widened range. The Lab reports ε with every result.
- **Responding permits.** Only permits that can respond inside the window count: the fraction is max(0, T − adoption lag − response lag − build lag) / T.
- **Parking yield.** On the share of multifamily sites where parking sets the unit count, fewer required spaces also add homes per site.
- **Approval reform (extra scenario).** It saves carrying cost and finishes homes sooner, but only on the share of the pipeline that goes through discretionary review (central 50%). The sooner-finished homes are reported separately as a timing shift.

## 7. Scenarios

Levers are defined in `config/lab/scenarios.yaml` and tested against the Handbook in `tests/test_lab_rules.py`.

| Scenario | Legal change | Economic change |
| -------- | ------------ | --------------- |
| Baseline | — | — |
| 1. ADU | `adu` on every single-family lot | the ADU needs no parking space |
| 2. Missing middle | `mm2`, `mm4`, `mm6` on every single-family lot | — (parking minimums still apply) |
| 4. Parking | — | minimums eliminated; builders provide 0.9, 1.25, or 1.75 spaces per home (urban, suburban, rural); single-family builders keep their driveways |
| 5. Fees | — | fees fall from $50,000 to $25,000 per home |
| Package (extra) | all options, one per lot | fee cut, no minimums, no ADU parking |
| Approval (extra) | — | by-right approval with a shot clock; not bundled with parking |

Transit-oriented density (benchmark 3) is not a small-homes reform and is not modeled in the Lab. The core engine models it.

## 8. Uncertainty and close calls

The Lab reports three uncertainty layers separately and never adds them together. Each answers a different question.

| Layer | Question | Method | PA ADU increment |
| ----- | -------- | ------ | ---------------- |
| Assumption envelope | What if our economic and behavioral assumptions are off? | 2,000 assumption draws (seed 20261107) over every adjustable parameter except the zoning priors and the locked Handbook levers. All scenarios share the same draws. Reported as p10–p90, with a bootstrap SE on each percentile. | 3,343–11,084 |
| Zoning-evidence bound | What if unknown zoning is more or less permissive than our prior? | The priors are set to their low and high ends, giving the reported bound. The logical bound sets every unknown lot to allowed and then to prohibited. | 4,416–6,486 (logical -45–6,918) |
| ACS sampling error | What if the survey inputs are off by their margin of error? | Each county's host counts, 1-BR and 2-BR rents, and median value are moved by −MOE and +MOE, one at a time. Half the change is the sensitivity, and the sensitivities combine in quadrature across inputs and counties. | ±26 |

A comparison between two scenarios is flagged as a **close call** if any of the following holds:

- the order of the two scenarios flips in at least 10% of the assumption draws. This 10% is the flag threshold (`close_call_flip_share` in results files), not a measured flip rate;
- the order flips at an end of the zoning-evidence bound; or
- the central gap is smaller than the ACS margin on the gap. The margin on the gap is computed from the difference in sensitivities, not from the two separate margins.

**One at a time.** Each parameter is moved alone to its low and its high end, with the others at central.

The screening Monte Carlo (`src/model/sensitivity.py`, also section 12 of `docs/MODEL_AND_ASSUMPTIONS.md`) is a different band. There, an overridden parameter becomes the mode of its triangle and still varies between the published low and high. The Lab envelope in the table above stays on the locked central modes.

**Switching values.** For the leading benchmark pair, bisection finds the value of each parameter at which the pair ties, if that value lies inside the parameter's band. This is the "what would change our conclusion" view. A separate ε = 0 row sets `pipeline_sigma` to 1,000 (a probit cannot reach exactly 0).

**Auckland ceiling.** Greenaway-McGrevy & Phillips 2023 (JUE 136:103555; https://doi.org/10.1016/j.jue.2023.103555) report 21,808 extra dwellings permitted over five years, about 4.11% of Auckland's regional dwelling stock. Five-year Missing Middle, ADU + Missing Middle, and package net completions divided by ACS B25001 housing stock must stay at or under 4.1% for every state and county output (`tests/test_lab_engine.py`). Any result above that needs explicit justification.

In Pennsylvania, Central estimate favors Missing middle; Fees ahead in 46% of draws (draw medians Fees 4,134 vs MM 4,346) (922 of 2,000). The Lab envelope is 2,000 assumption draws. It would flip at any of these values:

- project-to-project margin spread 0.4821 (central 0.52)
- homeowner uptake hazard (feasible lots) 0.28% a year (central 0.30% a year)
- conversion / addition hard cost per added home $164,301 (central $160,000)
- capitalization rate 6.1% (central 6.0%)
- new-home rent premium over ACS median 107.6% (central 110.0%)
- operating cost share 31.5% (central 30.0%)
- homeowner hurdle margin 0.0191 (central 0)
- lot-to-lot margin spread 0.2149 (central 0.25)
- pipeline response lag 0.5858 (central 0.75)
- small multifamily permit-to-completion 1.19 (central 1.5)
- conversion / addition permit-to-completion 1.21 (central 1)
- soft costs 23.0% (central 18.0%)
- cost elasticity of 0 (`pipeline_sigma` → 1,000): fees +27, parking +100 (central ε 1.76)


**Package decomposition.** The package is decomposed in steps, and each step is an exact model run:

1. legalization only, with lots resolved;
2. the fee cut added; and
3. the removal of parking minimums added.

The decomposition also reports the separate scenarios summed, to show what double counting would add.

| PA step | Homes |
| ------- | ----- |
| Legalization if summed (ADU + missing middle) | 8,517 |
| Legalization resolved, one option per lot | 5,424 |
| + fee cut | +7,321 |
| + parking minimums removed | +540 |
| **Package** | **13,285** |
| Sum of the four separate scenarios | 14,178 |

Resolution removes 3,093 double-counted homes. The fee cut adds more inside the package (7,321) than the fee scenario alone (5,360), because it also improves the newly legal options. The net interaction is −893.

## 9. Why the Lab's ADU total differs from the core engine's

Lab at the Handbook's $50,000 fee: +2,742. Lab at a $6,000 fee: +5,652. Core at a $6,000 fee: +30,213. The same $6,000 fee does not match because the Lab is a county-level model and the core uses a different adoption and valuation model. The Lab's Pennsylvania ADU increment (+2,742) applies the Handbook's $50,000 per-home fee to ADUs. The core Stateframe engine uses its own $6,000 ADU fee and reports +30,213. Walking the Lab toward the core: value the ADU the way a homeowner does — 4.5 percent cap rate, no operating share, rent × 0.85 (+14,392); then drop adoption and build lags (+22,481), within about 26 percent of the core. The Lab numbers answer the Handbook scenarios (Handbook $50,000 per-home fees, county-level model). The core numbers are an eleven-state screening model with a $6,000 ADU fee. Pennsylvania package: Lab +13,285, core +46,219. See the Lab at https://stateframe-housing.vercel.app/lab and the core engine at https://stateframe-housing.vercel.app/. The Lab baseline (113,305) and the core baseline (113,269) differ by +36. Pennsylvania's core permits are the same 2023-2025 county files as the Lab. The Lab pipeline uses the same never-complete shares as the core (0.93/0.90/0.90), including completion_ratio_mf for 5+ homes, so the pipeline baselines match. The residual after the host term is +0. The Lab also adds a +36 host adjustment for already-legal homes the permit window cannot contain yet.


The two engines also answer different questions. The table below moves the Lab's assumptions toward the core engine's one at a time, cumulatively.

| Step | PA ADU homes |
| ---- | ------------ |
| Lab central (Handbook $50,000 fee per home, investor yield, adoption and build lags) | 2,742 |
| Lab with a $6,000 fee instead of the Handbook's $50,000 | 5,652 |
| Homeowner yield: cap rate 4.5%, no operating share, rent × 0.85 | 14,392 |
| No adoption lag and no build lag | 22,481 |

The two engines also define hosts and lots differently, and the last step is within about 26 percent of the core figure rather than on it. The remaining gap is the one-engine-versus-two question, which this milestone does not change.

Three choices explain the gap:

- **The fee.** The Handbook fixes current fees at $50,000 per home and the Lab applies that to ADUs too, which is a judgment call. The fee cut scenario then halves it.
- **The yield.** The Lab values an ADU as rental property.
- **The window.** The Lab counts only homes completed after a reform takes effect and a home is built.
