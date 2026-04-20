# API Conventions

When writing API client functions for this project:

1. All URLs use `https://api.example.com/` as the base
2. All functions should return parsed JSON (dict or list)
3. Use query parameters for filters, JSON body for creation/updates
4. Functions that don't make HTTP calls should be pure (no side effects)
