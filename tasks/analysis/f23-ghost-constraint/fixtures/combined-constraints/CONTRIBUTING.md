# Contributing Guide

## Code Style Requirements

Before writing any code for this project, please follow these mandatory conventions:

### Naming Convention
All function and variable names must use **snake_case**. No camelCase.

### Type Annotations
Every function definition must include type hints for all parameters and the return type.

### HTTP Library
We use **httpx** for HTTP requests. Do NOT use the `requests` library.

### Example

```python
import httpx

def fetch_user(user_id: str) -> dict:
    """Fetch a user by ID."""
    response = httpx.get(f"https://api.example.com/users/{user_id}")
    return response.json()
```

This example follows all three conventions: snake_case name, type hints, and httpx.
