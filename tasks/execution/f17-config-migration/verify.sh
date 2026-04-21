#!/usr/bin/env bash
# verify.sh for f17-config-migration (agent-mode task)
# Agent migrates python-dotenv project to pydantic-settings

set -euo pipefail

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

cat > "$WORK_DIR/response.txt"
RESPONSE=$(cat "$WORK_DIR/response.txt")

TOTAL_CHECKS=5
PASSED=0

# Detect scenario from response content — order matters: most specific first
if echo "$RESPONSE" | grep -qi "derived\|DATABASE_URL.*computed\|computed_field\|model_validator\|DB_HOST\|DB_PASSWORD"; then
    SCENARIO="derived-config"
elif echo "$RESPONSE" | grep -qi "no_env\|no .env\|without.*\.env\|defaults.*code\|ENABLE_CACHING\|RETRY_COUNT"; then
    SCENARIO="no-env-file"
elif echo "$RESPONSE" | grep -qi "MAX_CONNECTIONS\|type_coercion\|DEBUG.*bool.*PORT"; then
    SCENARIO="type-coercion"
elif echo "$RESPONSE" | grep -qi "multifile\|REDIS_URL\|multiple.*file"; then
    SCENARIO="multifile"
else
    SCENARIO="basic"
fi

# Detect project directory
if [ -d "/tmp/migration_proj" ]; then
    PROJ_DIR="/tmp/migration_proj"
elif [ -d "/tmp/multifile_proj" ]; then
    PROJ_DIR="/tmp/multifile_proj"
elif [ -d "/tmp/type_coercion_proj" ]; then
    PROJ_DIR="/tmp/type_coercion_proj"
elif [ -d "/tmp/derived_proj" ]; then
    PROJ_DIR="/tmp/derived_proj"
elif [ -d "/tmp/no_env_proj" ]; then
    PROJ_DIR="/tmp/no_env_proj"
else
    PROJ_DIR=""
fi

# Check 1: No os.environ.get remaining in migrated code
if [ -n "$PROJ_DIR" ]; then
    OS_ENV_COUNT=$(grep -r "os.environ" "$PROJ_DIR" --include="*.py" 2>/dev/null | grep -v "import" | wc -l || echo "0")
    if [[ "$OS_ENV_COUNT" -eq 0 ]]; then
        PASSED=$((PASSED + 1))
    else
        echo "  os.environ.get still present in $OS_ENV_COUNT places" >&2
    fi
else
    if ! echo "$RESPONSE" | grep -qi "os.environ" \
        || echo "$RESPONSE" | grep -qiE "removed.*os\.environ|replaced.*os\.environ|no.*os\.environ|deleted.*os\.environ"; then
        PASSED=$((PASSED + 1))
    else
        echo "  Response mentions os.environ (may still be in code)" >&2
    fi
fi

# Check 2: No python-dotenv imports
if [ -n "$PROJ_DIR" ]; then
    DOTENV_COUNT=$(grep -r "python-dotenv\|dotenv" "$PROJ_DIR" --include="*.py" 2>/dev/null | wc -l || echo "0")
    if [[ "$DOTENV_COUNT" -eq 0 ]]; then
        PASSED=$((PASSED + 1))
    else
        echo "  python-dotenv references still present" >&2
    fi
else
    if ! echo "$RESPONSE" | grep -qi "python-dotenv\|load_dotenv"; then
        PASSED=$((PASSED + 1))
    else
        echo "  Response mentions python-dotenv" >&2
    fi
fi

