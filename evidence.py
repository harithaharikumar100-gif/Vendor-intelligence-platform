"""Evidence dates and deterministic scoring; unknown information is never a clean finding."""
import calendar
import hashlib
import re
import config
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse


def now_utc():
    return datetime.now(timezone.utc)


def months_before(months, now=None):
    now = now or now_utc()
    year, month = divmod(now.year * 12 + now.month - 1 - months, 12)
    return now.replace(year=year, month=month + 1,
                       day=min(now.day, calendar.monthrange(year, month + 1)[1]))


def parse_date(value, now=None):
    """Return a UTC date only when a day or a supported relative date is known."""
    now = now or now_utc()
    text = str(value or '').strip()
    if not text:
        return None
    relative = re.fullmatch(r'(\d+)\s+(day|week|month|year)s? ago', text.lower())
    if relative:
        count, unit = int(relative[1]), relative[2]
        return (months_before(count * (12 if unit == 'year' else 1), now)
                if unit in ('month', 'year') else now - timedelta(days=count * (7 if unit == 'week' else 1)))
    if text.lower() in ('today', 'yesterday'):
        return now - timedelta(days=text.lower() == 'yesterday')
    try:
        parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except ValueError:
        pass
    for fmt in ('%b %d, %Y', '%B %d, %Y', '%d %B %Y', '%d %b %Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def within_months(value, months, now=None):
    now = now or now_utc()
    date = parse_date(value, now)
    return date is not None and months_before(months, now).date() <= date.date() <= now.date()


def expired(timestamp, seconds, now=None):
    date = parse_date(timestamp)
    return date is None or ((now or now_utc()) - date).total_seconds() >= seconds


def http_url(value):
    try:
        url = urlparse(str(value or ''))
        return url.scheme in ('http', 'https') and bool(url.hostname) and not url.username and not url.password
    except ValueError:
        return False


def source_id(url):
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def score_events(events, recency_multiplier=1.0):
    """Provisional policy v2. Each event has an inspectable contribution, never an LLM score."""
    points = {'Low': 0, 'Elevated': 15, 'High': 35, 'Critical': 75}
    contributions = []
    for event in events:
        if event.get('verification_status') != 'source_linked' or not event.get('sources'):
            continue
        # Unknown dates and entity matches stay visible for review, without entering the score.
        if (not within_months(event.get('event_date'), config.LOOKBACK_MONTHS)
                or event.get('ambiguous_match') or event.get('severity') not in points
                or not all(http_url(url) for url in event['sources'])):
            continue
        multiplier = recency_multiplier if within_months(event['event_date'], 12) else 1
        contribution = points.get(event.get('severity'), 0) * multiplier
        if event.get('resolution') == 'resolved':
            contribution *= 0.5
        contributions.append({'event_id': event['event_id'], 'base': points.get(event.get('severity'), 0),
                              'recency_multiplier': multiplier, 'points': contribution})
    return (min(100, round(sum(x['points'] for x in contributions))) if contributions else None), contributions
