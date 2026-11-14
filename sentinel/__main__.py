import argparse
import json
import time
from pathlib import Path
from .store import connect, seed, ingest
from .collector import collect
from .server import serve


def main():
    parser = argparse.ArgumentParser(description='Sentinel ransomware listing monitor')
    parser.add_argument('--db', default='data/sentinel.db')
    sub = parser.add_subparsers(dest='command', required=True)
    tor_check = sub.add_parser('tor-check', help='Verify a local SOCKS route using Tor Project and save diagnostic')
    tor_check.add_argument('--proxy', default='socks5h://127.0.0.1:9050')
    sub.add_parser('demo', help='Seed fictional training records')
    web = sub.add_parser('serve', help='Start local dashboard')
    web.add_argument('--port', type=int, default=8000)
    live = sub.add_parser('monitor', help='Dashboard plus periodic live intelligence collection')
    live.add_argument('--config', type=Path, default=Path('config/sources.live.json'))
    live.add_argument('--port', type=int, default=8000)
    imp = sub.add_parser('import', help='Import a normalized JSON metadata array')
    imp.add_argument('file', type=Path)
    imp.add_argument('--source', default='Manual import')
    crawl = sub.add_parser('collect', help='Poll configured enabled sources')
    crawl.add_argument('--config', type=Path, default=Path('config/sources.json'))
    crawl.add_argument('--interval', type=int, default=0, help='Repeat every N seconds; minimum 300; zero runs once')
    args = parser.parse_args()
    if args.command == 'collect' and args.interval and args.interval < 300:
        parser.error('--interval must be zero or at least 300 seconds')
    db = connect(args.db)
    try:
        if args.command == 'tor-check':
            from .tor import diagnose
            result = diagnose(db, args.proxy)
            print(json.dumps(result))
            if result['status'] != 'ok':
                raise SystemExit(1)
        elif args.command == 'demo':
            seed(db)
            print('48 fictional records ready. Run: python -m sentinel serve')
        elif args.command == 'monitor':
            from .monitor import monitor
            db.close()
            monitor(args.db, args.config, args.port)
        elif args.command == 'serve':
            db.close()
            serve(args.db, args.port)
        elif args.command == 'import':
            rows = json.loads(args.file.read_text())
            if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                parser.error('Import requires a JSON array of objects')
            print(json.dumps({'added': ingest(db, rows, args.source)}))
        else:
            while True:
                print(json.dumps(collect(db, args.config)), flush=True)
                if not args.interval:
                    break
                time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        db.close()


if __name__ == '__main__':
    main()
