# Small Homes Policy Lab — method

The Lab compares small-home reforms across all 67 Pennsylvania counties, with New Hampshire as a portability test. It sits beside the Stateframe core engine: it shares the repository, license, test harness, and web server, but has its own configuration (`config/lab/`), data extracts (`data/sample/lab/`), and code (`src/lab/`). Run it with `python -m src.lab.run --state PA [--county Allegheny]`.

## 1. Outcome

**Net new homes completed inside the five-year window** (2027–2031), counted when finished. A rebuild that demolishes one house and finishes four counts +3. Each scenario is reported as Baseline plus an increment.

For each county and scenario the Lab reports three numbers:

| Output | Meaning |
| ------ | ------- |
| Eligible capacity | Homes that become legal and physically fit on a lot: Σ H × max d over options that are legal and fit |
| Feasible capacity | Of those, homes on lots whose pro forma clears the hurdle: Σ H × F × d |
| Delivery | Expected completions in five years: N = Σ H × F × p(T) × d |

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
| `mm2` keep the house, add a home | 1 | 2-BR rent | conversion cost × (1 + soft) + fee + spaces × surface cost | house footprint + half the new home's floor area + spaces × 325 | owner, homeowner hazard |
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
  - λ is 0.6% a year for homeowners on feasible lots. This is anchored to California's post-legalization ADU rate of about 0.3% of single-family homes a year with roughly half of lots feasible. Developers rebuilding a lot have half that rate.
- **Why the package is not a sum.** Separate scenarios each assume a lot can do their one option. The package lets every option compete for the same lot, so a lot that would add an ADU under one reform and a second home under another adds only one of them.

## 5. Legal status: unknown is never zero

- **Observed rules.** `config/lab/evidence/{PA,NH}.yaml` records observed rules: Philadelphia's ADU limits, Pittsburgh's 2026 ADU ordinance, New Hampshire's RSA 674:72 and SB 284.
- **Unknown lots.** Every other lot is **unknown**. An unknown lot is split into two partitions: "prohibited today" with prior probability π, and "allowed today" with 1 − π. The priors are π = 0.85 for the benchmark ADU and π = 0.90 for 2–6 homes. Treating unknown as zero would erase the reform's effect; treating it as allowed would erase the baseline.
- **Evidence coverage.** This is the stock-weighted share of hosts with an observed status:
  - PA: 13% for ADUs (Philadelphia and Pittsburgh) and 0% for 2–6 homes.
  - NH: 92% for ADUs and 0% for 2–6 homes.

## 6. Baseline and increments

**Pipeline baseline.** The 2023–2025 Building Permits Survey county average, by structure size, × 5 years × completion share. Completion shares are 0.93 for 1-unit, 0.90 for 2–4, and 0.84 for 5+.

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
- **Elasticity check.** The implied cost elasticity φ(z0) / F0 × (1 + h) / σ_p is 2.3 at central values, inside the 1–3 literature range. The Lab reports it with every result.
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
| 4. Parking | — | minimums eliminated; builders provide 0.5, 1.25, or 1.75 spaces per home (urban, suburban, rural); single-family builders keep their driveways |
| 5. Fees | — | fees fall from $50,000 to $25,000 per home |
| Package (extra) | all options, one per lot | fee cut, no minimums, no ADU parking |
| Approval (extra) | — | by-right approval with a shot clock; not bundled with parking |

Transit-oriented density (benchmark 3) is not a small-homes reform and is not modeled in the Lab. The core engine models it.
