#!/usr/bin/env bash
# verify.sh for f10-env-mismatch
#
# Receives model response on stdin.
# Checks:
#   1. Identifies version/environment mismatch between two contexts
#   2. Identifies the mechanism (shebang, alias, PATH, JAVA_HOME, .nvmrc, rbenv)
#   3. Suggests fix addressing the root cause (fix shebang, activate venv, nvm use, set JAVA_HOME)
#   4. Does NOT suggest simply reinstalling the package
#
# Environment:
#   SAMPLE_ID - identifies which sample
#
# Outputs: PASS N/M or FAIL

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

TOTAL_CHECKS=4
PASSED=0

# Map SAMPLE_ID to expected patterns
SAMPLE="${SAMPLE_ID:-f10-python-venv}"
case "$SAMPLE" in
    f10-python-venv)
        MISMATCH_PATTERNS="3\.11.*3\.12|3\.12.*3\.11|venv.*python3\.11.*alias.*3\.12|version.*mismatch|different.*python|shebang.*resolv|alias.*python.*3\.12|python.*3\.11.*venv.*3\.12|two.*python"
        MECHANISM_PATTERNS="shebang|#!/usr/bin/env python|alias|PATH.*resolv|virtualenv|venv.*activ|\.venv"
        FIX_PATTERNS="shebang.*python3\.11|activ.*venv|source.*\.venv|change.*shebang|fix.*shebang|#!/usr/bin/python3\.11|use.*python3\.11|\.venv/bin/python"
        FORBIDDEN_PATTERNS="pip install.*debugpy|reinstall.*debugpy|install debugpy"
        ;;
    f10-node-nvm)
        MISMATCH_PATTERNS="18.*20|20.*18|node.*version.*mismatch|nvm.*default.*18|\.nvmrc.*20|v18.*v20|v20.*v18|different.*node.*version"
        MECHANISM_PATTERNS="nvm|\.nvmrc|node.*version.*manager|default.*node|nvm.*use|nvm.*alias"
        FIX_PATTERNS="nvm use 20|nvm use|source.*nvm|\.nvmrc|nvm alias default 20|auto.*nvm|avn|nvm.*exec"
        FORBIDDEN_PATTERNS="npm install.*express|reinstall.*express|install.*express.*again"
        ;;
    f10-ruby-rbenv)
        MISMATCH_PATTERNS="3\.1.*3\.2|3\.2.*3\.1|rbenv.*local.*3\.2.*shell.*3\.1|version.*mismatch|different.*ruby|ruby.*3\.1.*3\.2"
        MECHANISM_PATTERNS="rbenv|\.ruby-version|PATH.*rbenv|rbenv.*shims|rbenv.*local|rbenv.*shell"
        FIX_PATTERNS="rbenv shell 3\.2|rbenv local|rbenv global|eval.*rbenv|source.*rbenv|\.ruby-version|rbenv.*rehash"
        FORBIDDEN_PATTERNS="gem install.*sidekiq|reinstall.*sidekiq|install.*sidekiq.*again"
        ;;
    f10-java-home)
        MISMATCH_PATTERNS="JDK.*17.*21|17.*21|JAVA_HOME.*17.*project.*21|java.*17.*need.*21|version.*mismatch|different.*jdk"
        MECHANISM_PATTERNS="JAVA_HOME|jdk.*version|java.*home|/usr/libexec/java_home"
        FIX_PATTERNS="JAVA_HOME.*21|export JAVA_HOME.*21|set.*JAVA_HOME|java_home.*21|JDK.*21|use.*jdk.*21|/usr/libexec/java_home.*21"
        FORBIDDEN_PATTERNS="mvn.*clean.*install|reinstall.*dependencies|mvn dependency|install.*again"
        ;;
    *)
        MISMATCH_PATTERNS="mismatch"
        MECHANISM_PATTERNS="mechanism"
        FIX_PATTERNS="fix"
        FORBIDDEN_PATTERNS="reinstall"
        ;;
esac

# Check 1: Identifies version/environment mismatch between two contexts
if grep -qEi "$MISMATCH_PATTERNS" "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  Version/environment mismatch not identified (pattern: ${MISMATCH_PATTERNS})" >&2
fi

# Check 2: Identifies the mechanism
if grep -qEi "$MECHANISM_PATTERNS" "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  Mechanism not identified (pattern: ${MECHANISM_PATTERNS})" >&2
fi

# Check 3: Suggests fix addressing the root cause
if grep -qEi "$FIX_PATTERNS" "$STDIN_FILE"; then
    PASSED=$((PASSED + 1))
else
    echo "  No specific root-cause fix found (pattern: ${FIX_PATTERNS})" >&2
fi

# Check 4: Does NOT suggest simply reinstalling the package
FORBIDDEN_FOUND=$(grep -cEi "$FORBIDDEN_PATTERNS" "$STDIN_FILE" || true)
if [[ "$FORBIDDEN_FOUND" -eq 0 ]]; then
    PASSED=$((PASSED + 1))
else
    echo "  Suggests reinstalling the package (symptom fix)" >&2
    grep -Ein "$FORBIDDEN_PATTERNS" "$STDIN_FILE" >&2 || true
fi

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi
