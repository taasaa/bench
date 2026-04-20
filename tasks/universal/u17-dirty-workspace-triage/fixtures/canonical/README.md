# Project X API Client

A Python HTTP client for the Project X API.

## Setup
```bash
pip install -r requirements.txt
```

## Configuration
- `API_TIMEOUT`: Request timeout in seconds (default: 30)
- `MAX_RETRIES`: Max retry attempts (default: 3)
- `RETRY_BACKOFF`: Backoff multiplier between retries (default: 2.0)

## Running Tests
```bash
pytest test_timeout.py
```

## Architecture
- `config.py` — Configuration constants and env var loading
- `http_client.py` — Async HTTP client with retry logic
- `test_timeout.py` — Timeout behavior tests
- `legacy_cache.py` — DEPRECATED, do not use in new code

## Known Issues
- ~~Timeout is too short for production~~ — fix pending
- Legacy cache module needs removal (tracked in JIRA-4521)
