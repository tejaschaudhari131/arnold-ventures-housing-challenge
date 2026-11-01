# New Hampshire portability

The Lab's second state is New Hampshire: ten counties, no local lot-area extract, and more observed zoning than Pennsylvania. The same engine, assumption file, and uncertainty layers run both states. Switching the https://stateframe-housing.vercel.app/lab selector from PA to NH is the demonstration.

## What travels

- Hosts are ACS 2020–2024 B25024 1-unit detached and attached homes, with margins of error.
- Contexts are tract density bins (urban ≥ 2,000, suburban ≥ 200 units per square mile).
- Lots are the assumed lognormal (median by type and context, σ = 0.6). There is no WPRDC equivalent.
- Options, pro formas, one-best-option resolution, the transition rule, and the pipeline threshold model are unchanged.
- Unknown zoning is still a prior, never zero.

## What is observed in New Hampshire

`config/lab/evidence/NH.yaml`:

- **RSA 674:72-73 (HB 577, 2025 ch. 197).** One attached or detached ADU is allowed by right on a detached single-family host from 2025-07-01, with up to one parking space. This falls inside the window, so the adoption lag applies from that date. Towns that already allowed detached ADUs before it count as already legal. That share is `nh_detached_adu_already_legal` (central 0.57, band 0.45–0.70), assumed from the NHMA 2024 survey (about 129 of 227 towns; figure not re-verified) and drawn in the Monte Carlo. Attached hosts stay unknown and use `prior_adu_prohibited_nh_attached` (0.10 / 0.30 / 0.60), not the Pennsylvania 0.85 prior, because the statute's default is allowed unless a town acts. ASSUMPTION, widened range. Towns may require owner occupancy (179 of 227 zoned jurisdictions); the Lab has no owner-occupancy friction, so that 0.79 share is not applied.
- **SB 284 (Chapter 258, 2025).** Statewide cap of one required parking space per home, effective 2025-09-13. The pipeline response (73 five-year completions) is a Baseline adjustment, not a parking-scenario increment.

ADU evidence coverage is 92 percent of hosts. Missing-middle coverage is 0 percent — the same gap as Pennsylvania.

## Result

| Scenario | NH increment | Likely range | Zoning | Census survey error |
| -------- | -----------: | -----------: | -----: | ------------------: |
| Baseline (level) | 22,788 | 21,147–23,472 | 22,756–22,810 | ±19 |
| ADUs | +38 | 6–57 | 19–60 | ±3 |
| Missing middle | +870 | 267–1,499 | 750–966 | ±67 |
| Parking | +29 | 6–43 | 19–36 | ±2 |
| Fees | +1,001 | 408–1,161 | 981–1,015 | ±8 |
| Package | +1,890 | 949–2,583 | 1,749–2,003 | ±72 |
| Approval | +1,327 | 899–2,185 | 1,327–1,327 | ±0 |

Baseline is the BPS 2023–2025 run-rate, the same completion shares as the core engine, the SB 284 parking-cap adjustment (73 homes), and a host adjustment. The ADU increment is +38: about 57 percent of detached hosts already allowed a detached ADU and stay in Baseline; the rest became legal on 2025-07-01. Missing middle is unknown everywhere, so the prior does the work (nearly all `mm2`). Parking is incremental to SB 284's already-in-Baseline cap. Fees use the same $50,000 → $25,000 Handbook lever as Pennsylvania. The package is resolved, not summed. Approval is the discretionary-share pipeline only.

Handbook ranking: Fees > Missing middle > ADUs > Parking. The top pair is Fees over Missing middle (47% of draws flip). 9 of ten counties have a close top-benchmark pair.


## What this test is for

A second state with less local data should not require new code. It did not. The ADU result staying small, at +38, is the intended check: a reform that is already law is in Baseline. The host model still counts a background ADU flow of 413 homes over five years on 244,313 lots where ADUs are already legal. NH OPD permit data may undercount ADUs. A team that treated unknown as zero would report a zero missing-middle increment in both states. A team that treated unknown as allowed would erase Baseline. The Lab does neither.
