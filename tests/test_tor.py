"""Direct onion policy, parsing and diagnostics; all network calls are mocked."""
import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from sentinel.collector import fetch, parse
from sentinel.tor import validate_onion, diagnose
from sentinel.store import connect


def onion_host():
    key = bytes(range(32))
    raw = key + hashlib.sha3_256(b'.onion checksum'+key+b'\x03').digest()[:2] + b'\x03'
    return base64.b32encode(raw).decode().lower()+'.onion'


def source():
    return {'type':'onion_html', 'url':'http://'+onion_host()+'/',
            'proxy':'socks5h://127.0.0.1:9050', 'actor':'fictional',
            'item_selector':'.glow-card','fields':{'name':'h2.company-name'}}


class OnionTests(unittest.TestCase):
    def test_valid_v3_address(self):
        validate_onion(source())

    def test_bad_destination_rejected_before_network(self):
        for url in ('https://example.com', 'http://'+'a'*56+'.onion/', 'http://short.onion/', 'http://user:secret@'+onion_host()):
            config = source(); config['url'] = url
            with self.subTest(url=url), patch('requests.Session') as session, self.assertRaises(ValueError):
                fetch(config)
            session.assert_not_called()

    def test_proxy_required_and_local_remote_dns_only(self):
        for proxy in (None, 'socks5://127.0.0.1:9050', 'http://127.0.0.1:9050', 'socks5h://remote.example:9050', 'socks5h://127.0.0.1:bad'):
            config = source(); config['proxy'] = proxy
            with self.subTest(proxy=proxy), patch('requests.Session') as session, self.assertRaises(ValueError):
                fetch(config)
            session.assert_not_called()

    def test_only_listing_name_extracted(self):
        body = '''<html><div class="glow-card"><h2 class="company-name">Fictional Co</h2>
        <p class="description">Untrusted description</p><a href="/archive.zip">Download</a>
        <script>bad()</script></div><div class="warning"><h2 class="company-name">WARNING</h2></div>
        <div class="css-modal"><h2>Sample data</h2></div></html>'''
        rows = parse(body,source())
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['name'],'Fictional Co')
        self.assertNotIn('description',rows[0])
        self.assertNotIn('archive.zip',json.dumps(rows))

    def test_layout_change_is_not_healthy(self):
        with self.assertRaises(ValueError):
            parse('<html><h1>Access challenge</h1></html>',source())

    def test_status_only_does_not_invent_victims(self):
        config = source(); config['type'] = 'onion_status'
        self.assertEqual(parse('<h1>Login</h1>',config),[])

    def test_diagnostic_does_not_store_exit_ip(self):
        with tempfile.TemporaryDirectory() as directory:
            db = connect(Path(directory)/'test.db')
            try:
                with patch('sentinel.collector.fetch',return_value='{"IsTor":true,"IP":"192.0.2.1"}'):
                    self.assertEqual(diagnose(db)['status'],'ok')
                row = dict(db.execute('SELECT * FROM transport_checks').fetchone())
                self.assertNotIn('192.0.2.1',json.dumps(row))
                with patch('sentinel.collector.fetch',side_effect=RuntimeError('private details')):
                    self.assertEqual(diagnose(db)['status'],'error')
                row = dict(db.execute('SELECT * FROM transport_checks').fetchone())
                self.assertNotIn('private details',json.dumps(row))
            finally:
                db.close()
