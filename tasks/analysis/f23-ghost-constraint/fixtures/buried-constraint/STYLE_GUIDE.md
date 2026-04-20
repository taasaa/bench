# Project Style Guide

All code in this project must follow these conventions:

## Naming
- Functions and variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`

## Type Hints
All function definitions must include type hints for parameters and return types.

## HTTP Client
Use `httpx` for all HTTP requests. The `requests` library is deprecated in this project.

## Error Handling
- Use specific exception types (not bare `except:`)
- Always include error messages in raises
