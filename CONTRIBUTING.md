# Contributing to Bench

Thank you for your interest in contributing.

## How to Report Bugs

Open a [bug report](https://github.com/taasaa/bench/issues/new?template=bug_report.yml).
Include: Python version, OS, steps to reproduce, expected vs actual behavior, and any relevant logs.

## How to Suggest Features

Open a [feature request](https://github.com/taasaa/bench/issues/new?template=feature_request.yml).
Describe the problem you want to solve and the behavior you'd expect.

## Development Setup

```bash
# Clone the repo
git clone git@github.com:taasaa/bench.git
cd bench

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in dev mode
pip install -e ".[dev]"

# Run tests
pytest
```

## Code Style

- We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting
- Line length: 100 characters
- Target Python: 3.10+

```bash
# Lint and format check
ruff check .

# Format
ruff format .
```

## Testing Requirements

- All new features must include tests
- Bug fixes must include a regression test
- Run `pytest` locally before pushing
- CI must pass before merge

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes with clear commit messages
3. Add/update tests
4. Ensure all CI checks pass
5. Open a PR with a clear description of what changed and why

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
