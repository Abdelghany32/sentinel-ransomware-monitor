import hashlib
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS victims (
      id TEXT PRIMARY KEY, name TEXT NOT NULL, actor TEXT NOT NULL,
      country TEXT NOT NULL, sector TEXT NOT NULL, source TEXT NOT NULL,
      source_url TEXT NOT NULL, published_at TEXT, first_seen TEXT NOT NULL,
      last_seen TEXT NOT NULL, demo INTEGER NOT NULL DEFAULT 0);
    CREATE INDEX IF NOT EXISTS victims_seen ON victims(first_seen);
    CREATE TABLE IF NOT EXISTS watchlist (term TEXT PRIMARY KEY);
    CREATE TABLE IF NOT EXISTS runs (
      id INTEGER PRIMARY KEY, source TEXT, started_at TEXT, status TEXT,
      added INTEGER, observed INTEGER, error TEXT);
    ''')
    # Additive migration: existing claims and timestamps remain intact.
    db.executescript("""
    CREATE TABLE IF NOT EXISTS investigations (
      victim_id TEXT PRIMARY KEY REFERENCES victims(id),
      status TEXT NOT NULL DEFAULT 'new', priority TEXT NOT NULL DEFAULT 'medium',
      notes TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL DEFAULT 0,
      updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS audit_events (
      id INTEGER PRIMARY KEY, victim_id TEXT NOT NULL REFERENCES victims(id),
      created_at TEXT NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS observations (
      victim_id TEXT NOT NULL REFERENCES victims(id), source TEXT NOT NULL,
      source_url TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
      sightings INTEGER NOT NULL DEFAULT 1,
      PRIMARY KEY(victim_id, source, source_url));
    CREATE INDEX IF NOT EXISTS audit_victim ON audit_events(victim_id, id);
    CREATE TABLE IF NOT EXISTS source_state (
      name TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 1,
      last_attempt TEXT, last_success TEXT, next_poll TEXT,
      failures INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '',
      latest_source_at TEXT, interval_seconds INTEGER NOT NULL DEFAULT 900);
    CREATE TABLE IF NOT EXISTS transport_checks (
      proxy TEXT PRIMARY KEY, checked_at TEXT NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL);
    PRAGMA user_version=4;
    """)
    columns = {r['name'] for r in db.execute('PRAGMA table_info(observations)')}
    if 'source_observed_at' not in columns:
        db.execute('ALTER TABLE observations ADD COLUMN source_observed_at TEXT')
        db.commit()
    source_columns = {r['name'] for r in db.execute('PRAGMA table_info(source_state)')}
    if 'transport' not in source_columns:
        db.execute("ALTER TABLE source_state ADD COLUMN transport TEXT NOT NULL DEFAULT 'https_feed'")
        db.commit()
    return db


def ingest(db, rows, source, demo=False):
    stamp = now()
    prepared = []
    from .providers import timestamp
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('name'), str) or not isinstance(row.get('actor'), str):
            raise ValueError('name and actor must be strings')
        name, actor = row['name'].strip(), row['actor'].strip()
        if not name or not actor or len(name) > 300 or len(actor) > 100:
            raise ValueError('Each record needs name (1–300 chars) and actor (1–100 chars)')
        published = row.get('published_at') or None
        if published:
            parsed = datetime.fromisoformat(str(published).replace('Z', '+00:00'))
            published = parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()
        # Same actor / organization is one tracked claim, across multiple sources.
        key = hashlib.sha256(f'{int(demo)}|{actor.casefold()}|{name.casefold()}'.encode()).hexdigest()[:24]
        prepared.append(((key, name, actor, str(row.get('country') or 'Unknown')[:100],
                          str(row.get('sector') or 'Unknown')[:100], source,
                          str(row.get('source_url') or '')[:2000], published, stamp, stamp, int(demo)), timestamp(row.get('source_observed_at'))))
    added = 0
    with db:
        for values, source_observed_at in prepared:
            cur = db.execute('INSERT OR IGNORE INTO victims VALUES (?,?,?,?,?,?,?,?,?,?,?)', values)
            added += cur.rowcount
            db.execute('UPDATE victims SET last_seen=? WHERE id=?', (stamp, values[0]))
            db.execute('''INSERT INTO observations(victim_id,source,source_url,first_seen,last_seen,source_observed_at)
                          VALUES(?,?,?,?,?,?) ON CONFLICT(victim_id,source,source_url)
                          DO UPDATE SET last_seen=excluded.last_seen, sightings=sightings+1,
                          source_observed_at=COALESCE(excluded.source_observed_at,observations.source_observed_at)''',
                       (values[0], source, values[6], stamp, stamp, source_observed_at))
    return added


def records(db, query='', actor='', days=30, mode='demo'):
    cutoff = (datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
              - timedelta(days=days - 1)).isoformat()
    rows = db.execute("""SELECT v.*, COALESCE(i.status,'new') AS status,
                      COALESCE(i.priority,'medium') AS priority
                      FROM victims v LEFT JOIN investigations i ON i.victim_id=v.id
                      WHERE v.first_seen>=? AND v.demo=? ORDER BY v.first_seen DESC,v.id""",
                      (cutoff, int(mode == 'demo'))).fetchall()
    query = query.casefold()
    return [dict(r) for r in rows if (not actor or r['actor'] == actor) and
            query in ' '.join((r['name'], r['actor'], r['country'], r['sector'])).casefold()]


def seed(db):
    names = ['Cedar', 'Northstar', 'Bluewater', 'Juniper', 'Silverline', 'Orchard', 'Summit', 'Harbor']
    sectors = ['Manufacturing', 'Healthcare', 'Technology', 'Retail', 'Education', 'Logistics']
    rows = [{'name': f'{names[i % 8]} {sectors[i % 6]} {i + 1:02d} (fictional)',
             'actor': ['Orion (demo)', 'Vesper (demo)', 'Cinder (demo)'][i % 3],
             'country': ['United States', 'France', 'Germany', 'United Kingdom', 'Canada'][i % 5],
             'sector': sectors[i % 6]} for i in range(48)]
    ingest(db, rows, 'Fictional training dataset', demo=True)
    with db:
        for i, row in enumerate(db.execute('SELECT id FROM victims WHERE demo=1 ORDER BY name')):
            stamp = (datetime.now(timezone.utc) - timedelta(days=(i * 7) % 29, hours=i % 12)).isoformat()
            db.execute('UPDATE victims SET first_seen=?, last_seen=? WHERE id=?', (stamp, stamp, row['id']))


STATUSES = ('new', 'investigating', 'reviewed', 'dismissed')
PRIORITIES = ('low', 'medium', 'high')


class ConflictError(Exception):
    """Another browser changed this investigation; reload before saving."""


def investigation(db, victim_id):
    if not db.execute('SELECT 1 FROM victims WHERE id=?', (victim_id,)).fetchone():
        raise LookupError('Claim not found')
    row = db.execute('SELECT * FROM investigations WHERE victim_id=?', (victim_id,)).fetchone()
    result = dict(row) if row else dict(victim_id=victim_id, status='new', priority='medium',
                                       notes='', version=0, updated_at='')
    result['history'] = [dict(r) for r in db.execute(
        'SELECT * FROM audit_events WHERE victim_id=? ORDER BY id DESC LIMIT 50', (victim_id,))]
    result['observations'] = [dict(r) for r in db.execute(
        'SELECT * FROM observations WHERE victim_id=? ORDER BY last_seen DESC', (victim_id,))]
    return result


def update_investigation(db, victim_id, payload):
    status, priority, notes, version = (payload.get(k) for k in ('status', 'priority', 'notes', 'version'))
    if (status not in STATUSES or priority not in PRIORITIES or not isinstance(notes, str)
            or len(notes) > 5000 or type(version) is not int or version < 0):
        raise ValueError('Invalid status, priority, notes (max 5000), or version')
    # Serialize read-modify-write and reject stale saves rather than losing notes.
    with db:
        db.execute('BEGIN IMMEDIATE')
        before = investigation(db, victim_id)
        if before['version'] != version:
            raise ConflictError('This investigation changed. Reopen it before saving.')
        after = dict(status=status, priority=priority, notes=notes, version=version+1)
        stamp = now()
        db.execute("""INSERT INTO investigations VALUES(?,?,?,?,?,?)
                      ON CONFLICT(victim_id) DO UPDATE SET status=excluded.status,
                      priority=excluded.priority, notes=excluded.notes,
                      version=excluded.version, updated_at=excluded.updated_at""",
                   (victim_id, status, priority, notes, version+1, stamp))
        db.execute('INSERT INTO audit_events(victim_id,created_at,before_json,after_json) VALUES(?,?,?,?)',
                   (victim_id, stamp, json.dumps({k: before[k] for k in after}), json.dumps(after)))
    return investigation(db, victim_id)
