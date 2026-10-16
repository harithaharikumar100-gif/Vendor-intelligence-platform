"""Registry search discovers candidates; only authoritative structured records verify identity."""
import re
from urllib.parse import urlparse
from normalizer import normalize_vendor_name

REGISTRY_HOSTS = ('ised-isde.canada.ca', 'ic.gc.ca', 'ised-isde.gc.ca', 'ontario.ca', 'gov.on.ca',
                  'gov.bc.ca', 'quebec.ca', 'alberta.ca', 'gov.mb.ca', 'novascotia.ca', 'gov.ns.ca',
                  'saskatchewan.ca', 'gnb.ca', 'gov.nl.ca', 'princeedwardisland.ca', 'yukon.ca',
                  'gov.nt.ca', 'gov.nu.ca')


def authoritative(url):
    host = (urlparse(url).hostname or '').lower()
    return any(host == domain or host.endswith('.' + domain) for domain in REGISTRY_HOSTS)


def verify_record(vendor, bn, url, text):
    result = {'identity_verified': False}
    if not authoritative(url):
        return result
    name = re.search(r'(?:Corporation Name|Legal Name|Dénomination sociale)\s*[:\n]\s*([^\n]{2,150})', text, re.I)
    number = re.search(r'(?:Business Number|Numéro d’entreprise|BN)\s*[:\n]\s*(\d{9})\b', text, re.I)
    corporation = re.search(r'(?:Corporation Number|Numéro de société)\s*[:\n]\s*([\d-]{6,15})', text, re.I)
    if not name or not (number or corporation):
        return result
    normalize = lambda value: re.sub(r'\W+', '', normalize_vendor_name(value)['normalized_name']).casefold()
    result.update(legal_name=name[1].strip(), business_number=number[1] if number else '',
                  corporation_number=corporation[1] if corporation else '', url=url)
    result['identity_verified'] = normalize(name[1]) == normalize(vendor) and (not bn or (number and number[1] == bn))
    result['identity_verified'] = bool(result['identity_verified'])
    return result
