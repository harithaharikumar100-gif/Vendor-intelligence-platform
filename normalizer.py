"""
normalizer.py - Input Normalisation & Entity Disambiguation (SK-VDD-001 Section 4)
---------------------------------------------------------------------------------
Features:
- Strips Canadian and international legal suffixes (Inc., Ltd., Corp., LP, LLP, ULC, etc.)
- Expands common Canadian entity acronyms and trade names
- Generates phonetic and query-broadened name variants
- Validates Canadian Business Numbers (9-digit CRA BN)
"""

import re

# Canadian and common corporate legal suffixes
CANADIAN_SUFFIXES = [
    r"\bincorporated\b", r"\bcorporation\b", r"\blimited\b", r"\bcompagnie\b",
    r"\binc\.?\b", r"\bltd\.?\b", r"\bcorp\.?\b", r"\blp\.?\b", r"\bllp\.?\b",
    r"\bulc\.?\b", r"\bco\.?\b", r"\bcie\.?\b", r"\bplc\.?\b", r"\bllc\.?\b",
    r"\bgmbh\.?\b", r"\bsa\.?\b", r"\bag\.?\b", r"\bpvt\.?\b", r"\bholdings\b"
]

# Common Canadian entity acronym mapping
KNOWN_ACRONYMS = {
    "royal bank of canada": ["RBC", "Royal Bank"],
    "rbc": ["Royal Bank of Canada"],
    "toronto-dominion bank": ["TD", "TD Bank", "Toronto-Dominion"],
    "td": ["Toronto-Dominion Bank", "TD Bank"],
    "td bank": ["Toronto-Dominion Bank"],
    "bank of nova scotia": ["Scotiabank", "BNS"],
    "scotiabank": ["Bank of Nova Scotia"],
    "bank of montreal": ["BMO", "BMO Financial Group"],
    "bmo": ["Bank of Montreal"],
    "canadian imperial bank of commerce": ["CIBC"],
    "cibc": ["Canadian Imperial Bank of Commerce"],
    "national bank of canada": ["National Bank", "NBC", "BNC"],
    "canadian national railway": ["CN", "CN Rail"],
    "canadian pacific kansas city": ["CPKC", "CP Rail"],
    "bell canada enterprises": ["BCE", "Bell"],
    "rogers communications": ["Rogers"],
    "telus corporation": ["TELUS"],
    "shopify": ["Shopify Inc"],
    "blackberry": ["BlackBerry Limited", "BB"],
    "cgi group": ["CGI Inc", "CGI"],
    "cgi": ["CGI Inc", "CGI Group"],
    "opentext": ["Open Text Corporation", "OTEX"],
    "constellation software": ["Constellation Software Inc", "CSI"],
    "thomson reuters": ["Thomson Reuters Corp", "TRI"],
    "bombardier": ["Bombardier Inc", "BBD"],
}


def normalize_vendor_name(name: str) -> dict:
    """
    Standardises vendor name per SK-VDD-001 Section 4.2:
    - Strips legal suffixes
    - Generates search variants and abbreviations
    - Identifies registered trade names
    """
    if not name:
        return {"raw": "", "clean": "", "variants": []}

    raw = name.strip()
    clean = raw

    # Strip common suffixes (case-insensitive)
    for pattern in CANADIAN_SUFFIXES:
        clean = re.sub(pattern, "", clean, flags=re.IGNORECASE).strip()

    # Clean redundant punctuation and multiple spaces
    clean = re.sub(r"[,.\-_/]+$", "", clean).strip()
    clean = re.sub(r"\s+", " ", clean).strip()

    low_clean = clean.lower()
    variants = [raw, clean] if clean and clean.lower() != raw.lower() else [raw]

    # Add known acronyms or expanded trade names
    if low_clean in KNOWN_ACRONYMS:
        for v in KNOWN_ACRONYMS[low_clean]:
            if v not in variants:
                variants.append(v)
    elif raw.lower() in KNOWN_ACRONYMS:
        for v in KNOWN_ACRONYMS[raw.lower()]:
            if v not in variants:
                variants.append(v)

    # If vendor is multi-word, add acronym variant (e.g., Canadian Pacific -> CP)
    words = clean.split()
    if len(words) >= 2 and all(w[0].isalpha() for w in words):
        acronym = "".join(w[0].upper() for w in words)
        if len(acronym) >= 2 and acronym not in variants:
            variants.append(acronym)

    return {
        "raw_name": raw,
        "normalized_name": clean or raw,
        "variants": list(dict.fromkeys(variants))  # Deduplicated preserving order
    }


def validate_business_number(bn: str) -> bool:
    """Validates CRA 9-digit Business Number format (e.g. 123456789)."""
    if not bn:
        return False
    digits = re.sub(r"\D", "", bn)
    return len(digits) == 9


def extract_domain(url: str) -> str:
    """Extracts and normalizes domain from URL for cybersecurity checks."""
    if not url:
        return ""
    clean = url.replace("https://", "").replace("http://", "").split("/")[0]
    return clean.replace("www.", "").strip().lower()
