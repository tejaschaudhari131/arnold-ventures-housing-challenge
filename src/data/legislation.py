# Copyright 2026 Tejas Chaudhari, Yoon Yik Ng, and Christopher Severns
# SPDX-License-Identifier: Apache-2.0
"""Curated catalog of real enacted and proposed state housing legislation.

Maps actual Challenge-state bills and statutes onto Stateframe's deterministic
reform weights and statutory assumption bounds. No housing counts are stored
here — selecting a bill configures inputs and calls the live structural engine.
"""

from __future__ import annotations

from typing import Any

REAL_BILLS: list[dict[str, Any]] = [
    {
        "id": "PA_STARTER_PACKAGE",
        "state": "PA",
        "state_name": "Pennsylvania",
        "bill_number": "SB 1193 / HB 1976 + Municipal Fee & Parking Package",
        "status": "Proposed",
        "session": "2025–26 General Assembly",
        "citation": "Pa. Gen. Assembly SB 1193 (ADUs) & HB 1976 (Starter / Middle Housing Infill)",
        "summary": (
            "Legalizes by-right accessory dwelling units and 2–4 unit starter homes on "
            "water/sewer-served lots, pairs transit-corridor parking relief, and caps municipal tap/impact fees."
        ),
        "clauses": [
            "By-right internal or detached ADU on single-family lots (100% ADU weight)",
            "Duplex–fourplex infill on served residential parcels (85% Missing Middle weight)",
            "Repeals residential parking minimums near transit & commercial corridors (85% Parking, 60% TOD)",
            "50% reduction in municipal tap, hookup, and impact fees (80% Fee weight)",
        ],
        "reforms": {"adu": 1.0, "missing_middle": 0.85, "tod": 0.6, "parking": 0.85, "fees": 0.8},
        "lab_reforms": ["adu", "missing_middle", "parking", "fees"],
        "single_stair": False,
    },
    {
        "id": "PA_HB1976_ADU_MM",
        "state": "PA",
        "state_name": "Pennsylvania",
        "bill_number": "SB 1193 / HB 1976 Zoning-Only Amendment (No Fee Cap)",
        "status": "Proposed",
        "session": "2025–26 General Assembly",
        "citation": "Pa. Gen. Assembly SB 1193 & HB 1976 (Zoning Preemption Standalone)",
        "summary": (
            "Tests zoning legalization for backyard cottages and gentle density on its own, "
            "leaving municipal impact fees and suburban parking mandates untouched."
        ),
        "clauses": [
            "By-right ADU entitlement statewide (100% ADU weight)",
            "Duplex/triplex/fourplex allowance in boroughs and cities (75% Missing Middle weight)",
            "No municipal impact-fee cap or transit upzoning included (0% Fee & TOD)",
        ],
        "reforms": {"adu": 1.0, "missing_middle": 0.75, "tod": 0.0, "parking": 0.25, "fees": 0.0},
        "lab_reforms": ["adu", "missing_middle"],
        "single_stair": False,
    },
    {
        "id": "NH_HB1291_SB284",
        "state": "NH",
        "state_name": "New Hampshire",
        "bill_number": "HB 1291 / SB 284 Detached ADU & 1-Space Parking Cap",
        "status": "Enacted / Active",
        "session": "RSA 674:71–73 & 2024–25 Session",
        "citation": "N.H. RSA 674:71–73 (ADU Statute); HB 1291 (Detached ADUs) & SB 284 (Parking Cap)",
        "summary": (
            "Upgrades New Hampshire's existing attached-ADU law to allow detached backyard cottages by right "
            "and caps residential parking mandates at one space per home."
        ),
        "clauses": [
            "Expands RSA 674:71 to detached ADUs by right (100% ADU weight)",
            "Caps residential off-street parking requirements at 1 space/unit (100% Parking weight)",
            "Leaves multiplex zoning and municipal impact fees at local baseline",
        ],
        "reforms": {"adu": 1.0, "missing_middle": 0.0, "tod": 0.0, "parking": 1.0, "fees": 0.0},
        "lab_reforms": ["adu", "parking"],
        "single_stair": False,
    },
    {
        "id": "NH_BIPARTISAN_INFILL",
        "state": "NH",
        "state_name": "New Hampshire",
        "bill_number": "NH Water/Sewer Fourplex, ADU & Fee Cap Package",
        "status": "Proposed",
        "session": "2025–26 General Court",
        "citation": "N.H. HB 1399 / Housing Champions & Water-Sewer Infill Proposals",
        "summary": (
            "Pairs detached ADU expansion with 2–4 unit homes on water/sewer-connected lots, "
            "parking reform, and municipal impact-fee relief."
        ),
        "clauses": [
            "Detached & internal ADUs by right (100% ADU weight)",
            "2–4 unit residential infill on municipal water & sewer lots (80% Missing Middle weight)",
            "1-space parking cap & municipal fee moderation (100% Parking, 75% Fee weight)",
        ],
        "reforms": {"adu": 1.0, "missing_middle": 0.8, "tod": 0.0, "parking": 1.0, "fees": 0.75},
        "lab_reforms": ["adu", "missing_middle", "parking", "fees"],
        "single_stair": False,
    },
    {
        "id": "OR_HB2001_CFEC",
        "state": "OR",
        "state_name": "Oregon",
        "bill_number": "HB 2001 Middle Housing + CFEC Parking Reform",
        "status": "Enacted",
        "session": "2019 Statute / 2022 Rules",
        "citation": "Or. Laws 2019, ch. 639 (HB 2001); OAR 660-012 (Climate-Friendly & Equitable Communities)",
        "summary": (
            "Landmark law legalizing duplexes in cities above 10,000 residents and fourplexes/cottages "
            "in metros above 25,000, paired with transit-corridor parking mandate repeal."
        ),
        "clauses": [
            "Duplex–fourplex & cottage clusters inside urban growth boundaries (100% Missing Middle weight)",
            "Statewide urban ADU allowance without owner-occupancy or parking mandates (85% ADU weight)",
            "CFEC parking mandate repeal near transit & climate-friendly areas (100% Parking, 65% TOD)",
        ],
        "reforms": {"adu": 0.85, "missing_middle": 1.0, "tod": 0.65, "parking": 1.0, "fees": 0.0},
        "lab_reforms": ["adu", "missing_middle", "parking"],
        "single_stair": True,
    },
    {
        "id": "AZ_HB2720_HB2721",
        "state": "AZ",
        "state_name": "Arizona",
        "bill_number": "HB 2720 (Casitas) & HB 2721 (Middle Housing)",
        "status": "Enacted",
        "session": "2024 56th Legislature",
        "citation": "Ariz. Laws 2024, ch. 195 (HB 2720) & ch. 196 (HB 2721)",
        "summary": (
            "Bipartisan 2024 package legalizing backyard casitas (ADUs) without additional parking "
            "and allowing duplex–fourplex middle housing within 1 mile of central business districts in cities >=75k."
        ),
        "clauses": [
            "Up to 2–3 ADUs/casitas by right in cities >=75,000 with zero new parking mandates (100% ADU)",
            "Duplex–fourplex middle housing near central commercial cores & new subdivisions (65% Missing Middle)",
            "Prohibits extra municipal parking requirements on casitas & downtown middle housing (70% Parking)",
        ],
        "reforms": {"adu": 1.0, "missing_middle": 0.65, "tod": 0.25, "parking": 0.7, "fees": 0.0},
        "lab_reforms": ["adu", "missing_middle", "parking"],
        "single_stair": False,
    },
    {
        "id": "CT_WORK_LIVE_RIDE",
        "state": "CT",
        "state_name": "Connecticut",
        "bill_number": "HB 5002 / HB 5474 Work Live Ride Transit Communities",
        "status": "Proposed / Enacted Veto-Revised",
        "session": "2024–25 General Assembly",
        "citation": "Conn. Gen. Assembly HB 5474 / HB 5002 (Transit-Oriented Communities & Infrastructure Priority)",
        "summary": (
            "Prioritizes state infrastructure funds for municipalities adopting by-right transit-oriented "
            "communities around Metro-North, Shore Line East, Hartford Line, and CTfastrak stations."
        ),
        "clauses": [
            "By-right multi-family transit-oriented districts within 0.5 miles of rail & BRT (100% TOD)",
            "Caps residential parking minimums in station areas and opt-in towns (85% Parking)",
            "Complements PA 21-29 ADU & middle-housing opt-in framework (50% ADU, 55% Missing Middle)",
        ],
        "reforms": {"adu": 0.5, "missing_middle": 0.55, "tod": 1.0, "parking": 0.85, "fees": 0.0},
        "lab_reforms": ["adu", "missing_middle", "parking"],
        "single_stair": False,
    },
    {
        "id": "UT_SB174_HTRZ",
        "state": "UT",
        "state_name": "Utah",
        "bill_number": "SB 174 Internal ADUs & HTRZ Station-Area Zoning",
        "status": "Enacted",
        "session": "2021–2023 General Sessions",
        "citation": "Utah Code § 10-9a-530 (Internal ADUs) & § 63N-3-603 (Housing & Transit Reinvestment Zones)",
        "summary": (
            "Requires municipalities to allow internal ADUs by right, pair station-area plans around FrontRunner "
            "and TRAX rail, and moderate impact fees on smaller infill units."
        ),
        "clauses": [
            "Statewide internal ADU preemption with capped parking (80% ADU, 65% Parking)",
            "Mandatory Housing & Transit Reinvestment Zone density around rail/BRT stations (100% TOD)",
            "Moderate small-footprint fee calibration & Wasatch Front infill (35% Missing Middle, 40% Fees)",
        ],
        "reforms": {"adu": 0.8, "missing_middle": 0.35, "tod": 1.0, "parking": 0.65, "fees": 0.4},
        "lab_reforms": ["adu", "parking", "fees"],
        "single_stair": False,
    },
    {
        "id": "HI_ACT39_INFILL",
        "state": "HI",
        "state_name": "Hawaii",
        "bill_number": "Act 39 (SB 3202) Two-ADU Mandate & Urban District Infill",
        "status": "Enacted",
        "session": "2024 Regular Session",
        "citation": "Haw. Act 39, SLH 2024 (SB 3202) & Act 37 (Adaptive Urban Residential)",
        "summary": (
            "Requires counties to allow at least two accessory dwelling units on residential lots inside "
            "Urban districts with infrastructure, paired with parking and adaptive infill reforms."
        ),
        "clauses": [
            "Two ADUs/ohana units allowed per urban residential lot (100% ADU weight)",
            "Urban district residential conversion & multiplex allowance (70% Missing Middle, 70% TOD)",
            "Prohibits off-street parking mandates that block urban infill ADUs (85% Parking, 50% Fees)",
        ],
        "reforms": {"adu": 1.0, "missing_middle": 0.7, "tod": 0.7, "parking": 0.85, "fees": 0.5},
        "lab_reforms": ["adu", "missing_middle", "parking", "fees"],
        "single_stair": True,
    },
    {
        "id": "VA_TRANSIT_ADU_2025",
        "state": "VA",
        "state_name": "Virginia",
        "bill_number": "SB 304 / HB 900 Statewide ADU & Single-Stair Code Package",
        "status": "Proposed / Partial Enacted",
        "session": "2024–25 General Assembly",
        "citation": "Va. Gen. Assembly SB 304 (By-Right ADUs) & HB 368 / SB 195 (Single-Stair Code Study)",
        "summary": (
            "Establishes statewide by-right accessory dwelling units, transit-corridor density in Northern Virginia "
            "and Richmond/Hampton Roads, and six-story single-stair point-access block building code reform."
        ),
        "clauses": [
            "By-right ADUs without owner-occupancy or extra parking mandates (100% ADU, 75% Parking)",
            "Metro/VRE/Pulse transit-corridor housing & gentle density (75% TOD, 55% Missing Middle)",
            "Includes 6-story single-stair point-access block building code screen",
        ],
        "reforms": {"adu": 1.0, "missing_middle": 0.55, "tod": 0.75, "parking": 0.75, "fees": 0.0},
        "lab_reforms": ["adu", "missing_middle", "parking"],
        "single_stair": True,
    },
]


def load_legislation(state_code: str | None = None) -> dict[str, Any]:
    """Return curated real state bills (all Challenge states, or filtered to one state)."""
    if not state_code or state_code.strip().upper() == "ALL":
        bills = REAL_BILLS
    else:
        code = state_code.strip().upper()
        bills = [b for b in REAL_BILLS if b["state"] == code]
    return {
        "count": len(bills),
        "note": (
            "Statutory presets map enacted and proposed state housing bills onto Stateframe's "
            "deterministic reform levers. All housing figures are computed live by the engine."
        ),
        "bills": bills,
    }
