"""Exercise command entry points and network limits without external traffic."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sentinel.__main__ import main
from sentinel.collector import fetch, MAX_BYTES
from sentinel.store import connect, records


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / 'cli.db')

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args):
        output = io.StringIO()
        with patch('sys.argv', ['sentinel', '--db', self.db, *args]), contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            main()
        return output.getvalue()

    def test_demo_and_import_commands(self):
        self.assertIn('48 fictional', self.run_cli('demo'))
        fixture = Path(self.temp.name) / 'metadata.json'
        fixture.write_text(json.dumps([{'name': 'Company', 'actor': 'Actor'}]))
        self.assertEqual(json.loads(self.run_cli('import', str(fixture)))['added'], 1)
        db = connect(self.db)
        try:
            self.assertEqual(len(records(db)), 48)
            self.assertEqual(len(records(db, mode='live')), 1)
        finally:
            db.close()

    def test_invalid_interval_and_import(self):
        with self.assertRaises(SystemExit) as error:
            self.run_cli('collect', '--interval', '2')
        self.assertEqual(error.exception.code, 2)
        fixture = Path(self.temp.name) / 'invalid.json'; fixture.write_text('{}')
        with self.assertRaises(SystemExit):
            self.run_cli('import', str(fixture))

    def test_one_collection_pass(self):
        with patch('sentinel.__main__.collect', return_value=[{'status': 'ok'}]) as collect:
            self.assertEqual(json.loads(self.run_cli('collect')), [{'status': 'ok'}])
            collect.assert_called_once()

    def test_monitor_command_dispatch(self):
        with patch('sentinel.monitor.monitor') as monitor:
            self.run_cli('monitor', '--port', '8081')
            monitor.assert_called_once_with(self.db, Path('config/sources.live.json'), 8081)

    def test_server_command_dispatch(self):
        with patch('sentinel.__main__.serve') as serve:
            self.run_cli('serve', '--port', '8080')
            serve.assert_called_once_with(self.db, 8080)


class FetchTests(unittest.TestCase):
    def response(self, code=200, content_type='application/json', chunks=None):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status_code = code
        response.headers = {'Content-Type': content_type}
        response.iter_content.return_value = chunks if chunks is not None else [b'[]']
        return response

    def run_fetch(self, response, source=None):
        source = source or {'url': 'https://example.test/feed', 'type': 'json'}
        with patch('requests.Session') as factory:
            session = factory.return_value.__enter__.return_value
            session.get.return_value = response
            body = fetch(source)
            self.assertFalse(session.trust_env)
            self.assertFalse(session.get.call_args.kwargs['allow_redirects'])
            self.assertEqual(session.get.call_args.kwargs['timeout'], (15, 30))
            return body, session.get.call_args.kwargs

    def test_success_and_proxy_forwarding(self):
        body, options = self.run_fetch(self.response(), {'url':'http://example.onion', 'type':'json', 'proxy':'socks5h://127.0.0.1:9050'})
        self.assertEqual(body, '[]')
        self.assertEqual(options['proxies']['http'], 'socks5h://127.0.0.1:9050')

    def test_redirect_rejected(self):
        with self.assertRaises(ValueError):
            self.run_fetch(self.response(code=302))

    def test_unexpected_content_type_rejected(self):
        with self.assertRaises(ValueError):
            self.run_fetch(self.response(content_type='application/octet-stream'))

    def test_response_size_limit(self):
        with self.assertRaises(ValueError):
            self.run_fetch(self.response(chunks=[b'x' * (MAX_BYTES+1)]))

    def test_response_time_budget(self):
        with patch('sentinel.collector.time.monotonic', side_effect=[0, 61]), self.assertRaises(ValueError):
            self.run_fetch(self.response())

    def test_invalid_url(self):
        for url in ('file:///etc/passwd', 'https://user:secret@example.test'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                fetch({'url': url, 'type': 'json'})
