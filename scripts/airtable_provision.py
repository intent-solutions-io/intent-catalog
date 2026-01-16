#!/usr/bin/env python3
"""
Airtable Schema Provisioner

Creates/updates Airtable tables and fields based on airtable.base.json.
Outputs mappings/airtable_ids.json with table and field IDs.

Usage:
    python airtable_provision.py [--dry-run] [--base-id BASE_ID]

Environment:
    AIRTABLE_TOKEN: Personal access token with schema:write scope
    AIRTABLE_BASE_ID: Base ID (can also use --base-id flag)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    print("Error: requests not installed. Run: pip install requests")
    sys.exit(1)


SCHEMA_PATH = Path(__file__).parent.parent / "schema" / "airtable.base.json"
MAPPINGS_PATH = Path(__file__).parent.parent / "mappings" / "airtable_ids.json"

AIRTABLE_API_BASE = "https://api.airtable.com/v0"

# Map our schema types to Airtable field types
FIELD_TYPE_MAP = {
    "singleLineText": "singleLineText",
    "multilineText": "multilineText",
    "singleSelect": "singleSelect",
    "multipleRecordLinks": "multipleRecordLinks",
    "checkbox": "checkbox",
    "number": "number",
    "dateTime": "dateTime",
    "url": "url",
}


class AirtableProvisioner:
    def __init__(self, token: str, base_id: str, dry_run: bool = False):
        self.token = token
        self.base_id = base_id
        self.dry_run = dry_run
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self.mappings = {"tables": {}, "fields": {}}
        self.existing_tables = {}

    def _request(self, method: str, endpoint: str, data: dict | None = None) -> dict:
        """Make an API request with rate limit handling."""
        url = f"{AIRTABLE_API_BASE}{endpoint}"

        for attempt in range(3):
            if method == "GET":
                response = requests.get(url, headers=self.headers)
            elif method == "POST":
                response = requests.post(url, headers=self.headers, json=data)
            elif method == "PATCH":
                response = requests.patch(url, headers=self.headers, json=data)
            else:
                raise ValueError(f"Unsupported method: {method}")

            if response.status_code == 429:
                # Rate limited - wait and retry
                retry_after = int(response.headers.get("Retry-After", 30))
                print(f"  Rate limited, waiting {retry_after}s...")
                time.sleep(retry_after)
                continue

            if response.status_code >= 400:
                error_msg = response.text
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        error_msg = error_data["error"].get("message", error_msg)
                except Exception:
                    pass
                raise Exception(f"API error {response.status_code}: {error_msg}")

            return response.json()

        raise Exception("Max retries exceeded due to rate limiting")

    def get_existing_tables(self) -> dict:
        """Fetch existing tables in the base."""
        result = self._request("GET", f"/meta/bases/{self.base_id}/tables")
        tables = {}
        for table in result.get("tables", []):
            tables[table["name"]] = {
                "id": table["id"],
                "fields": {f["name"]: f for f in table.get("fields", [])},
                "primaryFieldId": table.get("primaryFieldId"),
            }
        return tables

    def create_table(self, name: str, spec: dict) -> str:
        """Create a new table."""
        # Prepare fields for creation
        fields = []
        for field_name, field_spec in spec["fields"].items():
            field_def = self._build_field_definition(field_name, field_spec)
            fields.append(field_def)

        data = {
            "name": name,
            "fields": fields,
        }

        if self.dry_run:
            print(f"  [DRY RUN] Would create table '{name}' with {len(fields)} fields")
            return f"dry-run-{name}"

        print(f"  Creating table '{name}'...")
        result = self._request("POST", f"/meta/bases/{self.base_id}/tables", data)
        return result["id"]

    def update_table_fields(self, table_id: str, table_name: str, spec: dict, existing: dict) -> None:
        """Update fields in an existing table."""
        existing_fields = existing.get("fields", {})

        for field_name, field_spec in spec["fields"].items():
            if field_name in existing_fields:
                # Field exists - check if update needed
                existing_field = existing_fields[field_name]
                if self._needs_update(existing_field, field_spec):
                    self._update_field(table_id, table_name, existing_field["id"], field_name, field_spec)
                else:
                    print(f"    Field '{field_name}' unchanged")
            else:
                # Create new field
                self._create_field(table_id, table_name, field_name, field_spec)

    def _build_field_definition(self, name: str, spec: dict) -> dict:
        """Build Airtable field definition from our spec."""
        airtable_type = FIELD_TYPE_MAP.get(spec["type"], spec["type"])

        field_def = {
            "name": name,
            "type": airtable_type,
        }

        # Add description if present
        if "description" in spec:
            field_def["description"] = spec["description"]

        # Handle select options
        if spec["type"] == "singleSelect" and "options" in spec:
            field_def["options"] = {
                "choices": [{"name": opt} for opt in spec["options"]]
            }

        # Handle checkbox (requires icon and color)
        if spec["type"] == "checkbox":
            field_def["options"] = {
                "icon": "check",
                "color": "greenBright"
            }

        # Handle number (requires precision)
        if spec["type"] == "number":
            field_def["options"] = {
                "precision": spec.get("precision", 0)
            }

        # Handle dateTime (requires date/time format)
        if spec["type"] == "dateTime":
            field_def["options"] = {
                "dateFormat": {"name": "iso"},
                "timeFormat": {"name": "24hour"},
                "timeZone": "utc"
            }

        # Handle linked records
        if spec["type"] == "multipleRecordLinks" and "linkedTable" in spec:
            linked_table_id = self.mappings["tables"].get(spec["linkedTable"])
            if linked_table_id:
                field_def["options"] = {
                    "linkedTableId": linked_table_id
                }

        return field_def

    def _needs_update(self, existing: dict, spec: dict) -> bool:
        """Check if field needs update."""
        # For now, just check if select options differ
        if spec["type"] == "singleSelect" and "options" in spec:
            existing_choices = set()
            if "options" in existing and "choices" in existing["options"]:
                existing_choices = {c["name"] for c in existing["options"]["choices"]}
            spec_choices = set(spec["options"])
            return existing_choices != spec_choices
        return False

    def _create_field(self, table_id: str, table_name: str, field_name: str, spec: dict) -> None:
        """Create a new field in a table."""
        field_def = self._build_field_definition(field_name, spec)

        if self.dry_run:
            print(f"    [DRY RUN] Would create field '{field_name}'")
            return

        print(f"    Creating field '{field_name}'...")
        data = {"fields": [field_def]}
        self._request("PATCH", f"/meta/bases/{self.base_id}/tables/{table_id}", data)

    def _update_field(self, table_id: str, table_name: str, field_id: str, field_name: str, spec: dict) -> None:
        """Update an existing field."""
        if self.dry_run:
            print(f"    [DRY RUN] Would update field '{field_name}'")
            return

        print(f"    Updating field '{field_name}'...")

        # Build update payload
        update = {"name": field_name}

        if spec["type"] == "singleSelect" and "options" in spec:
            update["options"] = {
                "choices": [{"name": opt} for opt in spec["options"]]
            }

        data = {"fields": [{"id": field_id, **update}]}
        self._request("PATCH", f"/meta/bases/{self.base_id}/tables/{table_id}", data)

    def provision(self, schema: dict) -> dict:
        """Provision all tables and fields."""
        print("Fetching existing tables...")
        self.existing_tables = self.get_existing_tables()
        print(f"Found {len(self.existing_tables)} existing tables")

        # First pass: create tables that don't exist
        for table_name, table_spec in schema["tables"].items():
            if table_name in self.existing_tables:
                self.mappings["tables"][table_name] = self.existing_tables[table_name]["id"]
                print(f"Table '{table_name}' exists (id: {self.existing_tables[table_name]['id']})")
            else:
                table_id = self.create_table(table_name, table_spec)
                self.mappings["tables"][table_name] = table_id
                # Refresh existing tables after creation
                if not self.dry_run:
                    time.sleep(0.5)  # Brief pause for API
                    self.existing_tables = self.get_existing_tables()

        # Second pass: update fields in existing tables
        print("\nUpdating fields...")
        for table_name, table_spec in schema["tables"].items():
            print(f"Processing table '{table_name}'...")
            table_id = self.mappings["tables"][table_name]
            existing = self.existing_tables.get(table_name, {})

            if not self.dry_run or table_name in self.existing_tables:
                self.update_table_fields(table_id, table_name, table_spec, existing)

            # Store field IDs
            if table_name in self.existing_tables:
                self.mappings["fields"][table_name] = {
                    f["name"]: f["id"]
                    for f in self.existing_tables[table_name].get("fields", {}).values()
                }

        # Refresh mappings after all updates
        if not self.dry_run:
            print("\nRefreshing field mappings...")
            self.existing_tables = self.get_existing_tables()
            for table_name in schema["tables"]:
                if table_name in self.existing_tables:
                    self.mappings["fields"][table_name] = {
                        f["name"]: f["id"]
                        for f in self.existing_tables[table_name].get("fields", {}).values()
                    }

        return self.mappings


def main():
    parser = argparse.ArgumentParser(description="Provision Airtable schema")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--base-id",
        help="Airtable base ID (overrides AIRTABLE_BASE_ID env var)",
    )
    args = parser.parse_args()

    # Get credentials
    token = os.environ.get("AIRTABLE_TOKEN")
    if not token:
        print("Error: AIRTABLE_TOKEN environment variable not set")
        return 1

    base_id = args.base_id or os.environ.get("AIRTABLE_BASE_ID")
    if not base_id:
        print("Error: AIRTABLE_BASE_ID not set (use --base-id or env var)")
        return 1

    # Load schema
    if not SCHEMA_PATH.exists():
        print(f"Error: Schema not found: {SCHEMA_PATH}")
        return 1

    with open(SCHEMA_PATH) as f:
        schema = json.load(f)

    print(f"Provisioning Airtable base: {base_id}")
    print(f"Schema version: {schema.get('version', 'unknown')}")
    print(f"Tables to provision: {', '.join(schema['tables'].keys())}")
    if args.dry_run:
        print("DRY RUN MODE - no changes will be made\n")
    print()

    # Provision
    provisioner = AirtableProvisioner(token, base_id, dry_run=args.dry_run)

    try:
        mappings = provisioner.provision(schema)
    except Exception as e:
        print(f"\nError during provisioning: {e}")
        return 1

    # Save mappings
    if not args.dry_run:
        MAPPINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(MAPPINGS_PATH, "w") as f:
            json.dump(mappings, f, indent=2, sort_keys=True)
        print(f"\nMappings saved to {MAPPINGS_PATH}")
    else:
        print(f"\n[DRY RUN] Would save mappings to {MAPPINGS_PATH}")
        print(json.dumps(mappings, indent=2, sort_keys=True))

    print("\nProvisioning complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
