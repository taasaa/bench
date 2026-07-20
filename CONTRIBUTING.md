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

# Install core and dev dependencies
pip install -e ".[dev]"

# (Optional) Install Bayesian IRT support dependencies
# Note: On macOS, this requires Homebrew LLVM 20.x to compile llvmlite:
#   brew install llvm@20
# Then pass the config and prefix paths to pip:
CMAKE_PREFIX_PATH=$(brew --prefix llvm@20) LLVM_CONFIG=$(brew --prefix llvm@20)/bin/llvm-config pip install -e ".[irt]"

# (Optional) Populate baseline reference data (needed for token/latency/cost ratio calculations)
# Note: the baselines/ directory is gitignored; run the baseline command to populate it from cache:
python -m bench_cli baseline

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
