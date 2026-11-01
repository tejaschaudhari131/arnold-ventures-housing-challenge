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

- **RSA 674:72 (HB 577, 2017).** One ADU is allowed on a detached single-family host, with parking. Effective 2017-06-01, so it is in-window: remaining adoption lag is zero. Attached hosts stay unknown and use `prior_adu_prohibited_nh_attached` (0.10 / 0.30 / 0.60), not the Pennsylvania 0.85 prior, because the statute's default is allowed unless a town acts. ASSUMPTION, widened range. Towns may require owner occupancy (179 of 227 zoned jurisdictions); the Lab has no owner-occupancy friction, so that 0.79 share is not applied. RSA 674:72 IV caps an added ADU parking space at one.
- **SB 284 (Chapter 258, 2025).** Statewide cap of one required parking space per home, effective 2025-09-13. The pipeline response (69 five-year completions) is a Baseline adjustment, not a parking-scenario increment.

ADU evidence coverage is 92 percent of hosts. Missing-middle coverage is 0 percent — the same gap as Pennsylvania.

## Result

| Scenario | NH increment | Likely range | Zoning | Census survey error |
| -------- | -----------: | -----------: | -----: | ------------------: |
| Baseline (level) | 22,099 | 21,041–23,237 | 22,099–22,099 | ±0 |
| ADUs | +15 | 9–28 | 4–34 | ±1 |
| Missing middle | +958 | 268–1,704 | 826–1,064 | ±65 |
| Parking | +3 | 0–13 | 3–3 | ±0 |
| Fees | +842 | 348–1,063 | 842–842 | ±0 |
| Package | +1,740 | 808–2,580 | 1,626–1,837 | ±66 |
| Approval | +1,302 | 898–2,138 | 1,302–1,302 | ±0 |

Baseline is the BPS 2023–2025 run-rate plus the SB 284 parking-cap adjustment. The ADU increment is attached-host priors and the no-parking lever — almost all detached hosts already have a legal ADU path. Missing middle is unknown everywhere, so the prior does the work (nearly all `mm2`). Parking is incremental to SB 284's already-in-Baseline cap. Fees use the same $50,000 → $25,000 Handbook lever as Pennsylvania. The package is resolved, not summed. Approval is the discretionary-share pipeline only.

Handbook ranking: Missing middle > Fees > ADUs > Parking. The top pair is Missing middle over Fees (42% of draws flip). 9 of ten counties have a close top-benchmark pair.


## What this test is for

A second state with less local data should not require new code. It did not. The ADU result shrinking to +15 is the intended check: a reform that is already law is in Baseline. A team that treated unknown as zero would report a zero missing-middle increment in both states. A team that treated unknown as allowed would erase Baseline. The Lab does neither.
