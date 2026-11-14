"""Direct onion transport validation and a Tor route diagnostic."""
import base64
import hashlib
import json
from urllib.parse import urlparse
from .store import now

DEFAULT_PROXY = 'socks5h://127.0.0.1:9050'


def validate_proxy(proxy):
    parsed = urlparse(proxy or '')
    try:
        valid = (parsed.scheme == 'socks5h' and parsed.hostname in ('127.0.0.1', 'localhost', '::1')
                 and parsed.port is not None and not parsed.username and not parsed.password
                 and parsed.path in ('', '/') and not parsed.query and not parsed.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('Direct onion mode requires a local socks5h proxy with an explicit port')


def validate_onion(source):
    parsed = urlparse(source.get('url', ''))
    host = parsed.hostname or ''
    if (parsed.scheme not in ('http', 'https') or not host.endswith('.onion')
            or parsed.username or parsed.password or parsed.fragment):
        raise ValueError('Direct mode requires an onion HTTP(S) URL without credentials or fragment')
    label = host[:-6]
    try:
        if len(label) != 56:
            raise ValueError()
        raw = base64.b32decode(label.upper())
        checksum = hashlib.sha3_256(b'.onion checksum' + raw[:32] + b'\x03').digest()[:2]
        if raw[34:] != b'\x03' or raw[32:34] != checksum:
            raise ValueError()
    except (ValueError, base64.binascii.Error):
        raise ValueError('Invalid Tor v3 onion address or checksum') from None
    validate_proxy(source.get('proxy'))


def diagnose(db, proxy=DEFAULT_PROXY):
    from .collector import fetch
    validate_proxy(proxy)
    result = {'checked_at': now(), 'proxy': proxy, 'status': 'error', 'detail': ''}
    try:
        payload = json.loads(fetch({'type':'json', 'url':'https://check.torproject.org/api/ip', 'proxy':proxy}))
        if not isinstance(payload, dict) or payload.get('IsTor') is not True:
            result['detail'] = 'Tor Project did not confirm a Tor exit route'
        else:
            result.update(status='ok', detail='Tor exit route confirmed; onion service availability is checked separately')
    except Exception as exc:
        # Never retain the exit IP or raw response/exception text.
        result['detail'] = f'{type(exc).__name__}: verify Tor bootstrap, proxy and network'
    with db:
        db.execute('''INSERT INTO transport_checks(proxy,checked_at,status,detail) VALUES(?,?,?,?)
                      ON CONFLICT(proxy) DO UPDATE SET checked_at=excluded.checked_at,
                      status=excluded.status,detail=excluded.detail''',
                   (proxy,result['checked_at'],result['status'],result['detail']))
    return result
