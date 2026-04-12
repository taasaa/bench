#!/usr/bin/env bash
# verify.sh for q4-root-cause
#
# Receives model response on stdin (text diagnosing a problem).
# Checks:
#   1. Response identifies the root cause (environment mismatch, path, networking, etc.)
#   2. Response includes a specific fix command or actionable step
#   3. Response does NOT suggest the primary symptom-fixing approaches
#
# Environment:
#   SAMPLE_ID - identifies which sample (determines expected root cause and forbidden fixes)
#
# Outputs: PASS N/M or FAIL

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

TOTAL_CHECKS=3
PASSED=0

# Map SAMPLE_ID to expected root cause patterns and forbidden symptom fixes
SAMPLE="${SAMPLE_ID:-q4-pip-python-mismatch}"
case "$SAMPLE" in
    q4-pip-python-mismatch)
        # Root cause: pip and python3 are in different environments/installations
        ROOT_PATTERNS="different.*(env|install|version|python)|pip.*python.*different|pip.*not.*same.*python|which pip|which python|two.*python|multiple.*python|virtualenv|venv"
        # Specific fix: python3 -m pip, creating venv, or using full path
        FIX_PATTERNS="python3 -m pip|python -m pip|venv|virtualenv|/usr/bin/python|pip3.*--target|use.*same.*python"
        # Forbidden primary fix: pip install --user or sudo pip install (treating symptoms)
        FORBIDDEN_PATTERNS="pip install --user|sudo pip install|pip install --force"
        ;;
    q4-node-npx-mismatch)
        # Root cause: npm global bin not in PATH, or node version mismatch (nvm)
        ROOT_PATTERNS="PATH|path.*not.*include|nvm|node.*version.*mismatch|different.*node|prefix|global.*bin|bin.*directory"
        # Specific fix: add to PATH, npx, nvm use, fix npm prefix
        FIX_PATTERNS="export PATH|PATH=|nvm use|npx tsc|npm config.*prefix|source.*nvm|\\.nvm"
        # Forbidden: reinstall, npm install -g again (treating symptoms)
        FORBIDDEN_PATTERNS="npm install -g typescript|reinstall|sudo npm"
        ;;
    q4-docker-compose-port)
        # Root cause: containers use Docker network, not localhost
        ROOT_PATTERNS="docker.*(network|bridge|compose.*network)|not.*localhost|container.*network|service.*name|host.*name|different.*network|link"
        # Specific fix: use service name as hostname, or docker network config
        FIX_PATTERNS="service.*name|compose.*service|host.*=.*db|host.*=.*database|host.*=.*postgres|DATABASE_HOST|networks:|depends_on|docker.*network"
        # Forbidden: expose/publish ports, change port number (treating symptoms)
        FORBIDDEN_PATTERNS="expose.*5432|publish.*5432|ports:.*5432|change.*port|port.*forward"
        ;;
    q4-cron-path-issue)
        # Root cause: cron has minimal PATH, different environment from interactive shell
        ROOT_PATTERNS="PATH|cron.*path|cron.*environment|cron.*shell|different.*environment|minimal.*path|login.*shell|\\./bashrc|\\./profile"
        # Specific fix: set PATH in crontab, use full path to python, source profile
        FIX_PATTERNS="PATH=|SHELL=|source.*profile|source.*bashrc|/usr/bin/python3|/opt/.*/python|\\*/opt/|\\. /etc/profile|PYTHONPATH"
        # Forbidden: reinstall pandas, pip install pandas again (treating symptoms)
        FORBIDDEN_PATTERNS="pip install pandas|sudo pip|reinstall.*pandas|install.*pandas.*again"
        ;;
    *)
        ROOT_PATTERNS="different"
        FIX_PATTERNS="fix"
        FORBIDDEN_PATTERNS="reinstall"
        ;;
esac

# Check 1: Response identifies the root cause
if grep -qEi "$ROOT_PATTERNS" "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  Root cause not identified (pattern: ${ROOT_PATTERNS})" >&2
fi

# Check 2: Response includes a specific fix command or actionable step
if grep -qEi "$FIX_PATTERNS" "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  No specific fix found (pattern: ${FIX_PATTERNS})" >&2
fi

# Check 3: Response does NOT suggest forbidden symptom-fixing approaches
# Only check if the forbidden pattern appears prominently (in first half of response)
HALF_FILE="$WORK_DIR/response_half.txt"
TOTAL_LINES=$(wc -l < "$STDIN_FILE")
HALF_LINES=$((TOTAL_LINES / 2 + 1))
head -n "$HALF_LINES" "$STDIN_FILE" > "$HALF_FILE"

FORBIDDEN_FOUND=$(grep -cEi "$FORBIDDEN_PATTERNS" "$HALF_FILE" || true)

if [[ "$FORBIDDEN_FOUND" -eq 0 ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  Suggests symptom-fixing approach in first half of response" >&2
    grep -Ein "$FORBIDDEN_PATTERNS" "$HALF_FILE" >&2 || true
fi

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi
