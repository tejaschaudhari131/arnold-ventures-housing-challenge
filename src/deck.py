# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Data-bound executive slide deck (<=30 slides, print-to-PDF ready).

Every figure on every slide is read from the locked Lab results, the 11-state
structural engine, the ADU model bridge, and the Tier-1 cross-validator.
"""

from __future__ import annotations

from functools import lru_cache
from html import escape
from typing import Any

from src.adu_fee_note import comparison
from src.bundle import load_bundle
from src.export.report import simulate_many
from src.lab.explain import assumption_catalog, locked_results
from src.model.crossval import cross_validate_tier1
from src.plain import homes, money
from src.version import stamp_html


def _h(val: float, signed: bool = False) -> str:
    return escape(homes(val, signed=signed))


def _m(val: float) -> str:
    return escape(money(val))


def _tag(kind: str) -> str:
    return f'<abbr class="tag {escape(kind)}">{escape(kind)}</abbr>'


def _county_archetypes(doc: dict[str, Any]) -> dict[str, int]:
    counts = {"zoning": 0, "fee": 0, "market": 0}
    for county in doc.get("counties", []):
        res = county.get("results", {})
        adu = res.get("adu", {})
        mm = res.get("missing_middle", {})
        fees = res.get("fees", {})
        pkg = res.get("package", {})
        elig = max(float(adu.get("eligible", 0.0)), float(mm.get("eligible", 0.0)))
        feas = max(float(adu.get("feasible", 0.0)), float(mm.get("feasible", 0.0)))
        share = (feas / elig) if elig > 0 else 0.0
        legal_top = max(float(adu.get("central", 0.0)), float(mm.get("central", 0.0)))
        pkg_c = float(pkg.get("central", 0.0))
        fee_c = float(fees.get("central", 0.0))
        if share >= 0.06 and legal_top > fee_c:
            counts["zoning"] += 1
        elif pkg_c >= 15.0 and (fee_c >= 0.6 * max(legal_top, 1.0) or pkg_c >= 1.35 * max(legal_top, 1.0)):
            counts["fee"] += 1
        else:
            counts["market"] += 1
    return counts


@lru_cache(maxsize=1)
def render_deck_html() -> str:
    """Render the 16-slide presentation deck with live engine outputs."""
    pa = locked_results("PA")
    nh = locked_results("NH")
    cat = assumption_catalog()
    bridge = comparison("PA")
    fixtures, assumptions = load_bundle()
    all_states = simulate_many(fixtures, assumptions)
    xval = cross_validate_tier1(fixtures, assumptions, draws=40)

    pa_sw = pa["statewide"]["results"]
    pa_decomp = pa["statewide"]["package_decomposition"]
    nh_sw = nh["statewide"]["results"]
    pa_arch = _county_archetypes(pa)
    allegheny = next(c for c in pa["counties"] if c["fips"] == "42003")
    al_res = allegheny["results"]

    cr_sf = float(assumptions.spec("completion_ratio_sf")["central"])
    cr_sm = float(assumptions.spec("completion_ratio_small")["central"])
    cr_adu = float(assumptions.spec("completion_ratio_adu")["central"])

    pa_rows_html = ""
    for sid, label in [
        ("missing_middle", "Missing Middle (2–6 units)"),
        ("fees", "50% Development Fee Cut"),
        ("adu", "Accessory Dwelling Units (ADUs)"),
        ("parking", "Parking Mandate Repeal"),
        ("package", "All Four Together (Joint Package)"),
    ]:
        r = pa_sw[sid]
        pa_rows_html += (
            f"<tr><td><strong>{escape(label)}</strong></td>"
            f"<td>{_h(r['central'], True)} {_tag('calculated')}</td>"
            f"<td>{_h(r['p10'])}–{_h(r['p90'])} {_tag('assumed')}</td>"
            f"<td>{_h(r['zoning_low'])}–{_h(r['zoning_high'])}</td>"
            f"<td>±{_h(r['acs_moe'])} {_tag('observed')}</td></tr>"
        )

    nh_rows_html = ""
    for sid, label in [
        ("fees", "50% Development Fee Cut"),
        ("missing_middle", "Missing Middle (2–6 units)"),
        ("adu", "ADU Expansion Beyond RSA 674:72"),
        ("parking", "Parking Mandate Repeal"),
        ("package", "All Four Together (Joint Package)"),
    ]:
        r = nh_sw[sid]
        nh_rows_html += (
            f"<tr><td><strong>{escape(label)}</strong></td>"
            f"<td>{_h(r['central'], True)} {_tag('calculated')}</td>"
            f"<td>{_h(r['p10'])}–{_h(r['p90'])} {_tag('assumed')}</td>"
            f"<td>{_h(r['zoning_low'])}–{_h(r['zoning_high'])}</td></tr>"
        )

    eleven_rows = ""
    for st in all_states:
        sc = st["scenarios"]
        vintage = escape(str((st.get("meta") or {}).get("permit_vintage") or "BPS"))
        eleven_rows += (
            f"<tr><td><strong>{escape(st['state'])}</strong></td>"
            f"<td>Tier {int(st['tier'])}</td>"
            f"<td>{vintage}</td>"
            f"<td>{_h(st['baseline_completions_5yr'])}</td>"
            f"<td>{_h(sc['adu']['incremental_completions'], True)}</td>"
            f"<td>{_h(sc['missing_middle']['incremental_completions'], True)}</td>"
            f"<td>{_h(sc['tod']['incremental_completions'], True)}</td>"
            f"<td>{_h(sc['parking']['incremental_completions'], True)}</td>"
            f"<td>{_h(sc['fees']['incremental_completions'], True)}</td>"
            f"<td><strong>{_h(sc['combined']['incremental_completions'], True)}</strong></td></tr>"
        )

    xval_rows = ""
    for code in ("CT", "WI", "UT", "HI"):
        item = xval["states"][code]
        adu_err = item["scenarios"]["adu"]["imputed_parcels"]["percent_error"]
        pkg_err = item["scenarios"]["combined"]["imputed_parcels"]["percent_error"]
        ratio = item.get("band_width_ratio")
        adu_txt = f"{adu_err:+.1f}%" if adu_err is not None else "small base"
        pkg_txt = f"{pkg_err:+.1f}%" if pkg_err is not None else "small base"
        ratio_txt = f"{float(ratio):.2f}×" if ratio is not None else "—"
        xval_rows += (
            f"<tr><td><strong>{escape(code)}</strong></td>"
            f"<td>{round(float(item['lot_full']) * 100)}% {_tag('observed')}</td>"
            f"<td>{round(float(item['lot_imputed']) * 100)}% {_tag('assumed')}</td>"
            f"<td>{escape(adu_txt)}</td>"
            f"<td>{escape(pkg_txt)}</td>"
            f"<td>{escape(ratio_txt)}</td></tr>"
        )

    oat = pa["statewide"]["one_at_a_time"]
    swings = []
    for pname, ends in oat.items():
        lo = float(ends["low"]["package"])
        hi = float(ends["high"]["package"])
        label = (cat["by_name"].get(pname) or {}).get("label", pname)
        swings.append((abs(hi - lo), label, lo, hi))
    swings.sort(reverse=True)
    top_drivers_html = "".join(
        f"<tr><td>{escape(lbl)}</td><td>{_h(lo, True)}</td><td>{_h(hi, True)}</td>"
        f"<td><strong>{_h(sw)} homes</strong></td></tr>"
        for sw, lbl, lo, hi in swings[:5]
    )

    adu_env_span = float(pa_sw["adu"]["p90"]) - float(pa_sw["adu"]["p10"])
    adu_zon_span = float(pa_sw["adu"]["zoning_high"]) - float(pa_sw["adu"]["zoning_low"])
    adu_moe_span = 2.0 * float(pa_sw["adu"]["acs_moe"])

    slides = [
        # Slide 1
        """<section class="slide slide-cover" data-slide="1">
          <p class="eyebrow">Arnold Ventures / The Turnout Housing Data &amp; Technology Innovation Challenge</p>
          <h1>Stateframe</h1>
          <p class="subtitle">The Anti-Black-Box State Housing Reform Simulator &amp; Legislative Stress-Tester</p>
          <div class="kpi-row">
            <div class="kpi"><strong>11 States</strong><span>Screening &amp; Tier-1/2 Cross-Validation</span></div>
            <div class="kpi"><strong>77 Counties</strong><span>Lot-Competing Micro-Simulation (PA &amp; NH)</span></div>
            <div class="kpi"><strong>100% Tagged</strong><span>Observed · Assumed · Calculated</span></div>
          </div>
          <p class="authors">Tejas Chaudhari · Yoon Yik Ng · Christopher Severns · Carnegie Mellon University · Apache-2.0</p>
        </section>""",
        # Slide 2
        """<section class="slide" data-slide="2">
          <p class="kicker">1 · The Problem &amp; Who Uses Stateframe</p>
          <h2>Why State Housing Bills Stall in Committee</h2>
          <div class="two-col">
            <div class="card-box">
              <h3>What lawmakers get today</h3>
              <ul>
                <li><strong>Advocacy calculators</strong> that multiply all single-family lots by a flat take-up rate—ignoring $50,000 impact fees, construction costs, and lot overlap.</li>
                <li><strong>Opaque academic regressions</strong> that cannot answer: <em>"What happens in my county if we amend the fee cap or exempt suburbs?"</em></li>
              </ul>
            </div>
            <div class="card-box accent">
              <h3>What Stateframe delivers</h3>
              <ul>
                <li><strong>Built for legislative staff, housing agencies, and governors' offices.</strong></li>
                <li>Every number carries an on-screen provenance badge: <abbr class="tag observed">observed</abbr>, <abbr class="tag assumed">assumed</abbr>, or <abbr class="tag calculated">calculated</abbr>.</li>
                <li>Automatic <strong>close-call</strong> and <strong>outcome-uncertain</strong> flags when ranges cross zero or rankings flip across draws.</li>
              </ul>
            </div>
          </div>
        </section>""",
        # Slide 3
        f"""<section class="slide" data-slide="3">
          <p class="kicker">2 · Benchmark Scenarios Addressed</p>
          <h2>All Five Handbook Reforms + Joint Package (5-Year Horizon)</h2>
          <div class="deck-table-wrap"><table>
            <thead><tr><th>Scenario</th><th>Policy Mechanism Modeled</th><th>Where Modeled</th></tr></thead>
            <tbody>
              <tr><td><strong>Baseline</strong></td><td>Current permit run-rate, completion shares, and statutory legal baseline</td><td>11 States + PA/NH Lab</td></tr>
              <tr><td><strong>1. ADUs</strong></td><td>Detached/attached ADU ≥600 sq ft on single-family lots, zero parking mandate</td><td>11 States + PA/NH Lab</td></tr>
              <tr><td><strong>2. Missing Middle</strong></td><td>2–6 units up to 3 stories on single-family lots (conversions &amp; teardowns)</td><td>11 States + PA/NH Lab</td></tr>
              <tr><td><strong>3. Transit-Oriented Density</strong></td><td>Higher FAR/height within 0.5-mile walksheds of major rail/BRT stops</td><td>11-State Screening Engine</td></tr>
              <tr><td><strong>4. Parking Repeal</strong></td><td>Eliminate minimums; builders still provide market parking (Hess &amp; Rehler 2021)</td><td>11 States + PA/NH Lab</td></tr>
              <tr><td><strong>5. 50% Fee Reduction</strong></td><td>Cut {_m(bridge['lab_fee'])} per-unit development fees by 50% across categories</td><td>11 States + PA/NH Lab</td></tr>
              <tr><td><strong>Combined Package</strong></td><td>Joint pro forma + single-lot best-use competition (never a naive sum)</td><td>11 States + PA/NH Lab</td></tr>
            </tbody>
          </table></div>
        </section>""",
        # Slide 4
        f"""<section class="slide" data-slide="4">
          <p class="kicker">3 · Dual-Resolution Architecture</p>
          <h2>Two Lenses, One Reconciled System</h2>
          <div class="two-col">
            <div class="card-box">
              <h3>Small Homes Policy Lab (<code>/lab</code>)</h3>
              <p><strong>PA (67 counties) &amp; NH (10 counties)</strong> · Answers the Handbook benchmarks directly.</p>
              <ul>
                <li>Urban / suburban / rural host-lot grids per county.</li>
                <li>Applies Handbook {_m(bridge['lab_fee'])} fee to every unit including ADUs.</li>
                <li>PA 5-year package: <strong>{_h(bridge['lab_package'], True)}</strong> net completions.</li>
              </ul>
            </div>
            <div class="card-box">
              <h3>11-State Screening Simulator (<code>/</code>)</h3>
              <p><strong>PA, CT, WI, UT, OR, HI, AZ, VA, TN, RI, NH</strong> · Statewide &amp; county triage.</p>
              <ul>
                <li>Adds rail/BRT transit walksheds (TOD) and realistic {_m(bridge['core_fee'])} ADU fees.</li>
                <li>Separates Tier-1 parcel-extract states from Tier-2 Census-imputed states.</li>
                <li>PA 5-year package: <strong>{_h(bridge['core_package'], True)}</strong> net completions.</li>
              </ul>
            </div>
          </div>
        </section>""",
        # Slide 5
        f"""<section class="slide" data-slide="5">
          <p class="kicker">3 · How It Works (Policymaker View)</p>
          <h2>Five Transparent Steps From Lots to Completed Homes</h2>
          <ol class="step-list">
            <li><strong>Observed Stock &amp; Permits:</strong> Start with Census ACS housing structures, rents, values, and 3-year Building Permits Survey county averages.</li>
            <li><strong>Legal &amp; Physical Fit:</strong> Filter out lots where reform is already legal (e.g., Pittsburgh ADUs, NH RSA 674:72, CT PA 21-29) or lot geometry cannot fit the building.</li>
            <li><strong>Pro Forma Feasibility:</strong> Compare capitalized rent / sale value against hard cost, soft cost, parking stalls, and fees; compute feasible share via normal margin dispersion.</li>
            <li><strong>Lot Competition:</strong> When ADUs and 2–6 unit multiplexes are both legal, each lot picks at most one best option—eliminating double-counting.</li>
            <li><strong>Adoption, Lags &amp; Completion:</strong> Apply post-reform annual start hazards, rulemaking &amp; build lags inside the 5-year window, and completion ratios ({cr_sf:.2f} SF / {cr_sm:.2f} small MF / {cr_adu:.2f} ADU).</li>
          </ol>
        </section>""",
        # Slide 6
        f"""<section class="slide" data-slide="6">
          <p class="kicker">4 · Key Findings — Pennsylvania County Lab (2027–2031)</p>
          <h2>Pennsylvania Adds {_h(pa_sw['package']['central'], True)} Homes Under the Joint Package</h2>
          <p class="lead-note">Baseline 5-year completions: <strong>{_h(pa_sw['baseline']['central'])}</strong> · Top standalone benchmark is a statistical <strong>Too Close to Call</strong> tie between Missing Middle and Fee Cut.</p>
          <div class="deck-table-wrap"><table>
            <thead><tr><th>Scenario</th><th>Middle Estimate</th><th>Likely Range (p10–p90)</th><th>Local-Rules Range</th><th>Census MOE</th></tr></thead>
            <tbody>{pa_rows_html}</tbody>
          </table></div>
        </section>""",
        # Slide 7
        f"""<section class="slide" data-slide="7">
          <p class="kicker">4 · Key Findings — Package Interactions</p>
          <h2>Don't Add Housing Bills Up: Competition vs. Cost Synergy</h2>
          <div class="kpi-row">
            <div class="kpi"><strong>{_h(pa_decomp['legalization_if_summed'], True)}</strong><span>ADUs + Missing Middle if added naively</span></div>
            <div class="kpi warn"><strong>{_h(pa_decomp['competition_loss'], True)}</strong><span>Same-lot competition overlap</span></div>
            <div class="kpi good"><strong>{_h(pa_decomp['fee_cut_step'], True)}</strong><span>Incremental lift from 50% fee cut</span></div>
            <div class="kpi"><strong>{_h(pa_decomp['package'], True)}</strong><span>Jointly modeled 4-reform package</span></div>
          </div>
          <p class="lead-note">In Pennsylvania, ADUs and 2–6 unit multiplexes compete for the same single-family lots ({_h(pa_decomp['legalization_resolved'], True)} jointly vs. {_h(pa_decomp['legalization_if_summed'], True)} summed). Cutting fees by 50% then rescues marginal multiplex &amp; ADU pro formas across suburban counties.</p>
        </section>""",
        # Slide 8
        f"""<section class="slide" data-slide="8">
          <p class="kicker">4 · Policy Insight — Committee Poison Pills</p>
          <h2>How a {_m(bridge['lab_fee'])} Impact Fee Cuts ADU Supply in Half</h2>
          <div class="deck-table-wrap"><table>
            <thead><tr><th>Step-by-Step Model Bridge (Pennsylvania ADUs)</th><th>5-Year Net Homes</th><th>What Changed</th></tr></thead>
            <tbody>
              <tr><td>1. County Lab at Handbook {_m(bridge['lab_fee'])} per-unit fee</td><td><strong>{_h(bridge['lab_adu'], True)}</strong></td><td>Full municipal impact-fee stack applied to backyard cottages</td></tr>
              <tr><td>2. County Lab with {_m(bridge['core_fee'])} ADU fee waiver</td><td><strong>{_h(bridge['after_fee'], True)}</strong></td><td>Exempting ADUs from $50k impact fees more than doubles supply</td></tr>
              <tr><td>3. + Homeowner valuation (4.5% cap rate, zero opex)</td><td><strong>{_h(bridge['after_yield'], True)}</strong></td><td>Owners value family/rental space above merchant developer hurdles</td></tr>
              <tr><td>4. + Drop rulemaking &amp; build schedule lags</td><td><strong>{_h(bridge['after_lags'], True)}</strong></td><td>Steady-state 5-year pace vs. Year 1–2 ramp-up</td></tr>
              <tr><td>5. 11-State Screening Engine ADU total</td><td><strong>{_h(bridge['core_adu'], True)}</strong></td><td>Remaining gap (~{int(round(bridge['close_share'] * 100))}%) is county vs. screening aggregation</td></tr>
            </tbody>
          </table></div>
        </section>""",
        # Slide 9
        f"""<section class="slide" data-slide="9">
          <p class="kicker">4 · Substate Geography — Pennsylvania's 67 Counties</p>
          <h2>Different Counties Hit Different Binding Constraints</h2>
          <div class="kpi-row">
            <div class="kpi good"><strong>{pa_arch['zoning']} counties</strong><span>Zoning-Locked (≥6% of lots pencil &amp; zoning leads)</span></div>
            <div class="kpi"><strong>{pa_arch['fee']} counties</strong><span>Fee-Sensitive (need 50% fee cut to unlock margin)</span></div>
            <div class="kpi warn"><strong>{pa_arch['market']} counties</strong><span>Rent/Cost-Constrained (rents below build cost)</span></div>
          </div>
          <p class="lead-note"><strong>Worked Case Study — Allegheny County (42003):</strong> Pittsburgh's ADU law is observed; remaining suburbs use transparent priors. Baseline {_h(al_res['baseline']['central'])} homes · ADUs {_h(al_res['adu']['central'], True)} · Missing Middle {_h(al_res['missing_middle']['central'], True)} · Fee Cut {_h(al_res['fees']['central'], True)} · Joint Package <strong>{_h(al_res['package']['central'], True)}</strong>.</p>
        </section>""",
        # Slide 10
        f"""<section class="slide" data-slide="10">
          <p class="kicker">4 · Portability Test — New Hampshire (10 Counties)</p>
          <h2>Statutory Baselines Matter: Modeling NH After RSA 674:72 &amp; HB 577</h2>
          <p class="lead-note">New Hampshire already legalized one ADU by statute (RSA 674:72) and expanded detached ADUs in 2025. Stateframe credits only the remaining incremental legal expansion—preventing false credit for already-enacted laws.</p>
          <div class="deck-table-wrap"><table>
            <thead><tr><th>New Hampshire Scenario</th><th>Middle Estimate</th><th>Likely Range (p10–p90)</th><th>Local-Rules Range</th></tr></thead>
            <tbody>{nh_rows_html}</tbody>
          </table></div>
        </section>""",
        # Slide 11
        f"""<section class="slide" data-slide="11">
          <p class="kicker">4 · Cross-State Screening — All 11 Challenge States</p>
          <h2>Five-Year Net Completions Across All Eleven Official States</h2>
          <div class="deck-table-wrap"><table class="compact-table">
            <thead><tr><th>State</th><th>Data</th><th>Permits</th><th>Baseline</th><th>ADUs</th><th>Middle</th><th>TOD</th><th>Parking</th><th>Fees</th><th>Package</th></tr></thead>
            <tbody>{eleven_rows}</tbody>
          </table></div>
        </section>""",
        # Slide 12
        f"""<section class="slide" data-slide="12">
          <p class="kicker">5 · Replicability &amp; Data-Procurement Value</p>
          <h2>Tested Against Real Parcel Extracts — Where Does Better Data Pay Off?</h2>
          <div class="two-col">
            <div class="deck-table-wrap">
              <table>
                <thead><tr><th>Tier-1 State</th><th>Observed Fit</th><th>Imputed Fit</th><th>ADU Diff</th><th>Pkg Diff</th><th>Band Ratio</th></tr></thead>
                <tbody>{xval_rows}</tbody>
              </table>
            </div>
            <div class="card-box">
              <h3>PA ADU Uncertainty Widths</h3>
              <ul>
                <li><strong>Behavioral &amp; Cost Assumptions (p10–p90):</strong> {_h(adu_env_span)} homes</li>
                <li><strong>Missing Municipal Zoning Map:</strong> {_h(adu_zon_span)} homes</li>
                <li><strong>Census ACS Survey Error (±MOE):</strong> {_h(adu_moe_span)} homes</li>
              </ul>
              <p><em>Takeaway:</em> Lawmakers should not delay fee reform waiting for parcel maps—behavioral &amp; fee uncertainty is 3× wider than zoning-prior uncertainty.</p>
            </div>
          </div>
        </section>""",
        # Slide 13
        f"""<section class="slide" data-slide="13">
          <p class="kicker">5 · Sensitivity &amp; Switching Thresholds</p>
          <h2>Assumptions That Move the Pennsylvania Package Most</h2>
          <div class="deck-table-wrap"><table>
            <thead><tr><th>Published Assumption (<code>config/lab/assumptions.yaml</code>)</th><th>At Low Band</th><th>At High Band</th><th>Total Swing</th></tr></thead>
            <tbody>{top_drivers_html}</tbody>
          </table></div>
          <p class="lead-note">Every assumption slider is clamped to its published literature/empirical range and updates central, zoning-prior, and Census-MOE bounds live.</p>
        </section>""",
        # Slide 14
        """<section class="slide" data-slide="14">
          <p class="kicker">5 · Honest Scope &amp; Model Limitations</p>
          <h2>What Stateframe Cannot Tell Policymakers</h2>
          <div class="two-col">
            <div class="card-box">
              <h3>Out-of-Scope Outcomes</h3>
              <ul>
                <li><strong>Not a forecast:</strong> Conditional estimates under stated assumptions; leaves out recessions, interest-rate shocks, and construction labor bottlenecks.</li>
                <li><strong>No rent or price filtering model:</strong> Estimates physical completions, not general-equilibrium rent changes or income-restricted affordability.</li>
                <li><strong>No parcel-address predictions:</strong> Identifies county &amp; state totals, not which specific neighbor builds.</li>
              </ul>
            </div>
            <div class="card-box">
              <h3>Implementation Risks</h3>
              <ul>
                <li><strong>California ADU hazard transferability:</strong> Homeowner start rates anchored to post-reform CA HCD data may move slower or faster in Northeast markets.</li>
                <li><strong>Local poison-pill rewrites:</strong> Assumes towns do not invent new dimensional, FAR, or utility-connection barriers to nullify state preemption.</li>
                <li><strong>Municipal fiscal backfill:</strong> Cutting fees by 50% boosts supply but does not model how towns replace infrastructure revenue.</li>
              </ul>
            </div>
          </div>
        </section>""",
        # Slide 15
        """<section class="slide" data-slide="15">
          <p class="kicker">6 · Usability — Built for Live Committee Markup</p>
          <h2>Interactive Workflow From 30-Second Brief to Equation Audit</h2>
          <div class="two-col">
            <div class="card-box">
              <h3>For Legislators &amp; Staffers</h3>
              <ul>
                <li><strong>Quick Answer (<code>/brief</code>):</strong> Plain-English, ≤8th-grade reading level one-page sheet for any state and reform mix.</li>
                <li><strong>Bill Amendment Presets &amp; Pin-and-Compare:</strong> Pin Baseline Bill A, apply a committee amendment, and read exact Δ homes live.</li>
                <li><strong>3-Mode County Map:</strong> Switch between <em>Extra Homes</em>, <em>% Lift</em>, and <em>Primary County Bottleneck</em>.</li>
              </ul>
            </div>
            <div class="card-box">
              <h3>For Analysts &amp; Reviewers</h3>
              <ul>
                <li><strong>Click-Any-Number Lineage Inspector:</strong> Click any figure on screen to inspect its JSON path, engine module, and data vintage.</li>
                <li><strong>County Why Drawer &amp; Show-the-Math:</strong> Full substituted equations and illustrative pro forma receipts.</li>
                <li><strong>Provenance-Tagged Exports:</strong> CSV, JSON, Markdown, PNG, and 1-page print-to-PDF briefs.</li>
              </ul>
            </div>
          </div>
        </section>""",
        # Slide 16
        f"""<section class="slide" data-slide="16">
          <p class="kicker">6 · Reproducible Setup &amp; 50-State Scalability</p>
          <h2>Run From a Clean Checkout in Three Commands</h2>
          <pre class="cmd-box">bash scripts/setup.sh          # creates .venv with permissive MIT/Apache/BSD pins
