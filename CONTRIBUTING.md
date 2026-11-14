# Contributing

Use Python 3.11+ and a virtual environment:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m coverage run -m unittest discover -s tests -v
python -m coverage report
node --check sentinel/static/app.js
python -m build
python scripts/check_wheel.py
```

Keep source adapters small and add fictional parser fixtures. Tests must not contact live ransomware sites. Add regression tests for changes to ingestion, schema, API behavior, or investigations. Keep schema changes additive or provide an explicit migration and compatibility test. Explain the resulting behavior and test evidence in each pull request.

UI changes need manual keyboard/mobile checks and a screenshot from a fictional dataset. Never claim browser validation if only syntax checks were run. Do not commit databases, private source configuration, collection output, credentials, or analyst notes.

The GitHub workflow runs tests across Python 3.11–3.14, prints branch coverage, checks JavaScript syntax, builds distributions, and checks wheel assets. Coverage is reported, not enforced at an invented threshold. Dependency updates are configured through Dependabot.
