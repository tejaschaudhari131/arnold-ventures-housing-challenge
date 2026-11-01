# Decision log

| Date | Decision | Why |
| --- | --- | --- |
| 2026-11-01 | Branch from main `8952914` after PR #22 merged. | The earlier instruction was to stack on PR #22. It landed, so this branch starts there and does not reimplement its cache, unknown-state, or uncapped-potential work. |
| 2026-11-01 | Lab recompute and exports keep the locked p10/p90 and label it `Reference range (defaults)`. | A 2,000-draw conditional interval on every slider would be a synchronous multi-thousand-draw request. The contract allows a labeled reference. The Outcome uncertain badge is not shown on that reference. |
| 2026-11-01 | Partial Lab packages stay a labeled simple sum. | A real resolver for every subset is defect 4, Phase 4. This PR does not change model economics. |
| 2026-11-01 | Screening and Lab engines stay separate. | Defect 6. They answer different questions. Reconciliation is Phase 4. |
| 2026-11-01 | `capacity_completions` gains a basis label (`level` on baseline, `increment` on reforms) and no numeric change. | The same field name meant two things. Incremental results are unchanged. |
| 2026-11-01 | `pipeline_effect` returns zeros when the horizon is not positive. | Horizon 0 divided by the horizon. The published horizon is still 5 years. |
| 2026-11-01 | `/docs/<name>.md` is served from an allowlist of files directly under `docs/`. | Prod returned JSON 404 for `/docs/SMALL_HOMES_LAB.md`. The Lab link now points at that path. `vercel.json` includes `docs/` in the function bundle. |
| 2026-11-01 | 400 responses are truncated to 160 characters and do not repeat request text. | A hostile state string was echoed, including `<script>` and multi-kilobyte bodies. |
| 2026-11-01 | Downloads require HTTPS and re-check the host allowlist after redirects. | A redirect could leave the allowlist. |
| 2026-11-01 | CSP allows inline styles and only same-origin scripts. | The pages set `style` attributes from `innerHTML`. There are no inline scripts. |
| 2026-11-01 | The SBOM is generated from the installed resolution of `requirements.txt`, split into `required` and `optional`. | The old file listed only the three direct pins. |
| 2026-11-01 | Lab source fingerprints were rewritten after the horizon guard and the CLI state check. | `fingerprint()` hashes `src/lab/engine.py` and `src/lab/results.py`. Result numbers were not regenerated. The new stamps are PA `c80f359be200f18d` and NH `a1c2fa6fe66b03a7`. |
| 2026-11-01 | Phase 2's one-entry redesign is not in this PR. | The owner deferred it. Only the cheap 768/390 fixes are included. |
| 2026-11-01 | A 2- or 3-reform Lab CSV labels summed eligible and feasible counts and does not invent a joint close-call. | Adding per-reform eligible counts double-counts lots. Adams County, PA is about 173,453 summed versus about 148,523 on the joint package. The columns are renamed and `close_call_top_benchmark` is `not computed for mix`. The basis text lives in those columns. The CSV starts at the header row. |
| 2026-11-01 | A repeated Lab reform id is HTTP 400 `Duplicate reform.` The four ids in any order are the package. | `['adu','adu']` was counted twice (Adams central 98.2). A full list plus a repeat was treated as a custom mix. Screening reforms are an object, so a JSON key cannot repeat. |