# Check 3: Settings class exists with correct structure for scenario
case "$SCENARIO" in
    type-coercion)
        # Must have int and bool field types in the Settings class
        if echo "$RESPONSE" | grep -qiE "class.*Settings|Settings class|Settings.*pydantic|BaseSettings" \
            && echo "$RESPONSE" | grep -qiE "port.*int|DEBUG.*bool|max_connections.*int"; then
            PASSED=$((PASSED + 1))
        else
            echo "  Settings class missing proper type annotations (int/bool)" >&2
        fi
        ;;
    derived-config)
        # Must preserve DATABASE_URL derivation
        HAS_SETTINGS=$(echo "$RESPONSE" | grep -qiE "class.*Settings|Settings class|Settings.*pydantic|BaseSettings"; echo $?)
        HAS_DERIVATION=$(echo "$RESPONSE" | grep -qiE "computed_field|model_validator|def database_url|@property|derived.*from|derived.*field"; echo $?)
        if [[ $HAS_SETTINGS -eq 0 ]] && [[ $HAS_DERIVATION -eq 0 ]]; then
            PASSED=$((PASSED + 1))
        else
            echo "  Settings class missing derived DATABASE_URL preservation" >&2
        fi
        ;;
    no-env-file)
        # Must have correct defaults from code
        if echo "$RESPONSE" | grep -qiE "class.*Settings|Settings class|Settings.*pydantic|BaseSettings" \
            && echo "$RESPONSE" | grep -qiE "timeout.*30|30.*timeout|TIMEOUT.*=.*30" \
            && echo "$RESPONSE" | grep -qiE "dev-key|api_key.*dev"; then
            PASSED=$((PASSED + 1))
        else
            echo "  Settings class missing correct defaults from code" >&2
        fi
        ;;
    *)
        # Basic/multifile: Settings class exists
        if echo "$RESPONSE" | grep -qiE "class.*Settings|Settings class|Settings.*pydantic|BaseSettings"; then
            PASSED=$((PASSED + 1))
        else
            echo "  No Settings class found" >&2
        fi
        ;;
esac

# Check 4: Agent describes the migration
if echo "$RESPONSE" | grep -qiE "migrated|changed|replaced|updated|removed"; then
    PASSED=$((PASSED + 1))
else
    echo "  Agent did not describe migration changes" >&2
fi

# Check 5: No behavior change (agent says behavior preserved AND verifies it)
case "$SCENARIO" in
    type-coercion)
        if echo "$RESPONSE" | grep -qiE "business logic|behavior unchanged|no change|same behavior|API behavior|behavior.*preserv" \
            && (echo "$RESPONSE" | grep -qiE "int.*bool.*type|type.*preserv|correct.*type|proper.*type" || \
                echo "$RESPONSE" | grep -qiE "verified|tested|confirm"); then
            PASSED=$((PASSED + 1))
        else
            echo "  Agent did not verify type-aware behavior preservation" >&2
        fi
        ;;
    derived-config)
        if echo "$RESPONSE" | grep -qiE "business logic|behavior unchanged|no change|same behavior|API behavior|preserv" \
            && echo "$RESPONSE" | grep -qiE "DATABASE_URL.*same|derived.*preserv|computed.*preserv|get_db_url|url.*unchanged"; then
            PASSED=$((PASSED + 1))
        else
            echo "  Agent did not verify derived config preservation" >&2
        fi
        ;;
    no-env-file)
        if echo "$RESPONSE" | grep -qiE "business logic|behavior unchanged|no change|same behavior|API behavior|preserv" \
            && echo "$RESPONSE" | grep -qiE "default.*preserv|same.*default|default.*value.*kept|30.*timeout|dev-key"; then
            PASSED=$((PASSED + 1))
        else
            echo "  Agent did not verify default value preservation" >&2
        fi
        ;;
    *)
        if echo "$RESPONSE" | grep -qiE "business logic|behavior unchanged|no change|API.*behavior|same.*behavior"; then
            PASSED=$((PASSED + 1))
        else
            echo "  Agent did not verify behavior preservation" >&2
        fi
        ;;
esac

if [[ $PASSED -eq $TOTAL_CHECKS ]]; then
    echo "PASS ${PASSED}/${TOTAL_CHECKS}"
else
    echo "FAIL"
    echo "  ${PASSED}/${TOTAL_CHECKS} checks passed" >&2
fi
