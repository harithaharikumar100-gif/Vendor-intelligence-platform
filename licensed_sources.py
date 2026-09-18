"""
licensed_sources.py - Licensed Intelligence Source Availability (SK-VDD-001 Section 5 & 9.2)
-----------------------------------------------------------------------------------------------
The skill document's master source list (Section 5) includes several commercially
licensed platforms: Refinitiv/Bloomberg, Dun & Bradstreet, Factiva/LexisNexis,
World-Check, BitSight, and Shodan. This platform has no subscriptions to those
products, so it must not silently pretend to have queried them.

Section 9.2 requires: "If BitSight, World-Check, Refinitiv, or Factiva licenses
are not active, the corresponding dimension score confidence will be reduced.
This is logged in the data_gaps field."

This module is the single source of truth for which licensed sources are
configured (via API key env vars) and generates the data_gaps entries for
whichever ones are missing, per risk dimension.
"""

import os

# Maps each licensed source to the env var that would hold its credential,
# and which risk dimension(s) it feeds per Section 5's master reference table.
LICENSED_SOURCES = {
    "Refinitiv / Bloomberg (financial ratios, credit ratings, debt profiles)": {
        "env": "REFINITIV_API_KEY",
        "dimensions": ["financial"],
    },
    "Dun & Bradstreet (D-U-N-S, PAYDEX score, financial risk indicators)": {
        "env": "DNB_API_KEY",
        "dimensions": ["financial"],
    },
    "Factiva / LexisNexis (structured adverse media, sentiment tagging)": {
        "env": "FACTIVA_API_KEY",
        "dimensions": ["reputation"],
    },
    "World-Check / Refinitiv (PEP screening, sanctions adverse media)": {
        "env": "WORLDCHECK_API_KEY",
        "dimensions": ["key_person"],
    },
    "BitSight Security Ratings (continuous security posture scoring)": {
        "env": "BITSIGHT_API_KEY",
        "dimensions": ["cyber"],
    },
    "Shodan.io (exposed assets, open ports, misconfigurations)": {
        "env": "SHODAN_API_KEY",
        "dimensions": ["cyber"],
    },
    "HaveIBeenPwned Domain Search API (requires paid API key as of HIBP v3)": {
        "env": "HIBP_API_KEY",
        "dimensions": ["cyber"],
    },
}


def is_configured(source_label: str) -> bool:
    meta = LICENSED_SOURCES.get(source_label)
    if not meta:
        return False
    return bool(os.getenv(meta["env"], "").strip())


def configured_sources() -> list:
    return [name for name in LICENSED_SOURCES if is_configured(name)]


def missing_sources_for_dimension(dimension: str) -> list:
    return [
        name for name, meta in LICENSED_SOURCES.items()
        if dimension in meta["dimensions"] and not is_configured(name)
    ]


def data_gaps_for_dimension(dimension: str) -> list:
    """Section 8 data_gaps entries: sources that could not be accessed."""
    return [
        f"{name} not licensed/configured (set {LICENSED_SOURCES[name]['env']}) — "
        f"{dimension.replace('_', ' ')} dimension confidence reduced per SK-VDD-001 Section 9.2."
        for name in missing_sources_for_dimension(dimension)
    ]


def all_missing_data_gaps() -> list:
    gaps = []
    seen_dims = set()
    for name, meta in LICENSED_SOURCES.items():
        if is_configured(name):
            continue
        for dim in meta["dimensions"]:
            key = (name, dim)
            if key in seen_dims:
                continue
            seen_dims.add(key)
            gaps.append(
                f"{name} not licensed/configured (set {meta['env']}) — "
                f"{dim.replace('_', ' ')} dimension confidence reduced per SK-VDD-001 Section 9.2."
            )
    return gaps
