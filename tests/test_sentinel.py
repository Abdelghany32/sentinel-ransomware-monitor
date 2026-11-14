import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from sentinel.store import connect, ingest, records, seed
from sentinel.collector import parse, fetch
from sentinel.server import Handler


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / 'test.db')
        self.db = connect(self.path)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_idempotent_and_demo_isolation(self):
        row = {'name':'Example', 'actor':'Actor'}
        self.assertEqual(ingest(self.db,[row],'A'),1)
        stamp = records(self.db,mode='live')[0]['first_seen']
        self.assertEqual(ingest(self.db,[{'name':'EXAMPLE','actor':'actor'}],'B'),0)
        self.assertEqual(records(self.db,mode='live')[0]['first_seen'],stamp)
        ingest(self.db,[row],'Demo',True)
        self.assertEqual(len(records(self.db)),1)
        self.assertEqual(len(records(self.db,mode='live')),1)

    def test_validation_atomicity_and_filters(self):
        with self.assertRaises(ValueError):
            ingest(self.db,[{'name':'A','actor':'B'},{'name':''}],'Test')
        self.assertEqual(records(self.db,mode='live'),[])
        ingest(self.db,[{'name':"O'Reilly",'actor':'A','sector':'Health'}],'Test')
        self.assertEqual(len(records(self.db,query='HEALTH',mode='live')),1)
        self.assertEqual(records(self.db,query="' OR 1=1",mode='live'),[])

    def test_demo_seed(self):
        seed(self.db); seed(self.db)
        self.assertEqual(len(records(self.db)),48)
        self.assertEqual(records(self.db,mode='live'),[])

    def test_parsers(self):
        source = {'type':'json','url':'https://example.test'}
        self.assertEqual(parse('[{"name":"A","actor":"B"}]',source)[0]['source_url'],source['url'])
        with self.assertRaises(ValueError): parse('{}',source)
        with self.assertRaises(ValueError): parse('[null]',source)

    def test_onion_requires_remote_dns(self):
        with self.assertRaises(ValueError):
            fetch({'url':'http://example.onion','type':'html','proxy':'socks5://127.0.0.1:9050'})

    def test_html_selector_and_failure(self):
        source = {'type':'html','url':'https://example.test','actor':'A','item_selector':'.card','fields':{'name':'h2'}}
        self.assertEqual(parse('<div class="card"><h2>Example</h2></div>',source)[0]['name'],'Example')
        with self.assertRaises(ValueError): parse('<p>Unavailable</p>',source)

    def test_http_api(self):
        server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        server.db_path = self.path
        thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            self.assertEqual(urlopen(base).status,200)
            req = Request(base+'/api/watchlist',data=b'{"term":"health"}',headers={'Content-Type':'application/json'})
            self.assertEqual(urlopen(req).status,200)
            state = json.load(urlopen(base+'/api/dashboard'))
            self.assertEqual(state['watchlist'],['health'])
            ingest(self.db,[{'name':'=DANGER','actor':'A'}],'Test')
            self.assertIn("'=DANGER",urlopen(base+'/api/export?mode=live').read().decode())
            for path in ['/api/dashboard?days=bad','/api/dashboard?mode=bad']:
                with self.assertRaises(HTTPError) as ctx: urlopen(base+path)
                self.assertEqual(ctx.exception.code,400)
                ctx.exception.close()
            req = Request(base+'/api/watchlist',data=b'{"term":"evil"}',headers={'Content-Type':'application/json','Origin':'https://evil.example'})
            with self.assertRaises(HTTPError) as ctx: urlopen(req)
            self.assertEqual(ctx.exception.code,403)
            ctx.exception.close()
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__': unittest.main()
