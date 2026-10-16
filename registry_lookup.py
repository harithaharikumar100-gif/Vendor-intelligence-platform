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


def _lookup(vendor, business_number, queries, source):
    from registry_verification import verify_record, authoritative
    from evidence import now_utc
    result = {'found': False, 'identity_verified': False, 'source': source, 'url': '',
              'candidates': [], 'query_status': 'unknown', 'retrieved_at': now_utc().isoformat(),
              'method': 'search_index_and_registry_page'}
    statuses = []
    verified = []
    seen = set()
    for query in queries:
        hits = _serper(query, 5)
        statuses.append(getattr(hits, 'query_status', 'unknown'))
        for hit in hits:
            url = hit.get('link', '')
            if url in seen or not authoritative(url):
                continue
            seen.add(url)
            record = verify_record(vendor, business_number, url, _webpage(url, 20000))
            result['candidates'].append(dict(record, url=url))
            if record['identity_verified']:
                verified.append(record)
    result['query_status'] = ('failed' if any(s not in ('success', 'no_matches') for s in statuses)
                              else 'success' if seen else 'no_matches')
    ids = {r.get('business_number') or r.get('corporation_number') for r in verified}
    if len(ids) == 1:
        result.update(verified[0], found=True)
    elif len(ids) > 1:
        result['ambiguous'] = True
    return result


def search_corporations_canada(vendor: str, business_number: str = '') -> dict:
    queries = [f'"{vendor}" (site:ised-isde.canada.ca OR site:ic.gc.ca) "Corporations Canada"']
    if business_number:
        queries.insert(0, f'"{business_number}" "{vendor}" site:ised-isde.canada.ca')
    return _lookup(vendor, business_number, queries, 'Corporations Canada')


def search_provincial_registry(vendor: str, country: str = 'Canada', business_number: str = '', province: str = '') -> dict:
    query = (f'"{vendor}" "{province}" ("corporate registry" OR "corporation number") '
             '(site:ontario.ca OR site:gov.bc.ca OR site:quebec.ca OR site:alberta.ca OR site:gov.mb.ca '
             'OR site:novascotia.ca OR site:saskatchewan.ca OR site:gnb.ca OR site:gov.nl.ca '
             'OR site:princeedwardisland.ca OR site:yukon.ca OR site:gov.nt.ca OR site:gov.nu.ca)')
    return _lookup(vendor, business_number, [query], 'Provincial Registry')


def search_all_registries(vendor: str, business_number: str = '', company_url: str = '', country: str = 'Canada', province: str = '') -> dict:
    with ThreadPoolExecutor(max_workers=2) as ex:
        fed = ex.submit(search_corporations_canada, vendor, business_number)
        prov = ex.submit(search_provincial_registry, vendor, country, business_number, province)
        return {'federal_registry': fed.result(), 'provincial_registry': prov.result()}
