# Sentinel — Ransomware Metadata Monitoring

A local research project for collecting public ransomware listing metadata and inspecting newly observed claims and trends. Includes a Python collector, SQLite database, HTTP API, and responsive browser dashboard. All bundled data is fictional. No live leak sites are contacted automatically. The opt-in `monitor` command polls a public intelligence API over HTTPS.

## Direct onion monitoring — 0.4

A direct Tor connection has now been tested against one public ransomware listing page: **3 claims observed, 1 newly inserted**. This is separate from the RansomLook HTTPS feed.

```sh
docker compose -p sentinel-tor -f deployment/tor/compose.yml up --build -d
source .venv/bin/activate
python -m sentinel tor-check
python -m sentinel monitor --config config/sources.darkweb.json
```

Open **http://127.0.0.1:8000/?mode=live**. Read the [direct onion setup and verification guide](docs/DARKWEB.fr.md). The preset polls one public listing page hourly; it does not contact operators or download leaked files. The Tor diagnostic and source availability have separate states.

## Live intelligence — 0.3

```sh
source .venv/bin/activate
python -m sentinel monitor
```

Open **http://127.0.0.1:8000/?mode=live**. This starts the dashboard and a worker polling RansomLook's public recent-post API approximately every 15 minutes. The default `serve` command still only serves the database. A first real RansomLook sync succeeded with 100 observations. Ransomware.live PRO is an optional second connector requiring an environment API key; its authenticated endpoint has not been tested here.

See the [live setup guide in French](docs/LIVE.fr.md) for credentials, attribution, rate limits, freshness semantics and coverage limitations. There is no direct dark-web connection in this preset and no stolen-content download. A recent-items feed can miss records during outages.

## Portfolio edition — 0.2

Sentinel now includes an **analyst investigation workspace**: open a claim, set its review status and priority, write notes, and inspect its assessment history. Saves use version checks to prevent stale tabs from overwriting another assessment. Source observations preserve provenance across new ingestions.

- [Architecture and API additions](docs/ARCHITECTURE.md)
- [French portfolio and interview guide](docs/PORTFOLIO.fr.md)
- [Contribution and validation commands](CONTRIBUTING.md)
- [Security boundaries](SECURITY.md)
- [Changelog](CHANGELOG.md)

The repository includes a GitHub Actions test matrix and package checks. These are configured workflows, not a claim that a hosted CI run has already succeeded. No screenshots or real-world detection metrics are fabricated.

## 1. Quick start

Requires Python 3.11 or newer. Run commands from this repository directory.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m sentinel demo
python -m sentinel serve
```

Open **http://127.0.0.1:8000**. On Windows, activate with `.venv\Scripts\activate`. The dashboard, demo generator, and JSON import use only the Python standard library; third-party packages are needed for network collection and HTML parsing.

The dashboard binds to loopback. Stop it with Ctrl+C. Use `python -m sentinel serve --port 8080` if port 8000 is occupied. The SQLite file is created at `data/sentinel.db`. To use a separate database, put `--db path/to/file.db` before the command.

## 2. What you can do

- Switch between fictional demo data and collected metadata; they never share dashboard statistics.
- Filter claims by search keyword, actor, and 7/30/90/365-day observation windows.
- See tracked claims, claims first observed in the last 24 hours, distinct actors, and watchlist matches.
- Inspect daily first-observation activity and the six most represented sectors.
- Browse ten claims per page and click an organization for metadata, source observations, analyst notes and assessment history.
- Filter by review status and assign a manual priority; a reviewed claim is not automatically a confirmed incident.
- Save watchlist keywords matched case-insensitively against organization, country, and sector.
- Export filtered records as CSV with spreadsheet formula-prefix neutralization.
- Inspect collector health and recent errors. The browser refreshes every 60 seconds; this does not trigger collection.

## 3. Import your own metadata

Create `data/metadata.json` containing a normalized array:

```json
[
  {
    "name": "Example Organization",
    "actor": "Example actor",
    "country": "France",
    "sector": "Manufacturing",
    "published_at": "2026-11-10T10:00:00Z",
    "source_url": "https://your-approved-feed.example/listing"
  }
]
```

```sh
python -m sentinel import data/metadata.json --source "Research metadata feed"
```

Select **Collected metadata** in the dashboard. `name` and `actor` are mandatory; country and sector default to `Unknown`. Dates must be ISO 8601. Dates without time zones are interpreted as UTC. Publication dates are source-reported; first-seen and last-seen are generated by the collector. These are claims, not verified breaches.

## 4. Configure collection

```sh
cp config/sources.example.json config/sources.json
```

Edit the copy. Both generic examples start disabled; the separate live preset enables only RansomLook. Replace placeholders with a source you are authorized to access and set `enabled` to `true`.

### JSON adapter

The endpoint must return a JSON array matching the import schema, with `Content-Type` containing `json`. A run observes at most 10,000 records. The endpoint itself is recorded as provenance. This adapter does not automatically translate third-party schemas: add a tested mapping in `sentinel/collector.py` if a feed uses different fields.

### HTML adapter

Configure `item_selector` for a listing card and field selectors relative to each card. `actor` is configured per source. Example markup for the included selectors:

```html
<article class="victim-card">
  <h2 class="victim-name">Example Organization</h2>
  <span class="country">France</span>
  <span class="sector">Manufacturing</span>
