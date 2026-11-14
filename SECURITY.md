# Security boundaries

Sentinel is a local, single-user research tool. It is not approved for internet-facing deployment.

## Trust model

- Source configuration and local filesystem access belong to the trusted operator.
- Source response bodies, imported metadata, and analyst notes are untrusted text.
- The dashboard listens on IPv4 loopback and accepts only its loopback/localhost Host header with the actual port.
- Browser writes require JSON and reject mismatched Origin headers. There is no CORS allowance.
- Requests have a 10-second socket timeout and mutation bodies have a 32 KB bound.
- SQL values are bound parameters. Browser source text is rendered through text nodes.
- Onion fetches require SOCKS remote DNS. Redirects are disabled and response bodies are bounded.

## Limitations

Local processes can access the unauthenticated API. Host/Origin checks do not create user authentication. The Python HTTP server is for local use, not exposed deployments. Source URLs are operator-trusted and do not have an SSRF destination allowlist. Do not make configuration editable by remote users.

Assessment history records application changes transactionally, but is not tamper-proof, signed, or attributed to authenticated people. Investigation notes may contain sensitive information; keep the database out of public repositories. No encryption-at-rest or retention policy is implemented.

## Reporting

Do not put secrets, leaked material, real victim data, or working exploit details into public issues. Until a private reporting channel is configured by the repository owner, share only a minimal fictional reproduction with the owner through an established private channel. No response SLA is claimed.

## Direct Tor mode

The optional Docker Tor client exposes only a loopback SOCKS port. `onion_html` and `onion_status` validate v3 addresses and require local SOCKS remote DNS, without fallback. A public listing response is held transiently in memory for parsing; links, scripts, and leaked archives are not fetched. Tor routing is not a guarantee of anonymity or source authenticity. See [direct mode](docs/DARKWEB.fr.md).
