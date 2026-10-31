# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Pennsylvania incomplete-data walkthrough, anchored on Allegheny County.

Pennsylvania is a tier-2 state in this model: Census, permits, the gazetteer,
and the FHFA index are observed, and the lot-size screen is imputed. Allegheny
County is the worked example. Its pro forma is one row. The official state
total is the sum of all 67 county rows. No Pittsburgh parcel file is used.
"""

from __future__ import annotations

from typing import Any

from src.model.engine import simulate_state
from src.model.provenance import LEGEND, stamp_tree

ALLEGHENY_FIPS = "42003"


def _fmt(value: float, digits: int = 0) -> str:
    if digits == 0:
        return f"{value:,.0f}"
    return f"{value:,.{digits}f}"


def _field(label: str, value: float, tag: str, source: str, plain: str) -> dict[str, Any]:
    return {"label": label, "value": value, "tag": tag, "source": source, "plain": plain}


def build_case_study(
    fixtures: dict[str, Any],
    assumptions: Any,
    overrides: dict[str, Any] | None = None,
    reform_weights: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Central (or overridden) Pennsylvania run, told from Allegheny County up."""
    result = simulate_state(
        fixtures,
        assumptions,
        "PA",
        overrides,
        reform_weights=reform_weights,
    )
    raw_state = fixtures["states"]["PA"]
    raw = next(county for county in raw_state["counties"] if county["fips"] == ALLEGHENY_FIPS)
    allegheny = next(county for county in result["counties"] if county["fips"] == ALLEGHENY_FIPS)
    params = assumptions.resolve("PA", overrides)
    rounded_baseline = round(result["baseline_completions_5yr"])
    rounded_package = round(result["scenarios"]["combined"]["incremental_completions"])
    baseline_sum = sum(county["baseline_completions"] for county in result["counties"])
    package_sum = sum(county["combined"] for county in result["counties"])
    share = 0.0 if rounded_package == 0 else allegheny["combined"] / rounded_package
    annual_permits = raw["bps_sf"] + raw["bps_two"] + raw["bps_three_four"] + raw["bps_five_plus"]

    observed = {
        "kind": "observed",
        "value_imputed": bool(raw["value_imputed"]),
        "housing_units": raw["housing_units"],
        "sf_detached": raw["sf_detached"],
        "sf_attached": raw["sf_attached"],
        "median_value": raw["median_value"],
        "median_rent": raw["median_rent"],
        "median_income": raw["median_income"],
        "pre1940_share": raw["pre1940_share"],
        "transit_commute_share": raw["transit_commute_share"],
        "land_sqmi": raw["land_sqmi"],
        "bps_sf": raw["bps_sf"],
        "bps_two": raw["bps_two"],
        "bps_three_four": raw["bps_three_four"],
        "bps_five_plus": raw["bps_five_plus"],
        "population": raw["population"],
        "county_count": len(raw_state["counties"]),
    }
    assumed = {
        "kind": "assumptions",
        "imputed_lot_feasible_share": params["imputed_lot_feasible_share"],
        "fee_challenge_baseline": params["fee_challenge_baseline"],
        "fee_reduction_fraction": params["fee_reduction_fraction"],
        "supply_elasticity": params["supply_elasticity"],
        "adu_cost_psf": params["adu_cost_psf"],
        "adu_sqft": params["adu_sqft"],
        "adu_already_legal_share": params["adu_already_legal_share"],
        "mm_already_legal_share": params["mm_already_legal_share"],
        "geography_eligible_share": params["geography_eligible_share"],
        "feasibility_threshold": params["feasibility_threshold"],
    }
    calculated = {
        "kind": "calculated",
        "allegheny_baseline_completions": allegheny["baseline_completions"],
        "allegheny_adu": allegheny["adu"],
        "allegheny_missing_middle": allegheny["missing_middle"],
        "allegheny_tod": allegheny["tod"],
        "allegheny_parking": allegheny["parking"],
        "allegheny_fees": allegheny["fees"],
        "allegheny_package": allegheny["combined"],
        "state_baseline_completions": result["baseline_completions_5yr"],
        "state_adu": result["scenarios"]["adu"]["incremental_completions"],
        "state_missing_middle": result["scenarios"]["missing_middle"]["incremental_completions"],
        "state_tod": result["scenarios"]["tod"]["incremental_completions"],
        "state_parking": result["scenarios"]["parking"]["incremental_completions"],
        "state_fees": result["scenarios"]["fees"]["incremental_completions"],
        "state_package": result["scenarios"]["combined"]["incremental_completions"],
        "allegheny_share_of_package": share,
        "annual_permits": annual_permits,
        "rounded_state_baseline": float(rounded_baseline),
        "rounded_state_package": float(rounded_package),
        "county_sum_baseline": float(baseline_sum),
        "county_sum_package": float(package_sum),
    }
    value_tag = "assumed" if raw["value_imputed"] else "observed"
    value_plain = (
        "Allegheny County's ACS median was suppressed, so the model fills the state median and tags it assumed."
        if raw["value_imputed"]
        else "Allegheny County publishes an ACS median home value. It is observed, not filled from the state."
    )
    fields = [
        _field(
            "Housing units",
            raw["housing_units"],
            "observed",
            "ACS 2019–2023 table B25001, Allegheny County",
            "The county's housing stock is a Census count. The pro forma starts here, not from a parcel file.",
        ),
        _field(
            "Median home value",
            raw["median_value"],
            value_tag,
            "ACS 2019–2023 table B25077",
            value_plain,
        ),
        _field(
            "Median gross rent",
            raw["median_rent"],
            "observed",
            "ACS 2019–2023 table B25064",
            "Rent is the other observed price. ADU value and missing-middle rent both read it.",
        ),
        _field(
            "Annual permits, all types",
            annual_permits,
            "calculated",
            "Building Permits Survey, 2022–2024 county files, reconciled to the state file",
            "The four permit segments are observed. Adding them is arithmetic, so the total is calculated.",
        ),
        _field(
            "Imputed lot screen",
            params["imputed_lot_feasible_share"],
            "assumed",
            "config/assumptions.yaml imputed_lot_feasible_share",
            "Pennsylvania has no lot-size extract in this model. The share of lots that can hold a 600 sq ft ADU is the published imputation, borrowed from the tier-1 screening range.",
        ),
        _field(
            "Challenge fee stack",
            params["fee_challenge_baseline"],
            "assumed",
            "Challenge comparability assumption, not a Pennsylvania fee study",
            "The fee scenario cuts half of a $50,000 stack. That stack is not a measurement of Allegheny County's fees.",
        ),
        _field(
            "Already-legal ADU share",
            params["adu_already_legal_share"],
            "assumed",
            "State legal-baseline assumption for Pennsylvania",
            "Zoning is still mostly municipal. The model assumes only a small share of lots already have the benchmark ADU right.",
        ),
        _field(
            "Allegheny baseline completions",
            float(allegheny["baseline_completions"]),
            "calculated",
            "County permit run-rate times the completion ratios, then largest-remainder rounding",
            "This is Allegheny's piece of the five-year baseline. It is not a new policy.",
        ),
        _field(
            "Allegheny package, net completions",
            float(allegheny["combined"]),
            "calculated",
            "County pro forma after overlap, rounded so counties sum to the state",
            "ADUs, missing middle, transit-oriented density, parking, and the fee cut, with walkshed overlap removed.",
        ),
        _field(
            "Pennsylvania package, net completions",
            result["scenarios"]["combined"]["incremental_completions"],
            "calculated",
            "Sum of 67 county pro formas",
            "The official state number. It is not the pro forma evaluated at the state median price.",
        ),
    ]
    steps = [
        {
            "id": "question",
            "title": "Start with one county, end with the state",
            "body": (
                "Pennsylvania is a tier-2 state in Stateframe. The public inputs are the American Community Survey, "
                "the Building Permits Survey, population estimates, the county gazetteer, and the FHFA house-price index. "
                f"There is no statewide parcel extract, so lot size is imputed. Allegheny County "
                f"({_fmt(raw['housing_units'])} homes, observed) is the county this note walks. "
                f"The other {len(raw_state['counties']) - 1} counties use the same equations. "
                "The state total is their sum. The on-screen equation trace still opens on the largest county, "
                "which is Philadelphia, because that is where the most homes are. "
                "This walkthrough does not use a Pittsburgh parcel file."
            ),
        },
        {
            "id": "observed",
            "title": "What Allegheny County actually measures",
            "body": (
                f"Housing units, structure mix, median value (${_fmt(raw['median_value'])}, {value_tag}), "
                f"median rent (${_fmt(raw['median_rent'])}, observed), income, the pre-1940 share, and the transit-commute share "
                "come from ACS 2019–2023 summary tables. Annual permits come from the Building Permits Survey "
                f"for 2022–2024, about {_fmt(annual_permits)} units a year (calculated from observed segments) after the county file is reconciled to the state file. "
                "Land area and the interior point on the map come from the 2024 Census gazetteer. "
                "The state price path comes from the FHFA index. None of these is a modeled household."
            ),
        },
        {
            "id": "imputed",
            "title": "What is imputed because the parcel file is missing",
            "body": (
                f"The lot screen is {_fmt(100 * params['imputed_lot_feasible_share'], 0)} percent (assumed) in the central case. "
                "That number is an assumption: the midpoint of the Connecticut and Wisconsin screening shares, "
                "not a measurement of Allegheny lots. "
                f"The model also assumes that about {_fmt(100 * params['adu_already_legal_share'], 0)} percent of "
                "single-family lots already have the benchmark ADU right, because Pennsylvania has not preempted local zoning. "
                f"The fee scenario uses a ${_fmt(params['fee_challenge_baseline'])} stack and a "
                f"{_fmt(100 * params['fee_reduction_fraction'], 0)} percent cut. "
                "Those are challenge comparability assumptions. Construction cost per square foot, the supply elasticity, "
                "and the feasibility hurdle are assumptions too. Move the lot-share slider to see only the ADU path change."
            ),
        },
        {
            "id": "county",
            "title": "The Allegheny County pro forma",
            "body": (
                f"Under current rules, Allegheny's rounded five-year baseline is {_fmt(allegheny['baseline_completions'])} completions (calculated). "
                f"On top of that, the standalone reforms add about {_fmt(allegheny['adu'])} ADU completions (calculated), "
                f"{_fmt(allegheny['missing_middle'])} missing-middle completions (calculated), {_fmt(allegheny['tod'])} transit-oriented completions (calculated), "
                f"{_fmt(allegheny['parking'])} from parking reform (calculated), and {_fmt(allegheny['fees'])} from the fee cut (calculated). "
                f"The package, after overlap, is {_fmt(allegheny['combined'])} net completions (calculated). "
                "Each of those reform figures is calculated. The prices and the stock underneath them are observed. "
                "The lot screen and the fee stack underneath them are assumed. "
                + (
                    allegheny["close_call_reason"]
                    if allegheny["close_call"]
                    else "Allegheny's margins are not sitting on the feasibility hurdle in the central case."
                )
            ),
        },
        {
            "id": "rollup",
            "title": "Sixty-seven counties become Pennsylvania",
            "body": (
                f"Largest-remainder rounding forces the county integers to add up to the rounded state total. "
                f"Baseline completions: the counties sum to {_fmt(baseline_sum)}, and the rounded state total is {_fmt(rounded_baseline)}. "
                f"Package net completions: the counties sum to {_fmt(package_sum)}, and the rounded state total is {_fmt(rounded_package)}. "
                f"Allegheny County is {_fmt(100 * share, 1)} percent of that package. "
                f"The unrounded state package is {_fmt(result['scenarios']['combined']['incremental_completions'])} net completions over five years. "
                "A single pro forma at Pennsylvania's median price would not reproduce that total, because feasibility is curved. "
                "That is why the official result is the sum."
            ),
        },
        {
            "id": "missing",
            "title": "What a parcel extract would change, and what it would not",
            "body": (
                "A public lot-size extract for Pennsylvania would retag the lot screen from assumed to calculated-from-observed-bins, "
                "the way Connecticut and Wisconsin already work. It would not replace the ACS prices, the permit run-rate, "
                "or the rule that counties sum to the state. It would also not turn the $50,000 fee stack into a measurement. "
                "Until that extract is in the benchmark, completeness stays below the tier-1 states and this page is the "
                "incomplete-data case: the same equations, with the missing field labeled instead of invented."
            ),
        },
    ]
    study = {
        "state": "PA",
        "state_name": "Pennsylvania",
        "county_fips": ALLEGHENY_FIPS,
        "county_name": allegheny["name"],
        "tier": result["tier"],
        "focus_county": result["focus_county"],
        "value_imputed": bool(raw["value_imputed"]),
        "counties_sum_to_state": baseline_sum == rounded_baseline and package_sum == rounded_package,
        "legal_note": assumptions.states["PA"].get("legal_note", ""),
        "lot_feasible_note": result["lot_feasible_note"],
        "observed": observed,
        "assumed": assumed,
        "calculated": calculated,
        "fields": fields,
        "steps": steps,
        "explanations": {key: result["scenarios"][key]["explanation"] for key in result["scenarios"]},
        "provenance_legend": LEGEND,
    }
    return stamp_tree(study)