</article>
```

The parser extracts text only, never executes JavaScript, and never follows victim or download links. A zero-match HTML response fails the run so a changed layout is not silently treated as a healthy source. Pages rendered only by JavaScript need a different authorized metadata feed or an additional adapter.

### Tor sources

Run and maintain Tor separately, then use `socks5h://127.0.0.1:9050` (or your actual local SOCKS endpoint). `socks5h` resolves hostnames through the proxy. The collector refuses onion URLs without this proxy scheme. It does not install Tor, discover onion addresses, bypass authentication, or fetch leaked archives.

```sh
# One collection pass
python -m sentinel collect --config config/sources.json

# A persistent foreground worker; wait 15 minutes after each completed pass
python -m sentinel collect --config config/sources.json --interval 900
```

Run the collector in a second terminal alongside the dashboard. Intervals below five minutes are rejected. Requests are sequential with per-source delays, connection/read timeouts, a streaming time budget, a 2 MB decompressed response cap, content-type checks, and no redirects. A read can extend beyond the streaming budget by the socket timeout. Failures are logged and retried on the next scheduled pass; there is no immediate retry loop. Respect each source's applicable access restrictions and permitted polling rate.

The bundled RansomLook adapter has passed a live metadata sync; generic HTML sources and authenticated PRO remain unverified. You must validate selectors and feed mappings with fixtures before enabling each source.

## 5. Architecture

```text
Approved JSON endpoint / public HTML listing
                    |
       bounded HTTP request (optional Tor SOCKS)
                    |
         parser -> normalization / validation
                    |
     identity hash -> insert or refresh last_seen
                    |
             SQLite database
                    |
       local HTTP API -> browser dashboard
```

| File | Responsibility |
| --- | --- |
| `sentinel/__main__.py` | CLI, import, demo, scheduler, server startup |
| `sentinel/collector.py` | Network controls, JSON/HTML adapters, run logging |
| `sentinel/store.py` | Schema, validation, deduplication, filtering |
| `sentinel/server.py` | HTTP routes, watchlist mutations, export |
| `sentinel/static/` | Dependency-free browser UI |
| `config/sources.example.json` | Disabled configuration examples |
| `tests/test_sentinel.py` | Store, parser, network policy, API tests |
| `docs/PROJECT.md` | Design decisions, evaluation, and expansion plan |

## 6. API

| Method | Route | Result |
| --- | --- | --- |
| GET | `/api/health` | Service status |
| GET | `/api/dashboard` | Filtered claims, aggregates, watchlist, recent runs |
| GET | `/api/export` | Filtered CSV |
| POST | `/api/watchlist` | Add/delete a keyword |

Dashboard/export parameters: `mode=demo|live`, `days=7|30|90|365`, `actor=<exact actor>`, `q=<substring>`, `status=<review status>`. Defaults are demo and 30 days. POST JSON example: `{"term":"Healthcare","action":"add"}`; use `delete` to remove. Writes require JSON and reject a mismatched browser Origin.

## 7. Tests

```sh
python -m unittest discover -s tests -v
node --check sentinel/static/app.js  # optional Node.js syntax check
```

Tests cover case-insensitive duplicate detection, preservation of first observation, demo isolation, invalid-batch atomicity, search handling, HTML parsing, malformed JSON feeds, onion proxy policy, HTTP routes, watchlist persistence, invalid query handling, cross-origin write rejection, and CSV formula neutralization. Tests use temporary databases and a loopback server; they do not contact live leak sites.

## 8. Operational limits

This is a working local MVP, not an internet-facing service. It has no login, roles, email notifications, retention job, distributed scheduler, or immutable evidence archive. Do not expose the development HTTP server publicly. For a team deployment, replace it with a production web server and authenticated API behind TLS, extend the local host/origin controls with deployment-specific host validation and robust CSRF protection, and isolate the collector from sensitive networks.

Source configuration is trusted local operator input: arbitrary HTTP targets are allowed. Never expose source editing to untrusted users without destination restrictions. Database queries use bound parameters; source text is inserted into the page using text nodes rather than HTML. The project stores normalized metadata, not leaked files or raw source pages.

Identity is casefolded actor + organization name (plus demo/live partition). Repeated listings of the same organization by the same actor collapse into one claim; name variants and repeat incidents need analyst review. First-source provenance and original metadata are retained on duplicates; only last-seen updates. Per-source observation summaries now preserve first/last sighting and counts for new ingestions. They do not retain every response or subsequent metadata corrections. Legacy observation history is not reconstructed.

Trends reflect monitored-source coverage, publication behavior, collection outages, and ingestion timing. They do not estimate total ransomware incidence. Initial imports appear as new observations even when the source publication is old. Watchlist matches are local indicators, not delivered alerts. Assessment history is application-level and not tamper-proof or attributed to authenticated users. All matching records are returned to the browser before pagination; move filtering, pagination, and aggregates into SQL for large datasets.

Stop the application and collector before copying the SQLite file for a simple backup, or use SQLite's online backup API. Re-running `demo` resets demo observation dates. Real metadata is never seeded automatically.

## References

- [Requests: proxies and SOCKS remote DNS](https://requests.readthedocs.io/en/stable/user/advanced/)
- [Python SQLite: parameter substitution and transactions](https://docs.python.org/3.11/library/sqlite3.html)

## Developer installation and package

```sh
python -m pip install -e '.[dev]'
python -m coverage run -m unittest discover -s tests -v
python -m coverage report
python -m build
python scripts/check_wheel.py
```

After installation, `sentinel demo` and `sentinel serve` are equivalent to the module commands. The wheel includes dashboard assets. Python 3.11–3.14 are configured in CI; see the workflow output for actual platform results.
