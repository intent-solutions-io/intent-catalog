#!/usr/bin/env python3
"""
Airtable Sync Script

Syncs catalog.json to Airtable, respecting protected fields.
Never deletes records - marks missing as inactive.

Usage:
    python sync_airtable.py [--dry-run] [--catalog PATH] [--base-id BASE_ID]

Environment:
    AIRTABLE_TOKEN: Personal access token
    AIRTABLE_BASE_ID: Base ID (can also use --base-id flag)
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    print("Error: requests not installed. Run: pip install requests")
    sys.exit(1)


CATALOG_PATH = Path(__file__).parent.parent / "dist" / "catalog.json"
MAPPINGS_PATH = Path(__file__).parent.parent / "mappings" / "airtable_ids.json"
SCHEMA_PATH = Path(__file__).parent.parent / "schema" / "airtable.base.json"
SUMMARY_PATH = Path(__file__).parent.parent / "dist" / "sync_summary.json"

AIRTABLE_API_BASE = "https://api.airtable.com/v0"

# Fields that should never be overwritten from repo
PROTECTED_FIELDS = {"owner_notes", "priority", "business_value"}

# Batch size for Airtable API
BATCH_SIZE = 10


@dataclass
class SyncStats:
    """Track sync statistics."""
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    marked_inactive: int = 0
    errors: list = field(default_factory=list)


class AirtableSync:
    def __init__(self, token: str, base_id: str, dry_run: bool = False):
        self.token = token
        self.base_id = base_id
        self.dry_run = dry_run
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self.mappings = {}
        self.schema = {}
        self.record_cache = {}  # table_name -> {primary_key: record}
        self.stats = {
            "plugins": SyncStats(),
            "skills": SyncStats(),
            "documents": SyncStats(),
            "plugin_skill_links": SyncStats(),
            "entity_doc_links": SyncStats(),
        }

    def _request(self, method: str, endpoint: str, data: dict | None = None) -> dict:
        """Make an API request with rate limit handling."""
        url = f"{AIRTABLE_API_BASE}{endpoint}"

        for attempt in range(5):
            if method == "GET":
                response = requests.get(url, headers=self.headers, params=data)
            elif method == "POST":
                response = requests.post(url, headers=self.headers, json=data)
            elif method == "PATCH":
                response = requests.patch(url, headers=self.headers, json=data)
            else:
                raise ValueError(f"Unsupported method: {method}")

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 30))
                print(f"    Rate limited, waiting {retry_after}s...")
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

        raise Exception("Max retries exceeded")

    def load_mappings(self) -> None:
        """Load table/field ID mappings."""
        if not MAPPINGS_PATH.exists():
            raise FileNotFoundError(f"Mappings not found: {MAPPINGS_PATH}. Run provisioner first.")

        with open(MAPPINGS_PATH) as f:
            self.mappings = json.load(f)

        if not SCHEMA_PATH.exists():
            raise FileNotFoundError(f"Schema not found: {SCHEMA_PATH}")

        with open(SCHEMA_PATH) as f:
            self.schema = json.load(f)

    def fetch_existing_records(self, table_name: str, primary_field: str) -> dict:
        """Fetch all existing records from a table, keyed by primary field."""
        table_id = self.mappings["tables"].get(table_name)
        if not table_id:
            raise ValueError(f"Table '{table_name}' not found in mappings")

        records = {}
        offset = None

        while True:
            params = {"pageSize": 100}
            if offset:
                params["offset"] = offset

            result = self._request("GET", f"/{self.base_id}/{table_id}", params)

            for record in result.get("records", []):
                key = record["fields"].get(primary_field)
                if key:
                    records[key] = record

            offset = result.get("offset")
            if not offset:
                break

        return records

    def get_protected_field_values(self, existing_record: dict | None) -> dict:
        """Extract protected field values from existing record."""
        if not existing_record:
            return {}

        protected = {}
        for field_name in PROTECTED_FIELDS:
            if field_name in existing_record.get("fields", {}):
                protected[field_name] = existing_record["fields"][field_name]

        return protected

    def prepare_record_fields(self, entity: dict, table_name: str, existing: dict | None) -> dict:
        """Prepare fields for Airtable, preserving protected fields."""
        table_schema = self.schema["tables"].get(table_name, {})
        field_specs = table_schema.get("fields", {})

        fields = {}

        for field_name, spec in field_specs.items():
            source = spec.get("source", "repo")

            # Skip protected fields - preserve existing values
            if source == "airtable":
                if existing and field_name in existing.get("fields", {}):
                    fields[field_name] = existing["fields"][field_name]
                continue

            # Skip sync-managed fields
            if source == "sync":
                continue

            # Skip computed fields for now
            if source == "computed":
                continue

            # Map entity field to Airtable field
            entity_key = field_name
            if entity_key in entity:
                value = entity[entity_key]

                # Handle arrays - convert to comma-separated string for text fields
                if isinstance(value, list):
                    if spec["type"] in ("multilineText", "singleLineText"):
                        value = ", ".join(str(v) for v in value)

                # Handle booleans
                if spec["type"] == "checkbox":
                    value = bool(value)

                fields[field_name] = value

        # Add last_synced timestamp
        fields["last_synced"] = datetime.now(timezone.utc).isoformat()

        return fields

    def upsert_batch(self, table_name: str, records: list[dict]) -> list[dict]:
        """Upsert a batch of records."""
        table_id = self.mappings["tables"].get(table_name)
        if not table_id:
            raise ValueError(f"Table '{table_name}' not found in mappings")

        # Airtable upsert endpoint
        data = {
            "records": records,
            "typecast": True,  # Auto-convert types
        }

        if self.dry_run:
            return records

        result = self._request("PATCH", f"/{self.base_id}/{table_id}", data)
        return result.get("records", [])

    def sync_entities(
        self,
        entities: list[dict],
        table_name: str,
        primary_field: str,
        id_field: str,
        stats_key: str,
    ) -> dict:
        """Sync a list of entities to a table. Returns ID mapping."""
        print(f"  Syncing {len(entities)} {table_name}...")

        # Fetch existing records
        existing = self.fetch_existing_records(table_name, primary_field)
        print(f"    Found {len(existing)} existing records")

        # Track which IDs we've seen
        seen_ids = set()
        id_mapping = {}  # entity_id -> airtable_record_id

        # Prepare batches
        batch = []
        for entity in entities:
            entity_id = entity.get(id_field)
            if not entity_id:
                continue

            seen_ids.add(entity_id)
            existing_record = existing.get(entity_id)

            fields = self.prepare_record_fields(entity, table_name, existing_record)

            record = {"fields": fields}
            if existing_record:
                record["id"] = existing_record["id"]

            batch.append(record)

            if len(batch) >= BATCH_SIZE:
                if self.dry_run:
                    print(f"    [DRY RUN] Would upsert {len(batch)} records")
                else:
                    results = self.upsert_batch(table_name, batch)
                    for r in results:
                        pid = r["fields"].get(primary_field)
                        if pid:
                            id_mapping[pid] = r["id"]
                batch = []

        # Process remaining batch
        if batch:
            if self.dry_run:
                print(f"    [DRY RUN] Would upsert {len(batch)} records")
            else:
                results = self.upsert_batch(table_name, batch)
                for r in results:
                    pid = r["fields"].get(primary_field)
                    if pid:
                        id_mapping[pid] = r["id"]

        # Mark missing records as inactive
        missing = set(existing.keys()) - seen_ids
        if missing:
            print(f"    Marking {len(missing)} records as inactive")
            self.mark_inactive(table_name, [existing[k] for k in missing], stats_key)

        # Update stats
        stats = self.stats[stats_key]
        for entity_id in seen_ids:
            if entity_id in existing:
                stats.updated += 1
            else:
                stats.created += 1

        # Build ID mapping from existing records too
        for key, record in existing.items():
            if key not in id_mapping:
                id_mapping[key] = record["id"]

        return id_mapping

    def mark_inactive(self, table_name: str, records: list[dict], stats_key: str) -> None:
        """Mark records as inactive (soft delete)."""
        if not records:
            return

        table_id = self.mappings["tables"].get(table_name)
        if not table_id:
            return

        batch = []
        for record in records:
            # Only mark inactive if status field exists and isn't already inactive
            if "status" in record.get("fields", {}):
                if record["fields"]["status"] == "inactive":
                    continue

            batch.append({
                "id": record["id"],
                "fields": {"status": "inactive"},
            })

            if len(batch) >= BATCH_SIZE:
                if not self.dry_run:
                    self.upsert_batch(table_name, batch)
                self.stats[stats_key].marked_inactive += len(batch)
                batch = []

        if batch:
            if not self.dry_run:
                self.upsert_batch(table_name, batch)
            self.stats[stats_key].marked_inactive += len(batch)

    def sync_plugin_skill_links(
        self,
        relationships: list[dict],
        plugin_ids: dict,
        skill_ids: dict,
    ) -> None:
        """Sync plugin-skill relationships."""
        print("  Syncing PluginSkillLinks...")

        # Filter to plugin->skill relationships only
        links = [
            r for r in relationships
            if r.get("source_type") == "plugin" and r.get("target_type") == "skill"
        ]

        print(f"    Found {len(links)} plugin-skill relationships")

        existing = self.fetch_existing_records("PluginSkillLinks", "link_id")
        seen_ids = set()

        batch = []
        for rel in links:
            plugin_id = rel.get("source_id")
            skill_id = rel.get("target_id")
            relation_type = rel.get("relation_type")

            # Build composite key
            link_id = f"{plugin_id}::{skill_id}::{relation_type}"
            seen_ids.add(link_id)

            # Get Airtable record IDs
            plugin_record_id = plugin_ids.get(plugin_id)
            skill_record_id = skill_ids.get(skill_id)

            fields = {
                "link_id": link_id,
                "relation_type": relation_type,
                "confidence": rel.get("confidence", "inferred"),
                "last_synced": datetime.now(timezone.utc).isoformat(),
            }

            # Add linked records if we have the IDs
            if plugin_record_id:
                fields["plugin"] = [plugin_record_id]
            if skill_record_id:
                fields["skill"] = [skill_record_id]

            existing_record = existing.get(link_id)
            record = {"fields": fields}
            if existing_record:
                record["id"] = existing_record["id"]

            batch.append(record)

            if len(batch) >= BATCH_SIZE:
                if self.dry_run:
                    print(f"    [DRY RUN] Would upsert {len(batch)} links")
                else:
                    self.upsert_batch("PluginSkillLinks", batch)
                batch = []

        if batch:
            if self.dry_run:
                print(f"    [DRY RUN] Would upsert {len(batch)} links")
            else:
                self.upsert_batch("PluginSkillLinks", batch)

        # Update stats
        stats = self.stats["plugin_skill_links"]
        for link_id in seen_ids:
            if link_id in existing:
                stats.updated += 1
            else:
                stats.created += 1

    def sync_entity_doc_links(
        self,
        relationships: list[dict],
        plugin_ids: dict,
        skill_ids: dict,
        doc_ids: dict,
    ) -> None:
        """Sync entity-document relationships."""
        print("  Syncing EntityDocLinks...")

        # Filter to entity->document relationships
        links = [
            r for r in relationships
            if r.get("target_type") == "document"
        ]

        print(f"    Found {len(links)} entity-document relationships")

        existing = self.fetch_existing_records("EntityDocLinks", "link_id")
        seen_ids = set()

        batch = []
        for rel in links:
            entity_type = rel.get("source_type")
            entity_id = rel.get("source_id")
            doc_id = rel.get("target_id")
            relation_type = rel.get("relation_type")

            # Build composite key
            link_id = f"{entity_type}::{entity_id}::{doc_id}::{relation_type}"
            seen_ids.add(link_id)

            # Get document Airtable record ID
            doc_record_id = doc_ids.get(doc_id)

            fields = {
                "link_id": link_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "relation_type": relation_type,
                "confidence": rel.get("confidence", "inferred"),
                "last_synced": datetime.now(timezone.utc).isoformat(),
            }

            if doc_record_id:
                fields["document"] = [doc_record_id]

            existing_record = existing.get(link_id)
            record = {"fields": fields}
            if existing_record:
                record["id"] = existing_record["id"]

            batch.append(record)

            if len(batch) >= BATCH_SIZE:
                if self.dry_run:
                    print(f"    [DRY RUN] Would upsert {len(batch)} links")
                else:
                    self.upsert_batch("EntityDocLinks", batch)
                batch = []

        if batch:
            if self.dry_run:
                print(f"    [DRY RUN] Would upsert {len(batch)} links")
            else:
                self.upsert_batch("EntityDocLinks", batch)

        # Update stats
        stats = self.stats["entity_doc_links"]
        for link_id in seen_ids:
            if link_id in existing:
                stats.updated += 1
            else:
                stats.created += 1

    def generate_summary(self) -> dict:
        """Generate sync summary."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dry_run": self.dry_run,
            "stats": {
                name: {
                    "created": s.created,
                    "updated": s.updated,
                    "unchanged": s.unchanged,
                    "marked_inactive": s.marked_inactive,
                    "errors": s.errors,
                }
                for name, s in self.stats.items()
            },
            "totals": {
                "created": sum(s.created for s in self.stats.values()),
                "updated": sum(s.updated for s in self.stats.values()),
                "unchanged": sum(s.unchanged for s in self.stats.values()),
                "marked_inactive": sum(s.marked_inactive for s in self.stats.values()),
                "errors": sum(len(s.errors) for s in self.stats.values()),
            },
        }

    def sync(self, catalog: dict) -> dict:
        """Main sync entry point."""
        print("Loading mappings...")
        self.load_mappings()

        # Sync main entity tables
        print("\nSyncing Plugins...")
        plugin_ids = self.sync_entities(
            catalog.get("plugins", []),
            "Plugins",
            "plugin_id",
            "plugin_id",
            "plugins",
        )

        print("\nSyncing Skills...")
        skill_ids = self.sync_entities(
            catalog.get("skills", []),
            "Skills",
            "skill_id",
            "skill_id",
            "skills",
        )

        print("\nSyncing Documents...")
        doc_ids = self.sync_entities(
            catalog.get("documents", []),
            "Documents",
            "doc_id",
            "doc_id",
            "documents",
        )

        # Sync relationship tables
        print("\nSyncing relationships...")
        relationships = catalog.get("relationships", [])

        self.sync_plugin_skill_links(relationships, plugin_ids, skill_ids)
        self.sync_entity_doc_links(relationships, plugin_ids, skill_ids, doc_ids)

        return self.generate_summary()


