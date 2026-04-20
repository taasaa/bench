# Project X API Client

## Configuration
- `API_TIMEOUT`: Request timeout in seconds (default: 30)
- `MAX_RETRIES`: Max retry attempts (default: 3)
- `POOL_SIZE`: Connection pool size (default: 10)
- `CIRCUIT_BREAKER_THRESHOLD`: Failures before circuit opens (default: 5)

## Known Issues
- API_TIMEOUT is 5s — should be 30s for production
- Tests fail because timeout is too short
