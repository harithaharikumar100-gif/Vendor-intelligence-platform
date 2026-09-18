"""
sanctions_check.py - Real OFAC SDN Sanctions List Cross-Reference (SK-VDD-001 Section 6.3.2)
------------------------------------------------------------------------------------------------
The skill document requires screening every key person AND the vendor entity itself
against OFAC/UN/OSFI/EU sanctions lists (Section 6.3.2, Critical severity; Section 10.1
automatic escalation trigger). Elsewhere in this codebase, "sanctions screening" was only
ever the AI's general knowledge from web search — never a real cross-reference against
an actual list.

OFAC's Specially Designated Nationals (SDN) list is free and public (no API key,
no license) at sanctionslistservice.ofac.treas.gov. This module downloads and caches
it, then does conservative, high-precision matching — deliberately biased toward
false negatives over false positives, since a wrongly reported sanctions match is a
serious, reputationally damaging claim that must be traceable to a real record
(SK-VDD-001 Section 9.3 "No Speculation").

All calls are defensive and never raise.
"""

import csv
import io
import re
import requests
from datetime import datetime, timezone

SDN_URL = "https://sanctionslistservice.ofac.treas.gov/api/download/sdn.csv"

_SDN_CACHE = {"rows": None, "fetched_at": None}

_STOPWORDS = {"the", "inc", "ltd", "llc", "corp", "corporation", "company", "co", "of", "and"}


def _safe_print(msg: str):
    try:
        print(msg)
    except Exception:
        pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_name(name: str) -> set:
    """Returns the set of significant (non-stopword, len>2) tokens in a name."""
    if not name:
        return set()
    # SDN individual names are "LASTNAME, Firstname Middle" - flip to a flat token set.
    flat = name.replace(",", " ")
    tokens = re.findall(r"[A-Za-z]+", flat.lower())
    return {t for t in tokens if t not in _STOPWORDS and len(t) > 2}


def _load_sdn() -> list:
    """Fetches and caches the OFAC SDN list. Free, public, no key required."""
    if _SDN_CACHE["rows"] is not None:
        return _SDN_CACHE["rows"]
    rows = []
    try:
        r = requests.get(SDN_URL, timeout=25, headers={"User-Agent": "DRiskify-SK-VDD-001/1.0"})
        if r.status_code == 200:
            reader = csv.reader(io.StringIO(r.text))
            for cols in reader:
                if len(cols) < 4:
                    continue
                rows.append({
                    "ent_num": cols[0].strip(),
                    "name": cols[1].strip(),
                    "sdn_type": cols[2].strip().strip("-").strip() or "entity",
                    "program": cols[3].strip(),
                    "remarks": cols[11].strip() if len(cols) > 11 else "",
                })
            _safe_print(f"  [✓] OFAC SDN list loaded: {len(rows)} records")
    except Exception as e:
        _safe_print(f"  [!] OFAC SDN list fetch failed: {e}")
    _SDN_CACHE["rows"] = rows
    _SDN_CACHE["fetched_at"] = _now_iso()
    return rows


def search_sdn(query_name: str, min_shared_tokens: int = 2) -> list:
    """
    Conservative match: a hit requires the query's significant name tokens to be a
    SUBSET of (or equal to) an SDN record's tokens, with at least `min_shared_tokens`
    shared tokens. This deliberately rejects single-common-word matches (e.g. a person
    named "David Beck" will not match on "Beck" or "David" alone) to avoid false
    positives on a claim this serious.
    """
    query_tokens = _normalize_name(query_name)
    if len(query_tokens) < min_shared_tokens:
        return []

    matches = []
    for row in _load_sdn():
        row_tokens = _normalize_name(row["name"])
        if not row_tokens:
            continue
        shared = query_tokens & row_tokens
        if len(shared) >= min_shared_tokens and (query_tokens <= row_tokens or row_tokens <= query_tokens):
            matches.append({
                "ent_num": row["ent_num"],
                "matched_name": row["name"],
                "sdn_type": row["sdn_type"],
                "program": row["program"],
                "remarks": row["remarks"][:200],
                "source": "OFAC SDN List (sanctionslistservice.ofac.treas.gov)",
                "retrieved_at": _SDN_CACHE["fetched_at"],
            })
    return matches
