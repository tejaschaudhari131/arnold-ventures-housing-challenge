# Baseline

Recorded 2026-11-01 while this branch was cut from main.

## Git

| Item | Value |
| --- | --- |
| main SHA this branch started from | `8952914a3f1e84f1829a23c957335ca7f758f426` (merge of PR #22) |
| Previous main cited by the contract | `308e33614b38847aad7714390266362e5b906a9f` (merge of PR #21). Local checkout was stale at `a8f1bac` until `git fetch origin main`. |
| Open PR heads at record time | #15 `dependabot/pip/ruff-0.17.3` @ `a954cec`; #14 `dependabot/pip/pytest-9.2.0` @ `020b628`; #4 `dependabot/pip/setuptools-gte-84.2.1` @ `0994506`; #3 `dependabot/pip/pyyaml-6.0.3` @ `b44e13c`. PR #22 is merged. |

## Production `/api/health`

`GET https://stateframe-housing.vercel.app/api/health` on 2026-11-01:

```json
{"ok": true, "sha": "308e33614b38847aad7714390266362e5b906a9f", "short_sha": "308e336", "date": "", "fingerprints": {"NH": "f0a85db0ee26fda1", "PA": "18b20e94b790213c"}}
```

The date is empty because that deploy has no `VERCEL_GIT_COMMIT_DATE` and no build stamp. Prod is still the pre-#22 commit. `GET /docs/SMALL_HOMES_LAB.md` returned 404. The Lab HTML linked to the GitHub blob URL instead.

## Runtimes

| Tool | Version |
| --- | --- |
| Python | 3.12.3 |
| Node | v22.23.4 |
| pip (inside `.venv`, after setup) | 26.2.2 |

## Resolved dependencies

From `.venv/bin/python -m pip freeze` after `bash scripts/setup.sh`:

| Package | Version | Scope |
| --- | --- | --- |
| PyYAML | 6.0.2 | app (`required`) |
| pytest | 8.3.5 | dev |
| ruff | 0.14.2 | dev |
| pluggy | 1.7.0 | dev, from pytest |
| iniconfig | 2.3.1 | dev, from pytest |
| packaging | 26.3 | dev, from pytest (Apache-2.0 OR BSD-2-Clause) |

## Fixture fingerprints

SHA-256 prefixes of the committed files, and the Lab result stamps:

| File | SHA-256 prefix |
| --- | --- |
| `data/sample/fixtures.json` | `c95463c15bea938f` |
| `data/sample/lab/PA.json` | `f2dde64df3579ca9` |
| `data/sample/lab/results_PA.json` | `0fe789d6fdd62c7c` |
| `data/sample/lab/results_NH.json` | `bf9d2a3782cdb128` |

Lab result `fingerprint` field after the horizon guard in `src/lab/engine.py` and the unknown-state check in `src/lab/results.py` (source hash, not a numeric regen): PA `c80f359be200f18d`, NH `a1c2fa6fe66b03a7`. Before those edits they were `18b20e94b790213c` and `f0a85db0ee26fda1`.

## Commands actually run

| Command | Result |
| --- | --- |
| `sudo apt-get install -y python3.12-venv` | Success. `python3 -m venv` had failed because `ensurepip` was missing. |
| `bash scripts/setup.sh` | Success. Installed the six packages above. |
| `node --check src/web/static/app.js` and `lab.js` | Exit 0. |
| `node tests/js/lab_roundtrip.mjs` | Exit 0. Empty `on=none` and the hazard override round-trip. |
| `ruff check src tests` | All checks passed. |
| `pytest -q` (addopts cleared so the summary prints) | 184 passed in about 20s. Exit 0. |
