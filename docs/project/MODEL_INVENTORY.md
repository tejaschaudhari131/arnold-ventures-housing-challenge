# Model inventory

Two engines share a repository and a web server. They are not the same model. Duplicated mechanics are marked. Defect-flagged numbers are in `tests/fixtures/characterization.json`.

## Screening core (`src/model/`)

County pro formas summed to the state. Eleven states. Five reforms plus a package. Five-year permits and completions.

| Function | Role |
| --- | --- |
| **Inputs** | `src/data/schema.py` validates a state. `src/data/adapters.py` turns a raw extract into that schema. `src/data/acquire.py` downloads ACS, BPS, PEP, the gazetteer, and FHFA, then adapts. `config/assumptions.yaml` holds every default. `Assumptions.resolve` applies overrides inside the published band. |
| **Baseline** | `engine._baseline` extends the 2022–2024 permit mix over five years with the completion ratios and the trend. Already-legal production stays in the baseline. |
| **Economics** | `equations.py`: feasibility share, rental and sale value, elasticity increment, parking yield, FAR, walkshed. `engine.evaluate_county` builds one county pro forma. |
| **Host allocation** | Lot screen (`lot_feasibility`, `share_at_least`, `lognormal_tail`) splits eligible homes. Not a parcel list. |
| **Timing** | `cumulative_hazard`, `horizon_multiplier`, `adu_hazard`. Delivery is a hazard over the horizon, not a calendar of projects. |
| **Overlap** | `allocate_walkshed` removes walkshed parcels from missing middle and parking. The package is `_combined_row`, not the sum of the five standalone runs. |
| **Uncertainty** | `sensitivity.tornado` and `sensitivity.monte_carlo` move the published slider band with a fixed seed. `crossval.py` hides tier-1 parcel extracts. |
| **Reporting** | `engine.simulate_state` returns scenarios, a county table, and a trace. `export/report.py` writes CSV, JSON, and Markdown from that object. |
| **Presentation** | `src/web/static/app.js` only displays the server payload. It does not recompute the equations. |

## Small Homes Lab (`src/lab/`)

Pennsylvania (67 counties) and New Hampshire. Four Handbook bills plus a package and an extra approval scenario. Outcome is net new homes in 2027–2031.

| Function | Role |
| --- | --- |
| **Inputs** | `lab/config.py` loads YAML. `lab/data.py` builds counties, imputes gaps, and applies evidence rules. Unknown zoning stays unknown. `lab/acquire.py` is the refresh path. |
| **Baseline** | `pipeline_effect` is the permit pipeline. Homes already legal during the permit window stay there. `evaluate_county` adds a host adjustment for the legal set. |
| **Economics** | `options.evaluate_option` is the pro forma (ADU, 2, 4, 6 homes). `scenario_econ` sets fee, parking, and approval. |
| **Host allocation** | `resolve_hosts` gives each lot at most one option. `expand_segment` splits unknown zoning by the prior. |
| **Timing** | `timing_share` is the chance a start finishes inside the window after legal lag and build lag. |
| **Overlap** | `package_decomposition` compares the joint legalization run with the sum of ADU and missing middle, then adds the fee and parking steps. Partial selections in the UI are still sums (defect 4). |
| **Uncertainty** | `uncertainty.py`: assumption envelope, zoning bounds, and ACS margins, kept separate. The envelope is precomputed (2,000 draws, seed 20261107). A slider recompute does not redraw it. |
| **Reporting** | `results.compact` writes the locked JSON. `explain.py` serves Why, recompute, and the brief. |
| **Presentation** | `lab.js` renders locked or live JSON. Ranges on a live run are labeled `Reference range (defaults)`. |

## Duplicated mechanics

| Idea | Screening | Lab | Same equation? |
| --- | --- | --- | --- |
| Completion of the existing permit pipeline | `_baseline` and completion ratios | `pipeline_effect` | No. Different vintages (2022–2024 vs 2023–2025) and different completion parameters. |
| Development fee | Fee per reform in `assumptions.yaml`. ADU fee defaults to $6,000 | `fee_per_unit`, Handbook $50,000 on ADUs | No. The pages say so. |
| Feasibility | Normal CDF of a margin (`feasibility_share`) | `Phi` of the best option's excess margin | Related form, different inputs and options. |
| Adoption over time | Annual hazard and a cumulative hazard | `timing_share` with explicit lags | Related form, different clocks. |
| Overlap of ADU and missing middle | Walkshed removal inside the screening package | One option per lot in `resolve_hosts` | No. Do not substitute one for the other. |
| Uncertainty | One seeded triangular band on the screening sliders | Three layers, precomputed | No. |
| County-to-state sum | Sum of county completions, largest remainder for the table | Sum of county deliveries inside a draw, then percentiles | The add-up idea is shared. The percentile step exists only in the Lab. |

## What this inventory does not claim

The screening package of about 74,114 and the Lab package of about 18,023 are both calculated. They are not two measurements of one policy. Defect 6 stays open until a reconciliation report names the residual.
