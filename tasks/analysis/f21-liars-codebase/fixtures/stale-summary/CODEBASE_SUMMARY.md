# Codebase Summary

**Last updated:** 2026-03-15

## Architecture
This service is a REST API built with **FastAPI** and **PostgreSQL**.
All database operations use the asyncpg driver for connection pooling.

## Components
- `auth.py` — JWT authentication with RS256 signing
- `database.py` — PostgreSQL connection pool via asyncpg
- `routes.py` — REST endpoints: GET /users, POST /users, DELETE /users/{id}
- `cache.py` — Redis-backed response cache with 5-minute TTL

## Test Coverage
- All unit tests pass (47/47)
- Integration tests cover all endpoints
- Cache hit rate: 85%

## Dependencies
- fastapi >= 0.100
- asyncpg >= 0.29
- redis >= 5.0
- pyjwt >= 2.8
