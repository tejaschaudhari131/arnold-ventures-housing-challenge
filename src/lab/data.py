# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Turn acquired extracts into Lab host cells.

A host cell is one (county, context, host type) group of single-family lots.
It carries the observed host count and its ACS margin of error, a lot-size
distribution, the county rents and home value, and legal segments: shares of
the cell with a given observed or unknown legal status per option family.

Suppressed or missing ACS values are imputed from same-state relationships,
flagged ``assumed``, and given a widened margin. They are never set to zero.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.lab.config import (
    CACHE_DIR,
    CONTEXTS,
    HOST_TYPES,
    SAMPLE_DIR,
    load_assumptions,
    load_evidence,
)

ACS_MOE_Z = 1.645  # ACS publishes 90 percent margins of error


@dataclass
class Value:
    """A number with its provenance tag and 90 percent margin of error."""

    value: float
    moe: float
    tag: str  # observed | assumed | calculated
    source: str
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        out = {"value": self.value, "moe": self.moe, "tag": self.tag, "source": self.source}
        if self.note:
            out["note"] = self.note
        return out


@dataclass
class LegalSegment:
    """Share of a host cell that shares one legal record."""

    share: float
    adu: str
    mm: str
    adu_parking: float | None = None  # spaces an allowed ADU must provide, None = rule default
    adu_effective: str | None = None
    mm_effective: str | None = None
    rules: list[str] = field(default_factory=list)


@dataclass
class HostCell:
    county: str
    context: str
    host_type: str
    hosts: Value
    segments: list[LegalSegment]
    lot_bins: list[tuple[float, float, float]] | None = None  # (low_sqft, high_sqft, share), observed


@dataclass
class County:
    fips: str
    name: str
    state: str
    land_sqmi: float
    lat: float | None
    lon: float | None
    rent_1br: Value
    rent_2br: Value
    median_value: Value
    detached: Value
    attached: Value
    housing_units: Value
    bps: dict[str, dict[str, float]]
    cells: list[HostCell]
    hud_fmr: dict[str, float] | None
    imputed: list[str]
    context_units: dict[str, float] = field(default_factory=dict)

    @property
    def bps_avg(self) -> dict[str, float]:
        years = [row for row in self.bps.values() if row]
        keys = ("u1", "v1", "u2", "v2", "u34", "v34", "u5", "v5")
        n = len(self.bps) or 1
        return {k: sum(row.get(k, 0.0) for row in years) / n for k in keys}


@dataclass
class StateData:
    code: str
    name: str
    fips: str
    vintage: dict[str, str]
    counties: list[County]
    evidence: dict[str, Any]
    parking_cap: float | None
    parking_cap_effective: str | None
    source_path: str
    allegheny_lots: dict[str, Any] | None = None

    def county(self, fips_or_name: str) -> County:
        key = fips_or_name.strip().lower()
        for county in self.counties:
            if county.fips == key or county.name.lower() == key or county.name.lower().replace(" county", "") == key:
                return county
        raise KeyError(fips_or_name)


def _data_path(code: str, prefer_cache: bool) -> Path:
    cached = CACHE_DIR / f"{code}.json"
    if prefer_cache and cached.exists():
        return cached
    return SAMPLE_DIR / f"{code}.json"


def _observed(cell: dict[str, Any] | None, source: str) -> tuple[float | None, float | None]:
    if not cell:
        return None, None
    return cell.get("e"), cell.get("m")


def _impute(
    raw: dict[str, Any] | None,
    fallback: float,
    source: str,
    how: str,
    widen: float,
    imputed: list[str],
    name: str,
) -> Value:
    estimate, moe = _observed(raw, source)
    if estimate is not None and estimate > 0:
        if moe is None:
            return Value(estimate, widen * estimate, "observed", source, "margin not published; widened")
        return Value(estimate, moe, "observed", source)
    imputed.append(name)
    return Value(fallback, widen * fallback, "assumed", source, f"suppressed in ACS; imputed from {how}")


def context_of_bin(edge: float, thresholds: dict[str, float]) -> str:
    if edge >= thresholds["urban_min"]:
        return "urban"
    if edge >= thresholds["suburban_min"]:
        return "suburban"
    return "rural"


def _effective_after_window(effective: str | None, lag_years: float, window_end: date) -> bool:
    if not effective:
        return False
    start = date.fromisoformat(effective)
    return (start.toordinal() + lag_years * 365.25) > window_end.toordinal()


def lot_bins_from_wprdc(group: dict[str, Any], edges: list[float]) -> list[tuple[float, float, float]]:
    counts = group["counts"]
    total = sum(counts) or 1
    bins = []
    for i, count in enumerate(counts):
        low = edges[i]
        high = edges[i + 1] if i + 1 < len(edges) else edges[i] * 3
        bins.append((float(low), float(high), count / total))
    return bins


