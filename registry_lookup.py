"""
registry_lookup.py - Corporate Registry Direct Lookup (SK-VDD-001 Section 3.3 & 5)
--------------------------------------------------------------------------------
Provides real registry access beyond Google search snippets:
- Corporations Canada (federal) registry search + page fetch
- Provincial registry cross-reference
- Extracts: registration status, business number, directors, registered address

All calls are defensive — never raises; returns empty dict on any failure.
"""

import re
from concurrent.futures import ThreadPoolExecutor
from financial_fetcher import _serper, _webpage


def _safe_print(msg: str):
    try:
        print(msg)
    except Exception:
        pass


def search_corporations_canada(vendor: str, business_number: str = "") -> dict:
    """Search Corporations Canada federal registry for the vendor."""
    results = {"found": False, "source": "Corporations Canada (ic.gc.ca)", "url": ""}
    try:
        queries = []
        if business_number:
            queries.append(f'"{business_number}" site:ic.gc.ca corporation')
        queries.append(f'"{vendor}" site:ic.gc.ca "Corporations Canada"')
        queries.append(f'"{vendor}" ("Corporations Canada" OR "corporate status") registration')

        hits = []
        for q in queries:
            hits = _serper(q, 5)
            if hits:
                break

        if not hits:
            results["status"] = "Not found in federal registry search"
            return results

        top = hits[0]
        results["found"] = True
        results["url"] = top.get("link", "")
        results["snippet"] = top.get("snippet", "")

        # Try to fetch the actual registry page for structured data
        page_text = _webpage(top.get("link", ""), 8000)
        if page_text and len(page_text) > 200:
            m = re.search(r'(?:Status|Statut)[:\s]+([A-Za-z\s]+?)(?:\.|\n|<|,)', page_text)
            if m:
                results["status"] = m.group(1).strip()[:50]

            m = re.search(r'(?:Business Number|BN|Numero)[:\s]+(\d{9})', page_text)
            if m:
                results["business_number"] = m.group(1)

            m = re.search(
                r'(?:Registered (?:Office|Address)|Address)[:\s]+([^\n<]{10,120})',
                page_text, re.I,
            )
            if m:
                results["registered_address"] = m.group(1).strip()[:120]

            directors = re.findall(
                r'(?:Director|Directeur)[:\s]+([A-Z][a-zA-Z\s\-\.]{2,40})',
                page_text,
            )
            if directors:
                results["directors"] = list(dict.fromkeys(d.strip() for d in directors))[:10]

        # Fall back to snippet parsing if page fetch yielded nothing
        if "status" not in results:
            snippet = top.get("snippet", "") + " " + top.get("title", "")
            for pattern in [r'\b(Active|Active-Dissolution|Dissolved|Amalgamated|Discontinued|Amalgamated-Out)\b']:
                m = re.search(pattern, snippet, re.I)
                if m:
                    results["status"] = m.group(1)
                    break
            if "status" not in results:
                results["status"] = "Found (status not parsed)"

        _safe_print(f"  [✓] Corporations Canada: {results.get('status', 'found')}")
    except Exception as e:
        _safe_print(f"  [!] Corporations Canada lookup failed: {e}")
        results["error"] = str(e)[:100]

    return results


def search_provincial_registry(vendor: str, country: str = "Canada") -> dict:
    """Cross-reference provincial corporate registries via Serper."""
    results = {"found": False, "source": "Provincial Registry Cross-Reference", "url": ""}
    try:
        q = (
            f'"{vendor}" ("corporate registry" OR "company profile" OR "registration") '
            f'site:gov.on.ca OR site:gov.bc.ca OR site:quebec.ca OR site:alberta.ca '
            f'OR site:gov.mb.ca OR site:gov.ns.ca'
        )
        hits = _serper(q, 5)
        if hits:
            results["found"] = True
            results["url"] = hits[0].get("link", "")
            results["snippet"] = hits[0].get("snippet", "")
            _safe_print(f"  [✓] Provincial registry: found on {hits[0].get('link', '')[:60]}")
        else:
            results["status"] = "Not found in provincial registry search"
    except Exception as e:
        _safe_print(f"  [!] Provincial registry lookup failed: {e}")
        results["error"] = str(e)[:100]

    return results


def search_all_registries(
    vendor: str,
    business_number: str = "",
    company_url: str = "",
    country: str = "Canada",
) -> dict:
    """Run all registry lookups in parallel."""
    with ThreadPoolExecutor(max_workers=2) as ex:
        fed_fut = ex.submit(search_corporations_canada, vendor, business_number)
        prov_fut = ex.submit(search_provincial_registry, vendor, country)

        fed = fed_fut.result()
        prov = prov_fut.result()

    return {
        "federal_registry": fed,
        "provincial_registry": prov,
    }
