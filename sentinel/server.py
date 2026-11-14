import csv
import io
import json
from datetime import datetime, timezone
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from .store import connect, records, investigation, update_investigation, ConflictError, STATUSES

STATIC = Path(__file__).parent / 'static'


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def parse_request(self):
        if not super().parse_request():
            return False
        allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        if self.headers.get('Host') not in allowed:
            self.send(403, {'error': 'Local Host header required'})
            return False
        return True

    def send(self, status, body, kind='application/json'):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                  '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
        if url.path in assets:
            file, kind = assets[url.path]
            return self.send(200, (STATIC / file).read_bytes(), kind)
        if url.path not in ('/api/dashboard', '/api/export', '/api/health', '/api/investigation'):
            return self.send(404, {'error': 'Not found'})
        db = connect(self.server.db_path)
        try:
            if url.path == '/api/health':
                return self.send(200, {'status': 'ok'})
            args = parse_qs(url.query)
            if url.path == '/api/investigation':
                return self.send(200, investigation(db, args.get('id', [''])[0]))
            days = int(args.get('days', ['30'])[0])
            mode = args.get('mode', ['demo'])[0]
            if days not in (7, 30, 90, 365) or mode not in ('demo', 'live'):
                raise ValueError('Invalid filters')
            rows = records(db, args.get('q', [''])[0], args.get('actor', [''])[0], days, mode)
            status = args.get('status', [''])[0]
            if status and status not in STATUSES:
                raise ValueError('Invalid status')
            if status:
                rows = [r for r in rows if r['status'] == status]
            terms = [r['term'] for r in db.execute('SELECT term FROM watchlist ORDER BY term')]
            for row in rows:
                row['matches'] = [t for t in terms if t.casefold() in (row['name'] + ' ' + row['sector'] + ' ' + row['country']).casefold()]
            if url.path == '/api/export':
                output = io.StringIO()
                columns = ['name', 'actor', 'country', 'sector', 'source', 'source_url', 'published_at', 'first_seen', 'last_seen', 'demo', 'status', 'priority']
                writer = csv.writer(output)
                writer.writerow(columns)
                for row in rows:
                    values = [str(row[c]) if row[c] is not None else '' for c in columns]
                    writer.writerow(["'" + v if v.lstrip().startswith(('=', '+', '-', '@')) else v for v in values])
                return self.send(200, output.getvalue(), 'text/csv; charset=utf-8')
            actors = [r[0] for r in db.execute('SELECT DISTINCT actor FROM victims WHERE demo=? ORDER BY actor', (int(mode == 'demo'),))]
            sources = [dict(r) for r in db.execute('SELECT * FROM source_state ORDER BY name')]
            for source in sources:
                age = ((datetime.now(timezone.utc) - datetime.fromisoformat(source['last_success'])).total_seconds()
                       if source['last_success'] else None)
                source['freshness'] = ('disabled' if not source['enabled'] else 'error' if source['error'] else
                                       'never synced' if age is None else
                                       'stale' if age > max(source['interval_seconds'] * 2, 1800) else 'fresh')
            self.send(200, {'transport_checks': [dict(r) for r in db.execute('SELECT * FROM transport_checks ORDER BY checked_at DESC')], 'sources': sources, 'records': rows, 'watchlist': terms, 'actors': actors,
                           'timeline': dict(sorted(Counter(r['first_seen'][:10] for r in rows).items())),
                           'sectors': Counter(r['sector'] for r in rows),
                           'runs': [dict(r) for r in db.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 20')]})
        except LookupError:
            self.send(404, {'error': 'Claim not found'})
        except ValueError:
            self.send(400, {'error': 'Invalid query parameters'})
        finally:
            db.close()

    def do_POST(self):
        # Require same-origin JSON; no cross-origin writes from arbitrary websites.
        origin = self.headers.get('Origin')
        if (origin and origin != 'http://' + self.headers.get('Host', '')) or self.headers.get('Content-Type') != 'application/json':
            return self.send(403, {'error': 'Same-origin JSON required'})
        if self.path not in ('/api/watchlist', '/api/investigation'):
            return self.send(404, {'error': 'Not found'})
        db = connect(self.server.db_path)
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 32768 or self.headers.get('Transfer-Encoding'):
                raise ValueError()
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError()
            if self.path == '/api/investigation':
                if not isinstance(payload.get('id'), str):
                    raise ValueError()
                return self.send(200, update_investigation(db, payload['id'], payload))
            if not isinstance(payload.get('term'), str):
                raise ValueError()
            term = payload['term'].strip()
            action = payload.get('action', 'add')
            if not 2 <= len(term) <= 100 or action not in ('add', 'delete'):
                raise ValueError()
            with db:
                if action == 'delete':
                    db.execute('DELETE FROM watchlist WHERE term=?', (term,))
                else:
                    db.execute('INSERT OR IGNORE INTO watchlist VALUES (?)', (term,))
            self.send(200, {'ok': True})
        except ConflictError as exc:
            self.send(409, {'error': str(exc)})
        except LookupError:
            self.send(404, {'error': 'Claim not found'})
        except (ValueError, AttributeError):
            self.send(400, {'error': 'Invalid request: check field types, lengths and allowed values'})
        finally:
            db.close()


def serve(db_path, port):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.db_path = db_path
    print(f'Sentinel running at http://127.0.0.1:{port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
