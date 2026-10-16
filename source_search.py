"""Search-index transport that distinguishes empty results from unavailable access."""
import time
import requests
from evidence import now_utc


class SearchHits(list):
    def __init__(self, hits=(), status='unknown'):
        super().__init__(hits)
        self.query_status = status
        self.retrieved_at = now_utc().isoformat()


def search(query, count, key):
    if not key:
        return SearchHits(status='not_configured')
    for attempt in range(3):
        try:
            response = requests.post('https://google.serper.dev/search',
                                     json={'q': query, 'num': count},
                                     headers={'X-API-KEY': key}, timeout=12)
            if response.status_code == 200:
                hits = response.json().get('organic', [])
                return SearchHits(hits, 'success' if hits else 'no_matches')
            if response.status_code not in (429, 500, 502, 503, 504):
                return SearchHits(status='failed')
        except (requests.RequestException, ValueError):
            pass
        if attempt < 2:
            time.sleep(2 ** attempt)
    return SearchHits(status='failed')
