"""Regression tests for analyst workflows and HTTP trust boundaries."""
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from sentinel.store import connect, ingest, records, investigation, update_investigation, ConflictError
from sentinel.server import Handler
from sentinel.collector import collect


class InvestigationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / 'test.db')
        self.db = connect(self.path)
        ingest(self.db, [{'name': 'Example', 'actor': 'Actor'}], 'Source A')
        self.id = records(self.db, mode='live')[0]['id']

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def payload(self, **changes):
        return dict(status='investigating', priority='high', notes='Verify independently', version=0, **changes)

    def test_save_and_audit_persist_after_reconnect(self):
        saved = update_investigation(self.db, self.id, self.payload())
        self.assertEqual(saved['version'], 1)
        self.db.close()
        self.db = connect(self.path)
        saved = investigation(self.db, self.id)
        self.assertEqual(saved['notes'], 'Verify independently')
        self.assertEqual(len(saved['history']), 1)
        self.assertEqual(json.loads(saved['history'][0]['before_json'])['status'], 'new')
        self.assertEqual(records(self.db, mode='live')[0]['status'], 'investigating')

    def test_stale_save_rejected_without_audit_or_data_loss(self):
        update_investigation(self.db, self.id, self.payload())
        other = connect(self.path)
        try:
            with self.assertRaises(ConflictError):
                update_investigation(other, self.id, self.payload())
        finally:
            other.close()
        self.assertEqual(len(investigation(self.db, self.id)['history']), 1)
        self.assertEqual(investigation(self.db, self.id)['version'], 1)

    def test_invalid_assessment_does_not_write(self):
        for field, value in [('status', 'confirmed'), ('priority', 'urgent'), ('notes', 'x'*5001), ('notes', None), ('version', True)]:
            payload = self.payload(); payload[field] = value
            with self.subTest(field=field, value=str(value)[:20]), self.assertRaises(ValueError):
                update_investigation(self.db, self.id, payload)
        self.assertEqual(investigation(self.db, self.id)['history'], [])

    def test_unknown_claim_not_created(self):
        with self.assertRaises(LookupError):
            update_investigation(self.db, 'unknown', self.payload())
        self.assertEqual(self.db.execute('SELECT count(*) FROM investigations').fetchone()[0], 0)

    def test_provenance_tracks_multiple_sources(self):
        ingest(self.db, [{'name': 'EXAMPLE', 'actor': 'actor'}], 'Source B')
        ingest(self.db, [{'name': 'Example', 'actor': 'Actor'}], 'Source A')
        sources = {o['source']: o['sightings'] for o in investigation(self.db, self.id)['observations']}
        self.assertEqual(sources, {'Source A': 2, 'Source B': 1})
        self.assertEqual(records(self.db, mode='live')[0]['source'], 'Source A')

    def test_null_and_nonstring_identity_rejected(self):
        for value in (None, 123, [], {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ingest(self.db, [{'name': value, 'actor': 'A'}], 'Bad')
        self.assertEqual(len(records(self.db, mode='live')), 1)

    def test_legacy_database_additive_migration(self):
        legacy = str(Path(self.temp.name) / 'legacy.db')
        db = sqlite3.connect(legacy)
        db.execute('''CREATE TABLE victims(id TEXT PRIMARY KEY,name TEXT NOT NULL,actor TEXT NOT NULL,
                   country TEXT NOT NULL,sector TEXT NOT NULL,source TEXT NOT NULL,source_url TEXT NOT NULL,
                   published_at TEXT,first_seen TEXT NOT NULL,last_seen TEXT NOT NULL,demo INTEGER NOT NULL DEFAULT 0)''')
        db.execute("INSERT INTO victims VALUES('legacy','Company','Actor','Unknown','Unknown','Old','',NULL,'2026-01-01','2026-01-01',0)")
        db.commit(); db.close()
        migrated = connect(legacy)
        try:
            self.assertEqual(investigation(migrated, 'legacy')['version'], 0)
            self.assertEqual(migrated.execute('PRAGMA user_version').fetchone()[0], 4)
            self.assertEqual(migrated.execute('SELECT first_seen FROM victims').fetchone()[0], '2026-01-01')
        finally:
            migrated.close()

    def test_failed_source_does_not_stop_next_source(self):
        config = Path(self.temp.name) / 'sources.json'
        config.write_text(json.dumps({'sources': [dict(name=n, enabled=True, type='json', url='https://example.test') for n in ('bad', 'good')]}))
        with patch('sentinel.collector.fetch', side_effect=[ValueError('secret'), '[{"name":"New","actor":"A"}]']), patch('sentinel.collector.time.sleep'):
            runs = collect(self.db, config)
        self.assertEqual([r['status'] for r in runs], ['error', 'ok'])
        self.assertEqual(runs[1]['added'], 1)
        self.assertNotIn('secret', runs[0]['error'])


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / 'api.db')
        db = connect(self.path)
        ingest(db, [{'name': 'Example', 'actor': 'Actor'}], 'Source')
        self.id = records(db, mode='live')[0]['id']; db.close()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.db_path = self.path
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.temp.cleanup()

    def request(self, path, payload=None, headers=None):
        headers = {'Content-Type': 'application/json', **(headers or {})}
        request = Request(self.base + path, data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
        try:
            response = urlopen(request)
        except HTTPError as exc:
            response = exc
        with response:
            return response.code, response.read(), response.headers

    def test_investigation_roundtrip_conflict_and_filter(self):
        payload = dict(id=self.id, version=0, status='reviewed', priority='low', notes='<script>untrusted text</script>')
        self.assertEqual(self.request('/api/investigation', payload)[0], 200)
        self.assertEqual(self.request('/api/investigation', payload)[0], 409)
        status, body, _ = self.request('/api/investigation?id=' + self.id)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['notes'], payload['notes'])
        body = self.request('/api/dashboard?mode=live&status=reviewed')[1]
        self.assertEqual(len(json.loads(body)['records']), 1)
        body = self.request('/api/dashboard?mode=live&status=new')[1]
        self.assertEqual(json.loads(body)['records'], [])

    def test_source_health_freshness(self):
        from sentinel.store import now
        db = connect(self.path)
        with db:
            db.execute("INSERT INTO source_state(name,last_success) VALUES('fresh',?)", (now(),))
            db.execute("INSERT INTO source_state(name,last_success) VALUES('stale','2020-01-01T00:00:00+00:00')")
            db.execute("INSERT INTO source_state(name,error) VALUES('failed','HTTP 429')")
            db.execute("INSERT INTO source_state(name,enabled) VALUES('disabled',0)")
        db.close()
        sources = json.loads(self.request('/api/dashboard')[1])['sources']
        self.assertEqual({s['name']:s['freshness'] for s in sources},
                         {'fresh':'fresh','stale':'stale','failed':'error','disabled':'disabled'})

    def test_host_rebinding_blocked(self):
        self.assertEqual(self.request('/api/dashboard', headers={'Host': 'evil.example'})[0], 403)

    def test_malformed_payload_and_unknown_id(self):
        for payload in ([], 23, {'term': None}):
            self.assertEqual(self.request('/api/watchlist', payload)[0], 400)
        self.assertEqual(self.request('/api/investigation?id=missing')[0], 404)
        self.assertEqual(self.request('/api/dashboard?status=confirmed')[0], 400)

    def test_export_keeps_live_zero_and_security_headers(self):
        status, body, headers = self.request('/api/export?mode=live')
        self.assertEqual(status, 200)
        self.assertIn(',0,new,medium', body.decode())
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
