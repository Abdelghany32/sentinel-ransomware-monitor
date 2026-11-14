# Changelog

## 0.4.0

- Add a dedicated local Docker Tor client, route diagnostic and dashboard transport labels.
- Validate v3 onion checksums and require local SOCKS remote-DNS transport for direct modes.
- Add a directly verified Endzone public-listing adapter and combined dark-web preset.
- Add status-only onion checks, schema-4 transport metadata and regression tests.

## 0.3.0

- Add a verified RansomLook recent-publication connector and optional Ransomware.live PRO adapter.
- Add `monitor` to run the local dashboard and periodic collector together.
- Persist per-source polling deadlines, failures, last success and rate-limit backoff.
- Store provider observation dates separately from local ingestion and claimed publication dates.
- Display source freshness and provenance in the dashboard; exclude raw descriptions and download links.

## 0.2.0

- Add analyst assessments with workflow status, priority, notes and transactional history.
- Reject stale edits through version checks and HTTP 409 responses.
- Track per-source observations while retaining original claim metadata.
- Add backward-compatible schema initialization and migration tests.
- Reject invalid identity types, malformed mutation payloads, and unexpected Host headers.
- Preserve the live dataset flag (`0`) in CSV exports.
- Add an installable package and CLI entry point, CI matrix, dependency update configuration and wheel asset check.
- Add contribution, security, architecture and French portfolio guides.

## 0.1.0

- Local metadata collector, SQLite store, fictional dataset and dashboard.
- Filters, watchlist, CSV export, basic trends and collector run history.
