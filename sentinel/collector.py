"""Bounded, sequential metadata fetches; never follows victim or download links."""
import json
import time
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from .providers import PROVIDERS, provider_headers, parse_provider
from urllib.parse import urlparse
from .store import ingest, now

MAX_BYTES = 2_000_000


class FetchError(ValueError):
    def __init__(self, message, retry_after=0):
        super().__init__(message)
        self.retry_after = retry_after


def retry_seconds(value):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        try:
            return max(0, int((parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()))
        except (TypeError, ValueError, OverflowError):
            return 0


def fetch(source):
    import requests
    if source['type'] in ('onion_html', 'onion_status'):
        from .tor import validate_onion
        validate_onion(source)
    url = source['url']
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Source must be an http(s) URL without credentials')
    onion = parsed.hostname.endswith('.onion')
    proxy = source.get('proxy')
    if onion and (not proxy or not proxy.startswith('socks5h://')):
        raise ValueError('Onion sources require a socks5h:// proxy for remote DNS')
    headers = {'User-Agent': 'SentinelMetadataMonitor/0.4', **provider_headers(source)}
    with requests.Session() as session:
        session.trust_env = False
        with session.get(url, proxies={'http': proxy, 'https': proxy} if proxy else {},
                         headers=headers, timeout=(15, 30),
                         allow_redirects=False, stream=True) as response:
            if response.status_code != 200:
                raise FetchError(f'HTTP {response.status_code}', retry_seconds(response.headers.get('Retry-After')))
            expected = 'html' if source['type'] in ('html', 'onion_html', 'onion_status') else 'json'
            if expected not in response.headers.get('Content-Type', '').lower():
                raise ValueError('Unexpected content type')
            chunks, size, started = [], 0, time.monotonic()
            for chunk in response.iter_content(16384):
                size += len(chunk)
                if size > MAX_BYTES or time.monotonic() - started > 60:
                    raise ValueError('Response exceeds size or time budget')
                chunks.append(chunk)
            return b''.join(chunks).decode('utf-8', errors='replace')


def parse(body, source):
    if source['type'] == 'onion_status':
        return []  # Availability only; no victim identities inferred from arbitrary headings.
    if source['type'] in PROVIDERS:
        return parse_provider(body, source)
    if source['type'] == 'json':
        rows = json.loads(body)
        if not isinstance(rows, list) or len(rows) > 10000:
            raise ValueError('JSON feed must be an array with at most 10,000 records')
        if not all(isinstance(row, dict) for row in rows):
            raise ValueError('Every feed record must be an object')
        return [{**row, 'source_url': source['url']} for row in rows]
    if source['type'] not in ('html', 'onion_html'):
        raise ValueError('Unsupported source adapter')
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(body, 'html.parser')
    rows = []
    for card in soup.select(source['item_selector']):
        row = {'actor': source['actor'], 'source_url': source['url']}
        for field, selector in source['fields'].items():
            if field not in ('name', 'country', 'sector', 'published_at'):
                continue
            element = card.select_one(selector)
            row[field] = element.get_text(' ', strip=True) if element else ''
        rows.append(row)
    if not rows:
        raise ValueError('No listing cards matched; check selectors or source availability')
    return rows


def collect(db, config_path):
    sources = json.loads(config_path.read_text())['sources']
    if not isinstance(sources, list):
        raise ValueError('sources must be a list')
    names = set()
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get('name'), str) or not source['name']:
            raise ValueError('Each source needs a name')
        if source['name'] in names:
            raise ValueError('Source names must be unique')
        names.add(source['name'])
        if type(source.get('enabled', False)) is not bool:
            raise ValueError('enabled must be a boolean')
        interval = source.get('interval_seconds', 900)
        if type(interval) is not int or interval < 300:
            raise ValueError('Source interval must be at least 300 seconds')
        delay = source.get('delay_seconds', 3)
        if not isinstance(delay, (int, float)) or not 1 <= delay <= 60:
            raise ValueError('Source delay must be between 1 and 60 seconds')
    # This config is the active source inventory for this database.
    with db:
        db.execute('UPDATE source_state SET enabled=0')
        for source in sources:
            db.execute("""INSERT INTO source_state(name,enabled,interval_seconds,transport) VALUES(?,?,?,?)
                          ON CONFLICT(name) DO UPDATE SET enabled=excluded.enabled,
                          interval_seconds=excluded.interval_seconds,transport=excluded.transport""",
                       (source['name'], int(source.get('enabled', False)), source.get('interval_seconds', 900),
                        'tor_onion' if urlparse(source.get('url', '')).hostname and urlparse(source['url']).hostname.endswith('.onion') else 'https_feed'))
    results = []
    for source in sources:
        if not source.get('enabled', False):
            continue
        state = db.execute('SELECT * FROM source_state WHERE name=?', (source['name'],)).fetchone()
        if state['next_poll'] and state['next_poll'] > now():
            results.append({'source': source['name'], 'status': 'waiting', 'next_poll': state['next_poll']})
            continue
        start, added, observed, status, error = now(), 0, 0, 'ok', ''
        latest, failures, wait = state['latest_source_at'], 0, source.get('interval_seconds', 900)
        try:
            rows = parse(fetch(source), source)
            observed = len(rows)
            added = ingest(db, rows, source['name'])
            latest = max([r['source_observed_at'] for r in rows if r.get('source_observed_at')], default=latest)
        except Exception as exc:
            status, failures = 'error', state['failures'] + 1
            # Preserve actionable status codes, never exception text containing credentials or bodies.
            error = str(exc) if isinstance(exc, FetchError) else f'{type(exc).__name__}: check credentials, network or provider schema'
            wait = max(min(wait * (2 ** min(failures, 8)), 86400), getattr(exc, 'retry_after', 0))
        finished = now()
        next_poll = (datetime.now(timezone.utc) + timedelta(seconds=wait)).isoformat(timespec='seconds')
        with db:
            db.execute('INSERT INTO runs(source,started_at,status,added,observed,error) VALUES(?,?,?,?,?,?)',
                       (source['name'], start, status, added, observed, error))
            db.execute("""UPDATE source_state SET last_attempt=?,last_success=?,next_poll=?,
                          failures=?,error=?,latest_source_at=? WHERE name=?""",
                       (start, finished if status == 'ok' else state['last_success'], next_poll,
                        failures, error, latest, source['name']))
        results.append({'source': source['name'], 'status': status, 'added': added, 'observed': observed, 'error': error})
        time.sleep(source.get('delay_seconds', 3))
    return results