def render_markdown(study: dict[str, Any]) -> str:
    """The same walkthrough as a document a reviewer can read without the app."""
    observed = study["observed"]
    assumed = study["assumed"]
    calculated = study["calculated"]
    lines = [
        "# Pennsylvania incomplete-data case study: Allegheny County",
        "",
        "Prepared for the Arnold Ventures / The Turnout Housing Data and Technology Innovation Challenge by Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns, Carnegie Mellon University.",
        "",
        "This note is the incomplete-data case. Pennsylvania has no statewide parcel extract in Stateframe. Allegheny County shows how a county pro forma becomes the state total, and which inputs are observed, assumed, or calculated. The figures below are produced by `src/model/case_study.py` from `data/sample/` and `config/assumptions.yaml`. Re-run the tests to confirm they still match the engine.",
        "",
        "PlayHouse, an earlier Pittsburgh parcel explorer, is not a source for this case study. No PlayHouse code, parcel extract, or asset is used. The inputs are public series from the challenge data list.",
        "",
        "## 1. One county, then the state",
        "",
        study["steps"][0]["body"],
        "",
        f"Pennsylvania is tier {study['tier']} (observed classification in the benchmark). The legal screening note is an assumption: {study['legal_note']}",
        "",
        "## 2. Observed inputs for Allegheny County",
        "",
        study["steps"][1]["body"],
        "",
        "| Figure | Value | Tag | Source |",
        "| ------ | ----: | --- | ------ |",
        f"| Housing units | {_fmt(observed['housing_units'])} | observed | ACS 2019–2023 B25001 |",
        f"| Single-family detached | {_fmt(observed['sf_detached'])} | observed | ACS 2019–2023 B25024 |",
        f"| Single-family attached | {_fmt(observed['sf_attached'])} | observed | ACS 2019–2023 B25024 |",
        f"| Median home value | ${_fmt(observed['median_value'])} | {'assumed' if study['value_imputed'] else 'observed'} | ACS 2019–2023 B25077 |",
        f"| Median gross rent | ${_fmt(observed['median_rent'])} | observed | ACS 2019–2023 B25064 |",
        f"| Median household income | ${_fmt(observed['median_income'])} | observed | ACS 2019–2023 B19013 |",
        f"| Pre-1940 share of units | {observed['pre1940_share']:.1%} | observed | ACS 2019–2023 B25034 |",
        f"| Public-transit commute share | {observed['transit_commute_share']:.1%} | observed | ACS 2019–2023 B08301 |",
        f"| Land area | {observed['land_sqmi']:,.1f} sq mi | observed | Census 2024 county gazetteer |",
        f"| Annual single-family permits | {_fmt(observed['bps_sf'], 1)} | observed | BPS 2022–2024, reconciled to the state |",
        f"| Annual 2-unit permits | {_fmt(observed['bps_two'], 1)} | observed | BPS 2022–2024, reconciled to the state |",
        f"| Annual 3–4 unit permits | {_fmt(observed['bps_three_four'], 1)} | observed | BPS 2022–2024, reconciled to the state |",
        f"| Annual 5+ unit permits | {_fmt(observed['bps_five_plus'], 1)} | observed | BPS 2022–2024, reconciled to the state |",
        f"| Counties in the state sum | {int(observed['county_count'])} | observed | Census geography for Pennsylvania |",
        "",
        "County permit segments are the Building Permits Survey. They are scaled so the counties add up to the state permit file. That cleaning step is documented in `docs/DATA_PROVENANCE.md`. The segments stay tagged observed because they are the survey, reconciled, not a policy scenario.",
        "",
        "## 3. Assumed, because a parcel extract is not in the model",
        "",
        study["steps"][2]["body"],
        "",
        "| Figure | Central value | Tag | Why it is not a measurement |",
        "| ------ | ------------: | --- | --------------------------- |",
        f"| Share of lots that can hold an ADU | {assumed['imputed_lot_feasible_share']:.0%} | assumed | No Pennsylvania lot-size bins. The central value is the tier-1 screening imputation. |",
        f"| Share of lots already allowed an ADU | {assumed['adu_already_legal_share']:.0%} | assumed | Statewide preemption is limited. This is a legal screen, not an ordinance census. |",
        f"| Share of lots already allowed missing middle | {assumed['mm_already_legal_share']:.0%} | assumed | Same legal screen. |",
        f"| Geographically eligible share of the single-family stock | {assumed['geography_eligible_share']:.0%} | assumed | No urban-growth or sewer boundary is ingested for Pennsylvania. |",
        f"| ADU hard cost | ${assumed['adu_cost_psf']:,.0f} per sq ft | assumed | National cost assumption, indexed by the state's permit valuation. |",
        f"| ADU size | {_fmt(assumed['adu_sqft'])} sq ft | assumed | Benchmark size. |",
        f"| Fee stack in the fee scenario | ${_fmt(assumed['fee_challenge_baseline'])} | assumed | Challenge comparability case. Not Allegheny County's fee schedule. |",
        f"| Fee cut | {assumed['fee_reduction_fraction']:.0%} | assumed | The benchmark cut. |",
        f"| Supply elasticity | {assumed['supply_elasticity']:.2f} | assumed | Turns a cost saving into extra baseline permits. |",
        f"| Feasibility hurdle | {assumed['feasibility_threshold']:.2f} | assumed | A site clears when residual margin exceeds this. Central is zero. |",
        "",
        f"Lot-screen note from the engine: {study['lot_feasible_note']}",
        "",
        "## 4. Calculated county results",
        "",
        study["steps"][3]["body"],
        "",
        "Integer units use largest-remainder rounding. Tags on this table are calculated.",
        "",
        "| Pathway | Allegheny County | Pennsylvania |",
        "| ------- | ---------------: | -----------: |",
        f"| Baseline completions, 5 years | {_fmt(calculated['allegheny_baseline_completions'])} | {_fmt(calculated['state_baseline_completions'])} |",
        f"| ADUs, net | {_fmt(calculated['allegheny_adu'])} | {_fmt(calculated['state_adu'])} |",
        f"| Missing middle, net | {_fmt(calculated['allegheny_missing_middle'])} | {_fmt(calculated['state_missing_middle'])} |",
        f"| Transit-oriented density, net | {_fmt(calculated['allegheny_tod'])} | {_fmt(calculated['state_tod'])} |",
        f"| Parking reform, net | {_fmt(calculated['allegheny_parking'])} | {_fmt(calculated['state_parking'])} |",
        f"| Fee reduction, net | {_fmt(calculated['allegheny_fees'])} | {_fmt(calculated['state_fees'])} |",
        f"| Package, net | {_fmt(calculated['allegheny_package'])} | {_fmt(calculated['state_package'])} |",
        "",
        "Plain language for the state package:",
        "",
        study["explanations"]["combined"],
        "",
        "## 5. The sum is the result",
        "",
        study["steps"][4]["body"],
        "",
        f"Counties sum to the rounded state total: {str(study['counties_sum_to_state']).lower()}.",
        "",
        "## 6. What is still missing",
        "",
        study["steps"][5]["body"],
        "",
        "## Provenance",
        "",
        "| Tag | Meaning |",
        "| --- | ------- |",
        f"| observed | {LEGEND['observed']} |",
        f"| assumed | {LEGEND['assumed']} |",
        f"| calculated | {LEGEND['calculated']} |",
        "",
        "Sources, all on the official data list: ACS 2019–2023 5-year summary file; Building Permits Survey annual state and county files, 2022–2024; Census population estimates NST-EST2024; Census 2024 county gazetteer; FHFA All-Transactions state house-price index. Licenses and vintages are in `docs/DATA_PROVENANCE.md`.",
        "",
    ]
    return "\n".join(lines)
