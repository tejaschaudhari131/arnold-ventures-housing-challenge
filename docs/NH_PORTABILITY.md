# New Hampshire portability

The Lab's second state is New Hampshire: ten counties, no local lot-area extract, and more observed zoning than Pennsylvania. The same engine, assumption file, and uncertainty layers run both states. Switching the `/lab` selector from PA to NH is the demonstration.

## What travels

- Hosts are ACS 2020–2024 B25024 1-unit detached and attached homes, with margins of error.
- Contexts are tract density bins (urban ≥ 2,000, suburban ≥ 200 units per square mile).
- Lots are the assumed lognormal (median by type and context, σ = 0.6). There is no WPRDC equivalent.
- Options, pro formas, one-best-option resolution, the transition rule, and the pipeline threshold model are unchanged.
- Unknown zoning is still a prior, never zero.

## What is observed in New Hampshire

`config/lab/evidence/NH.yaml`:

- **RSA 674:72 (HB 577, 2017).** One ADU is allowed on a detached single-family host, with parking. Effective 2017-06-01, so it is in-window: remaining adoption lag is zero. Attached hosts stay unknown.
- **SB 284 (Chapter 258, 2025).** Statewide cap of one required parking space per home, effective 2025-09-13. The pipeline response (107 five-year completions) is a Baseline adjustment, not a parking-scenario increment.

ADU evidence coverage is 92 percent of hosts. Missing-middle coverage is 0 percent — the same gap as Pennsylvania.

## Result

| Scenario | NH increment | Why it looks like that |
| -------- | -----------: | ---------------------- |
| Baseline | 22,136 | BPS 2023–2025 run-rate plus the SB 284 parking-cap adjustment |
| ADUs | +81 | Almost all detached hosts already have a legal ADU path; the increment is attached-host priors and the no-parking lever |
| Missing middle | +2,344 | 2–6 homes are unknown everywhere, so the prior does the work. Nearly all `mm2` |
| Parking | +30 | Incremental to SB 284's already-in-Baseline cap |
| Fees | +1,095 | Same $50,000 → $25,000 Handbook lever as Pennsylvania |
| Package | +3,761 | Resolved, not summed |
| Approval | +1,364 | Discretionary-share pipeline only; timing pull-forward reported separately |

Missing middle still leads the four Handbook benchmarks. The MM-versus-fees pair is a close call (16 percent of draws). Seven of ten counties have a close top-benchmark pair.

## What this test is for

A second state with less local data should not require new code. It did not. The ADU result shrinking to +81 is the intended check: a reform that is already law is in Baseline. A team that treated unknown as zero would report a zero missing-middle increment in both states. A team that treated unknown as allowed would erase Baseline. The Lab does neither.
