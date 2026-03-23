# Contributing to NetScope

Thanks for your interest in contributing! This guide covers how to report issues, set up the project locally, and submit pull requests.

## Reporting Issues

- Use the [bug report](.github/ISSUE_TEMPLATE/bug_report.md) or [feature request](.github/ISSUE_TEMPLATE/feature_request.md) templates.
- Include your Python/Node version, OS, and relevant device output (redact hostnames, IPs, and credentials).

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- A Cisco lab or device for integration testing (optional)

### Backend

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Code Quality

All checks must pass before submitting a PR:

```bash
ruff check .
ruff format --check .
mypy --strict backend/
pytest -v
```

## Pull Request Guidelines

1. **Fork and branch.** Create a feature branch from `main` (e.g., `feat/add-arista-parser`).
2. **Keep changes focused.** One logical change per PR.
3. **Add tests.** Every new parser needs unit tests with real CLI output samples.
4. **Lint and format.** Run `ruff check` and `ruff format` before pushing.
5. **No secrets.** Never commit device output containing real hostnames, IPs, or credentials.
6. **Describe your change.** Include what changed, why, and how to test it.

## Project Structure

- `backend/` — FastAPI application, parsers, discovery engine
- `frontend/` — Vue 3 + Vite + Tailwind CSS + Cytoscape.js
- `tests/` — pytest test suite

See `DECISIONS.md` for architecture decisions (ADRs).
