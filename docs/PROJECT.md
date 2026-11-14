# Detailed project design and evaluation

The original MVP design below is supplemented by [the current architecture](ARCHITECTURE.md). Version 0.2 adds assessments, transactional history, per-source provenance summaries and package/CI tooling. Future-work items below refer to capabilities beyond those summaries.

## Problem and scope

An analyst needs to notice newly listed organizations without manually revisiting multiple public ransomware listing pages. Sentinel consolidates metadata and offers an auditable first-observation timestamp, simple source health, descriptive trend charts, and organization/sector keyword matching. It collects allegations made by sources; confirmation requires independent investigation.

The MVP covers collection, validation, persistence, inspection, and export. It deliberately does not acquire stolen documents, execute page scripts, or interact with threat actors. No source credentials are required by the bundled implementation.

## Data model

`victims`: deterministic identity, organization name, actor, country, sector, source label, source URL, optional claimed publication timestamp, first observation, latest observation, and a demo partition flag.

`watchlist`: unique keyword strings. Matching is case-insensitive substring matching; spelling variants, synonyms, and domains are not automatically resolved.

`runs`: monotonically increasing ID, source label, UTC start time, success/error status, number of new identities, observed record count, and sanitized failure description. Disabled sources do not create runs. No enabled sources means a successful empty pass, not proof that collection works.

SQLite uses write-ahead logging and a 30-second busy timeout. Each ingestion validates all rows before committing. A malformed row fails the whole source batch. Schema creation is idempotent; a migration framework would be needed before changing an existing schema.

## Ingestion algorithm

1. Load trusted configuration and skip disabled sources.
2. Validate the URL and enforce remote-DNS SOCKS for onion hosts.
3. Fetch one bounded response without following redirects.
4. Parse JSON records or text from configured HTML selectors.
5. Require organization and actor, normalize whitespace and dates, default missing dimensions to Unknown.
6. Hash demo/live partition, casefolded actor, and casefolded organization.
7. Insert unseen identities; refresh last-seen for existing identities while preserving their initial data.
8. Commit records, log success/failure, wait the configured source delay.
9. Continue to the next source even when an earlier source fails.

No automatic taxonomy inference occurs. A source's country or sector may be missing or incorrect. An analyst should curate a country/sector taxonomy when integrating multiple feeds.

## Analyst workflow

1. Run the fictional demo and inspect a listing's full metadata.
2. Import a small trusted JSON sample; switch to Collected metadata.
3. Add a keyword and verify that matching organizations are highlighted.
4. Prepare one enabled source, test its parser against a saved non-sensitive listing fixture, then collect once.
5. Inspect Collection health. Compare observed counts with the expected sample and investigate errors.
6. Enable recurring collection only after the one-pass output is correct.
7. Review new claims, verify them independently, and export a filtered CSV for reporting.

## Evaluation plan

| Property | Evaluation |
| --- | --- |
| Parser correctness | Compare extracted metadata against manually labeled fixtures for every source layout |
| Duplicate handling | Re-ingest identical/case-varied samples; new count should be zero |
| Observation fidelity | Ensure first-seen remains unchanged and last-seen advances |
| Failure isolation | Make one source fail and verify later enabled sources still run |
| Watchlist relevance | Measure false positives on common keywords and document substring behavior |
| Collection latency | Measure time from a known test listing's publication to its first observation |
| Coverage | Report enabled sources, last successful polls, and known outages alongside trends |
| UI correctness | Check filtering, pagination, empty states, export, and keyword persistence at desktop/mobile sizes |

The bundled automated tests validate local behavior. They do not establish real-world detection accuracy or source availability. No external dataset or live Tor integration was tested during implementation.

## Security boundaries

Treat the collector as a network-facing untrusted-content processor. Run it with a low-privilege account in an isolated environment. The configured endpoint is trusted operator input; the returned body is not. Dependencies must be maintained and reviewed. Only plain text metadata reaches the frontend, with a restrictive content policy and no clickable external source links.

The local dashboard is single-user and unauthenticated. Its loopback binding is a development convenience, not a production security architecture. Before remote deployment, introduce authenticated access, host allowlists, request limits, robust CSRF controls, HTTPS, audit logs, and operational monitoring. Never commit private collected datasets or proxy credentials to source control.

## Expansion roadmap

1. **Source adapters:** named adapters with fixture-based tests, schema versions, per-source health thresholds, and change detection.
2. **Provenance:** separate organization, incident, and observation tables so multiple sources and repeated incidents remain distinguishable.
3. **Alert delivery:** durable match events with acknowledgments and deduplicated email/webhook queues, only to configured destinations.
4. **Analysis:** coverage-adjusted comparisons, explicit publication-versus-observation views, and transparent anomaly thresholds with baseline windows.
5. **Scale:** indexed SQL filtering, server-side pagination, migrations, retention, and PostgreSQL when concurrency warrants it.
6. **Team operations:** production API framework, authentication, roles, deployment automation, monitored worker service, backups, and recovery tests.

For an academic report, include the problem statement, collection boundaries, architecture, schema, implementation walkthrough, fixture-based evaluation results, screenshots from your own run, bias/coverage discussion, and future work. Describe simulated and collected data separately; do not report demo counts as real incident statistics.