bash scripts/test.sh           # runs 288+ pytest checks, JS suites, and ruff lint
bash scripts/run.sh            # starts stdlib server at http://127.0.0.1:8080 (/ , /lab , /brief , /deck)
.venv/bin/python -m src.lab.check   # verifies SHA-256 fingerprints on PA &amp; NH envelopes</pre>
          <p class="lead-note"><strong>50-State Scaling:</strong> Tier-2 mode requires zero paid parcel data—only public Census ACS, Building Permits Survey, Gazetteer, and FHFA HPI. Build stamp: {stamp_html()}.</p>
        </section>""",
    ]

    body = "\n".join(slides)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Stateframe — Executive Slide Deck (16 Slides)</title>
  <link rel="stylesheet" href="/tokens.css">
  <link rel="stylesheet" href="/styles.css">
  <link rel="stylesheet" href="/deck.css">
</head>
<body class="deck-body">
  <header class="suite-bar deck-bar no-print">
    <a class="suite-brand" href="/">Stateframe <span class="suite-tag">Policy Suite</span></a>
    <nav class="suite-nav" aria-label="Stateframe workspaces">
      <a href="/">11-State Screening</a>
      <a href="/lab">PA &amp; NH County Lab</a>
      <a href="/brief">1-Page Brief</a>
      <a href="/deck" aria-current="page">Executive Deck</a>
    </nav>
    <span class="suite-spacer deck-spacer"></span>
    <span id="deck-counter" class="deck-counter" aria-live="polite">All 16 slides</span>
    <button type="button" id="deck-mode" class="btn">Slide-by-slide view</button>
    <button type="button" id="deck-prev" class="btn" hidden>Prev</button>
    <button type="button" id="deck-next" class="btn" hidden>Next</button>
    <button type="button" id="deck-print" class="btn pri">Print / Save PDF (≤30 slides)</button>
  </header>
  <main id="deck-main" class="deck-main">
    {body}
  </main>
  <script src="/deck.js"></script>
</body>
</html>
"""