def build_state(raw: dict[str, Any], allegheny: dict[str, Any] | None, source_path: str) -> StateData:
    code = raw["state"]
    doc = load_assumptions()
    widen = float(doc["imputation"]["moe_widen_share"])
    thresholds = doc["context_density"]
    edges = raw["density_edges"]
    for key in ("urban_min", "suburban_min"):
        if thresholds[key] not in edges:
            raise ValueError(f"context threshold {thresholds[key]} is not a density bin edge {edges}")
    evidence = load_evidence(code)
    state_acs = raw["state_acs"]
    s1 = (state_acs.get("rent_1br") or {}).get("e")
    s2 = (state_acs.get("rent_2br") or {}).get("e")
    s_value = (state_acs.get("median_value") or {}).get("e")
    if not (s1 and s2 and s_value):
        raise ValueError(f"{code}: state ACS rent or value row is missing")
    ratio_1_2 = s1 / s2

    places_by_county: dict[str, list[dict[str, Any]]] = {}
    for place in raw.get("places", []):
        places_by_county.setdefault(place["county"], []).append(place)
    rules = evidence.get("rules", [])
    lag = float(doc["params"]["adoption_lag_years"]["central"])
    bps_end = date(max(doc["bps_years"]), 12, 31)

    counties: list[County] = []
    for row in raw["counties"]:
        acs = row["acs"]
        imputed: list[str] = []
        src_rent = "ACS B25031 median gross rent"
        r1_obs = (acs.get("rent_1br") or {}).get("e")
        r2_obs = (acs.get("rent_2br") or {}).get("e")
        rent_1br = _impute(
            acs.get("rent_1br"),
            (r2_obs * ratio_1_2) if r2_obs else s1,
            src_rent + ", 1 bedroom",
            "county 2-bedroom rent x state 1BR/2BR ratio" if r2_obs else "state 1-bedroom median",
            widen, imputed, "rent_1br",
        )
        rent_2br = _impute(
            acs.get("rent_2br"),
            (r1_obs / ratio_1_2) if r1_obs else s2,
            src_rent + ", 2 bedrooms",
            "county 1-bedroom rent / state 1BR/2BR ratio" if r1_obs else "state 2-bedroom median",
            widen, imputed, "rent_2br",
        )
        median_value = _impute(
            acs.get("median_value"), s_value, "ACS B25077 median value", "state median value", widen, imputed, "median_value"
        )
        hu = _impute(acs.get("housing_units"), 0.0, "ACS B25001 housing units", "n/a", widen, imputed, "housing_units")
        detached = _impute(acs.get("detached"), 0.0, "ACS B25024 1-unit detached", "n/a", widen, imputed, "detached")
        attached = _impute(acs.get("attached"), 0.0, "ACS B25024 1-unit attached", "n/a", widen, imputed, "attached")

        # Context split from tract density bins. County ACS totals stay the
        # control; tract sums only set the shares.
        by_context = {ctx: {"detached": 0.0, "attached": 0.0, "housing_units": 0.0} for ctx in CONTEXTS}
        for i, cell in enumerate(row.get("density_bins") or []):
            ctx = context_of_bin(edges[i], thresholds)
            for key in ("detached", "attached", "housing_units"):
                by_context[ctx][key] += cell[key]
        unit_total = sum(by_context[ctx]["housing_units"] for ctx in CONTEXTS)
        context_units = {
            ctx: (by_context[ctx]["housing_units"] / unit_total if unit_total > 0 else (1.0 if ctx == "suburban" else 0.0))
            for ctx in CONTEXTS
        }

        cells: list[HostCell] = []
        county_places = places_by_county.get(row["fips"], [])
        for host_type in HOST_TYPES:
            total_obs = detached if host_type == "detached" else attached
            tract_total = sum(by_context[ctx][host_type] for ctx in CONTEXTS)
            # Place hosts (e.g. Pittsburgh) are allocated to the densest
            # contexts first; the place is a city inside its county.
            remaining_place = {}
            for place in county_places:
                place_hosts = (place.get(host_type) or {}).get("e") or 0.0
                remaining_place[place["rule"]] = place_hosts
            for ctx in CONTEXTS:
                share = by_context[ctx][host_type] / tract_total if tract_total > 0 else (1.0 if ctx == "suburban" else 0.0)
                count = total_obs.value * share
                if count <= 0:
                    continue
                hosts = Value(
                    count,
                    total_obs.moe * share,
                    "observed" if total_obs.tag == "observed" else "assumed",
                    f"{total_obs.source}; {ctx} share from ACS tract density",
                )
                segments = _segments_for(
                    code, row["fips"], host_type, count, rules, evidence, remaining_place, lag, bps_end
                )
                lot_bins = None
                if allegheny and row["fips"] == "42003":
                    area = "pittsburgh" if ctx == "urban" else "rest"
                    group = allegheny["groups"].get(f"{area}:{host_type}")
                    if group and group["parcels"] >= 200:
                        lot_bins = lot_bins_from_wprdc(group, allegheny["lot_edges_sqft"])
                cells.append(HostCell(row["fips"], ctx, host_type, hosts, segments, lot_bins))

        counties.append(
            County(
                fips=row["fips"],
                name=row["name"],
                state=code,
                land_sqmi=row["land_sqmi"],
                lat=row.get("lat"),
                lon=row.get("lon"),
                rent_1br=rent_1br,
                rent_2br=rent_2br,
                median_value=median_value,
                detached=detached,
                attached=attached,
                housing_units=hu,
                bps=row["bps"],
                cells=cells,
                hud_fmr=row.get("hud_fmr"),
                imputed=imputed,
                context_units=context_units,
            )
        )
    statewide = evidence.get("statewide", {})
    return StateData(
        code=code,
        name=raw["name"],
        fips=raw["state_fips"],
        vintage=raw["vintage"],
        counties=counties,
        evidence=evidence,
        parking_cap=statewide.get("parking_cap_per_unit"),
        parking_cap_effective=statewide.get("parking_cap_effective"),
        source_path=source_path,
        allegheny_lots=allegheny if code == "PA" else None,
    )


