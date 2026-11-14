"""Allowlisted public intelligence providers; retain listing metadata only."""
import json
import os
from datetime import datetime, timezone

PROVIDERS = {
    'ransomlook': 'https://www.ransomlook.io/api/recent',
    'ransomware_live': 'https://api-pro.ransomware.live/victims/recent',
}


def timestamp(value):
    if not value:
        return None
    if not isinstance(value, str):
        raise ValueError('Provider timestamp must be a string')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()


def provider_headers(source):
    kind = source['type']
    if kind not in PROVIDERS:
        return {}
    if source['url'] != PROVIDERS[kind]:
        raise ValueError('Provider URL must match its approved HTTPS endpoint')
    if kind == 'ransomware_live':
        secret = os.environ.get('RANSOMWARE_LIVE_API_KEY', '').strip()
        if not secret:
            raise ValueError('RANSOMWARE_LIVE_API_KEY is not configured')
        return {'X-API-KEY': secret}
    return {}


def parse_provider(body, source):
    payload = json.loads(body)
    # PRO clients may receive an envelope; never silently accept an unknown schema.
    if source['type'] == 'ransomware_live' and isinstance(payload, dict):
        payload = payload.get('victims')
    if not isinstance(payload, list) or len(payload) > 10000:
        raise ValueError('Provider must return a bounded array of victims')
    normalized = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError('Provider item must be an object')
        if source['type'] == 'ransomlook':
            name, actor = item.get('post_title'), item.get('group_name')
        else:
            name, actor = item.get('victim'), item.get('group')
        if not isinstance(name, str) or not isinstance(actor, str) or not name.strip() or not actor.strip():
            raise ValueError('Provider identity fields are missing or changed')
        normalized.append({
            'name': name.strip(), 'actor': actor.strip(),
            'country': item.get('country') or 'Unknown',
            'sector': item.get('activity') or 'Unknown',
            'source_url': source['url'],
            'source_observed_at': timestamp(item.get('discovered')),
            # Attack estimates, descriptions, stolen data and download links are excluded.
        })
    return normalized
