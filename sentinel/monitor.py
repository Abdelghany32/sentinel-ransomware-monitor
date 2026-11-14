"""Run a local dashboard and a periodic collector in one foreground process."""
import json
import threading
from .collector import collect
from .store import connect
from .server import serve


def monitor(db_path, config_path, port):
    stop = threading.Event()

    def worker():
        db = connect(db_path)
        try:
            while not stop.is_set():
                try:
                    print(json.dumps(collect(db, config_path)), flush=True)
                except Exception as exc:
                    print(json.dumps({'status': 'error', 'error': f'{type(exc).__name__}: check source configuration'}), flush=True)
                stop.wait(60)
        finally:
            db.close()

    thread = threading.Thread(target=worker, name='sentinel-collector', daemon=True)
    thread.start()
    print(f'Live workspace: http://127.0.0.1:{port}/?mode=live', flush=True)
    try:
        serve(db_path, port)
    finally:
        stop.set()
        thread.join(timeout=5)
