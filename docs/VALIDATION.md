# Validation record — 0.4

RansomLook passed a live HTTPS sync: 100 public metadata records observed and 100 local claims added. Authenticated Ransomware.live PRO remains unverified without an API key.

Local validation on Python 3.14.4:

| Check | Observed result |
| --- | --- |
| Editable installation in `.venv` | Passed with development extras |
| Automated suite | 48 tests passed |
| Coverage.py combined statement/branch coverage | 91% over `sentinel` |
| Store coverage | 95% |
| Collector coverage | 92% |
| CLI coverage | 84% |
| HTTP server coverage | 86% |
| JavaScript syntax | Passed `node --check` |
| Wheel/source distribution build | Passed |
| Wheel browser assets | HTML, CSS, JavaScript verified |

Reproduce using the commands in [CONTRIBUTING.md](../CONTRIBUTING.md). Coverage measures executed code, not proof of security or real-world detection accuracy. It does not measure frontend behavior. The uncovered server paths include server lifecycle and error branches; the tests do not simulate production load.

## Not verified

- Visual/browser interaction: browser automation service was unavailable.
- GitHub Actions execution: workflow configured locally, not run on GitHub.
- Other Python versions: configured in CI, not executed locally.
- Authenticated PRO remains unverified. Direct Tor bootstrap, route check and one public onion listing adapter were exercised successfully.
- Deployment hardening and external security audit: outside the local portfolio scope.

Direct onion verification: Tor bootstrapped to 100%; route diagnostic passed; one public page returned HTML; 3 claims observed, 1 new local identity, 2 deduplicated. UI rendering remains unverified.