def _rule_applies(rule: dict[str, Any], county_fips: str, host_type: str) -> bool:
    geo = rule.get("geography", {})
    if host_type not in rule.get("host_types", []):
        return False
    if geo.get("state"):
        return True
    return geo.get("county") == county_fips


def _segments_for(
    code: str,
    county_fips: str,
    host_type: str,
    count: float,
    rules: list[dict[str, Any]],
    evidence: dict[str, Any],
    remaining_place: dict[str, float],
    lag: float,
    bps_end: date,
) -> list[LegalSegment]:
    statewide = evidence.get("statewide", {})
    base_adu = "unknown"
    base_mm = statewide.get("mm", "unknown") if statewide.get("mm") in {"allowed", "prohibited"} else "unknown"
    base = LegalSegment(share=1.0, adu=base_adu, mm=base_mm)
    place_segments: list[LegalSegment] = []
    for rule in rules:
        if rule["option"] not in {"adu", "mm"} or not _rule_applies(rule, county_fips, host_type):
            continue
        geo = rule.get("geography", {})
        if geo.get("place"):
            take = min(remaining_place.get(rule["id"], 0.0), count * (1.0 - sum(s.share for s in place_segments)))
            if take <= 0:
                continue
            remaining_place[rule["id"]] = remaining_place.get(rule["id"], 0.0) - take
            seg = LegalSegment(share=take / count, adu=base.adu, mm=base.mm, rules=[rule["id"]])
            _apply(seg, rule)
            place_segments.append(seg)
        else:
            _apply(base, rule)
            base.rules.append(rule["id"])
    base.share = 1.0 - sum(s.share for s in place_segments)
    segments = [s for s in place_segments + [base] if s.share > 1e-12]
    return segments


def _apply(segment: LegalSegment, rule: dict[str, Any]) -> None:
    if rule["option"] == "adu":
        segment.adu = rule["status"]
        segment.adu_effective = rule.get("effective")
        if "parking_spaces" in rule:
            segment.adu_parking = float(rule["parking_spaces"])
    else:
        segment.mm = rule["status"]
        segment.mm_effective = rule.get("effective")


def post_window(effective: str | None, lag_years: float, bps_years: list[int]) -> bool:
    """True when homes under a rule cannot appear in the permit window yet."""
    return _effective_after_window(effective, lag_years, date(max(bps_years), 12, 31))


@lru_cache(maxsize=None)
def _load(code: str, prefer_cache: bool) -> StateData:
    path = _data_path(code, prefer_cache)
    if not path.exists():
        raise FileNotFoundError(f"No Lab data for {code} at {path}. Run python -m src.lab.acquire.")
    raw = json.loads(path.read_text(encoding="utf-8"))
    allegheny = None
    if code == "PA":
        lots = path.parent / "allegheny_lots.json"
        if lots.exists():
            allegheny = json.loads(lots.read_text(encoding="utf-8"))
    return build_state(raw, allegheny, str(path.relative_to(path.parents[2])))


def load_state(code: str, prefer_cache: bool = False) -> StateData:
    """Committed sample by default so results are reproducible; cache when asked."""
    return _load(code.upper(), prefer_cache)


def load_boundaries(code: str) -> dict[str, Any]:
    for directory in (SAMPLE_DIR, CACHE_DIR):
        path = directory / f"{code.upper()}_counties.geo.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    raise FileNotFoundError(code)
