# Project X API Client

## Configuration
- `API_TIMEOUT`: Request timeout (default: 30)
- `MAX_RETRIES`: Max retries (default: 3)
- `DEBUG`: Debug mode (default: False)

## Known Issues
- Timeout too short for production (API_TIMEOUT = 5)
- Debug mode left on in production config
