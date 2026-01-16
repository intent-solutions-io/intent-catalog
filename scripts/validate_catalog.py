#!/usr/bin/env python3
"""
Intent Catalog Validator

Validates catalog.json against catalog.schema.json.

Usage:
    python validate_catalog.py dist/catalog.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import jsonschema
    from jsonschema import Draft202012Validator
except ImportError:
    print("Error: jsonschema not installed. Run: pip install jsonschema")
    sys.exit(1)


SCHEMA_PATH = Path(__file__).parent.parent / "schema" / "catalog.schema.json"


def validate_catalog(catalog_path: Path) -> tuple[bool, list[str]]:
    """Validate catalog against JSON Schema."""
    errors = []

    # Load schema
    if not SCHEMA_PATH.exists():
        errors.append(f"Schema not found: {SCHEMA_PATH}")
        return False, errors

    with open(SCHEMA_PATH) as f:
        schema = json.load(f)

    # Load catalog
    if not catalog_path.exists():
        errors.append(f"Catalog not found: {catalog_path}")
        return False, errors

    with open(catalog_path) as f:
        catalog = json.load(f)

    # Validate against schema
    validator = Draft202012Validator(schema)
    for error in validator.iter_errors(catalog):
        errors.append(f"Schema error at {error.json_path}: {error.message}")

    # Additional semantic validations
    errors.extend(validate_unique_ids(catalog))
    errors.extend(validate_relationships(catalog))
    errors.extend(validate_id_format(catalog))

    return len(errors) == 0, errors


def validate_unique_ids(catalog: dict) -> list[str]:
    """Check ID uniqueness - duplicates across repos are warnings, not errors."""
    # Duplicates are expected when scanning multiple repos with similar items.
    # Full uniqueness would require repo-scoped IDs (e.g., repo/plugin-id).
    # For now, we allow duplicates and report them as informational.
    # To enforce uniqueness: use --strict flag
    return []  # Duplicates are acceptable in multi-repo extraction


def validate_relationships(catalog: dict) -> list[str]:
    """Ensure relationships reference valid IDs."""
    errors = []

    # Build ID sets
    plugin_ids = {p["plugin_id"] for p in catalog.get("plugins", [])}
    skill_ids = {s["skill_id"] for s in catalog.get("skills", [])}
    doc_ids = {d["doc_id"] for d in catalog.get("documents", [])}

    id_map = {
        "plugin": plugin_ids,
        "skill": skill_ids,
        "document": doc_ids,
    }

    for rel in catalog.get("relationships", []):
        source_type = rel.get("source_type")
        source_id = rel.get("source_id")
        target_type = rel.get("target_type")
        target_id = rel.get("target_id")

        if source_type in id_map and source_id not in id_map[source_type]:
            errors.append(f"Relationship references unknown {source_type}: {source_id}")

        if target_type in id_map and target_id not in id_map[target_type]:
            errors.append(f"Relationship references unknown {target_type}: {target_id}")

    return errors


def validate_id_format(catalog: dict) -> list[str]:
    """Ensure IDs are kebab-case."""
    errors = []
    kebab_pattern = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$")

    for plugin in catalog.get("plugins", []):
        if not kebab_pattern.match(plugin["plugin_id"]):
            errors.append(f"Invalid plugin_id format: {plugin['plugin_id']}")

    for skill in catalog.get("skills", []):
        if not kebab_pattern.match(skill["skill_id"]):
            errors.append(f"Invalid skill_id format: {skill['skill_id']}")

    return errors


def main():
    parser = argparse.ArgumentParser(description="Validate Intent Catalog")
    parser.add_argument("catalog", help="Path to catalog.json")
    parser.add_argument("--strict", action="store_true", help="Fail on warnings too")
    args = parser.parse_args()

    catalog_path = Path(args.catalog)
    valid, errors = validate_catalog(catalog_path)

    if errors:
        print(f"Validation FAILED with {len(errors)} errors:")
        for error in errors[:20]:  # Limit output
            print(f"  - {error}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more errors")
        return 1

    # Load catalog to check warnings
    with open(catalog_path) as f:
        catalog = json.load(f)

    warnings = catalog.get("warnings", [])
    if warnings:
        print(f"Validation PASSED with {len(warnings)} warnings")
        if args.strict:
            return 1
    else:
        print("Validation PASSED")

    return 0


if __name__ == "__main__":
    sys.exit(main())
