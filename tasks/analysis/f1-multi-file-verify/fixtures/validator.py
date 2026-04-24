"""Configuration validator module."""

from typing import Any, Dict, List

# Schema definition: each entry describes an expected field.
# The "kind" field specifies the expected type.
CONFIG_SCHEMA = {
    "server": {
        "kind": "object",
        "required": True,
        "properties": {
            "host": {"kind": "string", "required": True},
            "port": {"kind": "integer", "required": True},
            "timeout": {"kind": "integer", "required": False},
        },
    },
    "logging": {
        "kind": "object",
        "required": True,
        "properties": {
            "level": {"kind": "string", "required": True},
            "format": {"kind": "string", "required": False},
        },
    },
}


def validate_type(value: Any, expected_kind: str) -> bool:
    """Check if a value matches the expected kind."""
    type_map = {
        "string": str,
        "integer": int,
        "object": dict,
        "array": list,
        "boolean": bool,
    }
    expected_type = type_map.get(expected_kind)
    if expected_type is None:
        return False
    return isinstance(value, expected_type)


def validate_config(config: dict[str, Any]) -> list[str]:
    """Validate a config dictionary against the schema.

    Returns a list of error messages. Empty list means valid.
    """
    errors: list[str] = []

    for section_key, section_schema in CONFIG_SCHEMA.items():
        # BUG: checks "type" field but schema uses "kind"
        section_kind = section_schema.get("type")  # should be "kind"
        is_required = section_schema.get("required", False)

        if section_key not in config:
            if is_required:
                errors.append(f"Missing required section: {section_key}")
            continue

        section_value = config[section_key]

        if section_kind and not validate_type(section_value, section_kind):
            errors.append(f"Section '{section_key}' has wrong type: expected {section_kind}")

        # Validate sub-properties
        if "properties" in section_schema:
            for prop_key, prop_schema in section_schema["properties"].items():
                prop_kind = prop_schema.get("type")  # BUG: should be "kind"
                prop_required = prop_schema.get("required", False)

                if prop_key not in section_value:
                    if prop_required:
                        errors.append(f"Missing required property: {section_key}.{prop_key}")
                    continue

                if prop_kind and not validate_type(section_value[prop_key], prop_kind):
                    errors.append(f"Property '{section_key}.{prop_key}' has wrong type")

    return errors