def main():
    parser = argparse.ArgumentParser(description="Sync catalog to Airtable")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=CATALOG_PATH,
        help=f"Path to catalog.json (default: {CATALOG_PATH})",
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

    # Load catalog
    if not args.catalog.exists():
        print(f"Error: Catalog not found: {args.catalog}")
        print("Run 'make extract' first to generate catalog.json")
        return 1

    with open(args.catalog) as f:
        catalog = json.load(f)

    print(f"Syncing to Airtable base: {base_id}")
    print(f"Catalog version: {catalog.get('meta', {}).get('version', 'unknown')}")
    print(f"Entities: {len(catalog.get('plugins', []))} plugins, "
          f"{len(catalog.get('skills', []))} skills, "
          f"{len(catalog.get('documents', []))} documents")
    if args.dry_run:
        print("DRY RUN MODE - no changes will be made")
    print()

    # Sync
    syncer = AirtableSync(token, base_id, dry_run=args.dry_run)

    try:
        summary = syncer.sync(catalog)
    except Exception as e:
        print(f"\nError during sync: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Save summary
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SUMMARY_PATH, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary saved to {SUMMARY_PATH}")

    # Print summary
    print("\n" + "=" * 50)
    print("SYNC SUMMARY")
    print("=" * 50)
    totals = summary["totals"]
    print(f"Created:         {totals['created']}")
    print(f"Updated:         {totals['updated']}")
    print(f"Unchanged:       {totals['unchanged']}")
    print(f"Marked inactive: {totals['marked_inactive']}")
    print(f"Errors:          {totals['errors']}")

    if totals["errors"] > 0:
        print("\nErrors encountered - check sync_summary.json for details")
        return 1

    print("\nSync complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
