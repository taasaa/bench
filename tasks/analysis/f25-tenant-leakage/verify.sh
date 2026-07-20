#!/usr/bin/env bash
# verify.sh for f25-tenant-leakage
#
# Receives model response on stdin.
# Extracts the python code block and runs a cross-tenant leak test.
#
# Outputs: PASS 1/1 or FAIL

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

STDIN_FILE="$WORK_DIR/response.txt"
cat > "$STDIN_FILE"

# Extract python code
awk '/```python/{flag=1; next} /```/{flag=0} flag' "$STDIN_FILE" > "$WORK_DIR/config_loader.py"

if [[ ! -s "$WORK_DIR/config_loader.py" ]]; then
    awk '/```/{flag=!flag; next} flag' "$STDIN_FILE" > "$WORK_DIR/config_loader.py"
fi

if [[ ! -s "$WORK_DIR/config_loader.py" ]]; then
    echo "FAIL"
    echo "  Could not extract Python code block from response." >&2
    exit 0
fi

# Stub context.py
cat << 'EOF' > "$WORK_DIR/context.py"
from contextvars import ContextVar
current_tenant_id = ContextVar("tenant_id", default="public")
EOF

# Stub db.py
cat << 'EOF' > "$WORK_DIR/db.py"
import time
from context import current_tenant_id

def query_tenant_config() -> dict:
    tenant = current_tenant_id.get()
    return {"tenant": tenant, "features": ["v1"]}
EOF

# Test script
cat << 'EOF' > "$WORK_DIR/test_leak.py"
import sys
import context
try:
    import config_loader
except Exception as e:
    print(f"Error importing: {e}")
    sys.exit(1)

# Tenant A
context.current_tenant_id.set("tenant_A")
conf_a = config_loader.get_active_configuration()

# Tenant B
context.current_tenant_id.set("tenant_B")
conf_b = config_loader.get_active_configuration()

if conf_a["tenant"] == conf_b["tenant"]:
    print("LEAK_DETECTED")
    sys.exit(1)
print("SAFE")
EOF

pushd "$WORK_DIR" > /dev/null
set +e
OUTPUT=$(python test_leak.py 2>&1)
EXIT_CODE=$?
set -e
popd > /dev/null

if [[ $EXIT_CODE -ne 0 ]]; then
    if echo "$OUTPUT" | grep -q "LEAK_DETECTED"; then
        echo "FAIL"
        echo "  Cross-tenant data leak detected. Caching is unsafe." >&2
    else
        echo "FAIL"
        echo "  Code raised an exception: $OUTPUT" >&2
    fi
else
    echo "PASS 1/1"
fi
