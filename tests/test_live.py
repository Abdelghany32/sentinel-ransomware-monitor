"""Synthetic provider contracts and persistent polling policy; no live requests."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from sentinel.collector import collect, FetchError, retry_seconds
from sentinel.providers import parse_provider, provider_headers, PROVIDERS
from sentinel.store import connect, records, investigation


class ProviderTests(unittest.TestCase):
    def test_ransomlook_allowlist_and_date_semantics(self):
        source = {'type': 'ransomlook', 'url': PROVIDERS['ransomlook']}
        item = {'post_title':'Fictional Organization','group_name':'Demo Actor',
                'discovered':'2026-01-02 10:00:00', 'description':'Excluded',
                'link':'http://example.onion/archive', 'magnet':'Excluded'}
        row = parse_provider(json.dumps([item]), source)[0]
        self.assertEqual(row['name'], 'Fictional Organization')
        self.assertEqual(row['source_observed_at'], '2026-01-02T10:00:00+00:00')
        self.assertEqual(row['country'], 'Unknown')
        for field in ('link','magnet','description','published_at'):
            self.assertNotIn(field, row)

    def test_pro_schema_and_optional_fields(self):
        source = {'type':'ransomware_live','url':PROVIDERS['ransomware_live']}
        row = parse_provider(json.dumps({'victims':[{'victim':'Example','group':'Demo', 'activity':'Retail','country':'FR','discovered':'2026-01-02T12:00:00+02:00','attackdate':'2020-01-01'}]}), source)[0]
        self.assertEqual(row['actor'], 'Demo')
        self.assertEqual(row['sector'], 'Retail')
        self.assertEqual(row['source_observed_at'], '2026-01-02T10:00:00+00:00')

    def test_schema_drift_fails_closed(self):
        source = {'type':'ransomlook', 'url':PROVIDERS['ransomlook']}
        for body in ('{}', '[null]', '[{"title":"changed"}]'):
            with self.subTest(body=body), self.assertRaises(ValueError):
                parse_provider(body, source)

    def test_key_never_sent_to_custom_destination(self):
        with patch.dict(os.environ, {'RANSOMWARE_LIVE_API_KEY':'test-only'}):
            with self.assertRaises(ValueError):
                provider_headers({'type':'ransomware_live','url':'https://other.example'})
            self.assertEqual(provider_headers({'type':'ransomware_live','url':PROVIDERS['ransomware_live']}), {'X-API-KEY':'test-only'})
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            provider_headers({'type':'ransomware_live','url':PROVIDERS['ransomware_live']})

    def test_retry_after(self):
        self.assertEqual(retry_seconds('3600'), 3600)
        self.assertEqual(retry_seconds('-1'), 0)
        self.assertEqual(retry_seconds('invalid'), 0)
        self.assertEqual(retry_seconds('Wed, 01 Jan 2020 00:00:00 GMT'), 0)


class PollingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'db.sqlite'
        self.db = connect(self.path)
        self.config = Path(self.temp.name) / 'sources.json'
        self.source = {'name':'Test provider','enabled':True,'type':'ransomlook','url':PROVIDERS['ransomlook'],'interval_seconds':900}
        self.config.write_text(json.dumps({'sources':[self.source]}))
        self.body = json.dumps([{'post_title':'Example','group_name':'Actor','discovered':'2026-01-02 12:00:00'}])

    def tearDown(self):
        self.db.close(); self.temp.cleanup()

    def test_success_persists_provenance_and_cooldown(self):
        with patch('sentinel.collector.fetch', return_value=self.body) as fetch, patch('sentinel.collector.time.sleep'):
            self.assertEqual(collect(self.db, self.config)[0]['added'], 1)
            self.db.close(); self.db = connect(self.path)
            self.assertEqual(collect(self.db, self.config)[0]['status'], 'waiting')
            fetch.assert_called_once()
        claim = records(self.db, mode='live')[0]
        self.assertIsNone(claim['published_at'])
        self.assertEqual(investigation(self.db, claim['id'])['observations'][0]['source_observed_at'], '2026-01-02T12:00:00+00:00')
        state = self.db.execute('SELECT * FROM source_state').fetchone()
        self.assertIsNotNone(state['last_success'])
        self.assertEqual(state['latest_source_at'], '2026-01-02T12:00:00+00:00')

    def test_rate_limit_then_recovery(self):
        with patch('sentinel.collector.fetch', side_effect=FetchError('HTTP 429', 7200)), patch('sentinel.collector.time.sleep'):
            result = collect(self.db, self.config)[0]
        self.assertEqual(result['error'], 'HTTP 429')
        state = self.db.execute('SELECT * FROM source_state').fetchone()
        from datetime import datetime
        self.assertGreaterEqual((datetime.fromisoformat(state['next_poll'])-datetime.fromisoformat(state['last_attempt'])).total_seconds(),7200)
        with self.db:
            self.db.execute('UPDATE source_state SET next_poll=NULL')
        with patch('sentinel.collector.fetch', return_value=self.body), patch('sentinel.collector.time.sleep'):
            self.assertEqual(collect(self.db,self.config)[0]['status'],'ok')
        state = self.db.execute('SELECT * FROM source_state').fetchone()
        self.assertEqual(state['failures'],0)
        self.assertEqual(state['error'],'')

    def test_disabled_source_does_not_fetch(self):
        self.source['enabled'] = False
        self.config.write_text(json.dumps({'sources':[self.source]}))
        with patch('sentinel.collector.fetch') as fetch:
            self.assertEqual(collect(self.db,self.config),[])
            fetch.assert_not_called()

    def test_bad_interval_does_not_fetch(self):
        self.source['interval_seconds'] = 2
        self.config.write_text(json.dumps({'sources':[self.source]}))
        with patch('sentinel.collector.fetch') as fetch, self.assertRaises(ValueError):
            collect(self.db,self.config)
        fetch.assert_not_called()


class MonitorTests(unittest.TestCase):
    def test_worker_collects_and_stops_with_server(self):
        import contextlib
        import io
        import threading
        from sentinel.monitor import monitor
        done = threading.Event()
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory)/'monitor.db')
            db = connect(path); db.close()
            def collect_once(*args):
                done.set()
                return []
            def server(*args):
                if not done.wait(3):
                    raise AssertionError('Worker did not collect')
            with patch('sentinel.monitor.collect', side_effect=collect_once) as collect_mock, patch('sentinel.monitor.serve', side_effect=server), contextlib.redirect_stdout(io.StringIO()):
                monitor(path, Path(directory)/'config.json', 8000)
                collect_mock.assert_called_once()
            self.assertFalse(any(t.name == 'sentinel-collector' for t in threading.enumerate()))
