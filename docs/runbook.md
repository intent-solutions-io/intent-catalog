# Intent Catalog Operational Runbook

## Overview

The Intent Catalog is a unified index of plugins, skills, and documents across Intent Solutions repositories. It extracts metadata from repos, validates against a schema, and syncs to Airtable for business visibility.

**Architecture:**
```
Repos (CCPI, Nixtla) → extract_catalog.py → catalog.json → sync_airtable.py → Airtable
```

## Quick Reference

| Task | Command |
|------|---------|
| Extract catalog | `make extract` |
| Validate schema | `make validate` |
| Full CI pipeline | `make ci` |
| Dry-run sync | `python scripts/sync_airtable.py --dry-run` |
| Live sync | `python scripts/sync_airtable.py` |
| Provision schema | `python scripts/airtable_provision.py` |
| Quality report | `python scripts/quality_score.py` |
| Lint documents | `python scripts/doc_lint.py --check docs/` |

## Local Setup

### Prerequisites

- Python 3.10+
- pip

### Install Dependencies

```bash
pip install -r requirements.txt
# or manually:
pip install pyyaml jsonschema requests
```

### Environment Variables

```bash
# Required for Airtable operations
export AIRTABLE_TOKEN="pat..."        # Personal access token
export AIRTABLE_BASE_ID="app..."      # Base ID
```

### Verify Installation

```bash
python scripts/extract_catalog.py --help
python scripts/validate_catalog.py --help
python scripts/sync_airtable.py --help
```

## Extraction Operations

### Extract Catalog

```bash
# Using Makefile (default repos from config)
make extract

# Explicit repos
python scripts/extract_catalog.py \
  --repo /home/jeremy/000-projects/claude-code-plugins \
  --repo /home/jeremy/000-projects/nixtla \
  --out dist/catalog.json

# Using config file
python scripts/extract_catalog.py \
  --config config/catalog.sources.json \
  --out dist/catalog.json
```

### Validate Catalog

```bash
make validate
# or
python scripts/validate_catalog.py dist/catalog.json
```

### Check for ID Collisions

```bash
python scripts/extract_catalog.py \
  --config config/catalog.sources.json \
  --check-collisions
```

## Airtable Sync Operations

### Initial Setup (First Time)

1. Create Airtable base manually
2. Get base ID from URL: `https://airtable.com/BASE_ID/...`
3. Create personal access token with scopes: `data.records:read`, `data.records:write`, `schema.bases:read`, `schema.bases:write`
4. Provision schema:
   ```bash
   export AIRTABLE_TOKEN="..."
   export AIRTABLE_BASE_ID="..."
   python scripts/airtable_provision.py
   ```
5. Verify mappings created: `cat mappings/airtable_ids.json`

### Daily Sync (Automated)

Scheduled via GitHub Actions at 6 AM UTC daily. Monitor:
- Actions tab: `Sync to Airtable` workflow
- Artifacts: `evidence-bundle-*` for audit trail
- Issues: Check for `sync-failure` labeled issues

### Manual Sync

```bash
# Dry run first
python scripts/sync_airtable.py --dry-run

# Live sync
python scripts/sync_airtable.py

# Incremental sync (only changed entities)
python scripts/sync_airtable.py --incremental
```

### Review Evidence Bundle

After sync, evidence is saved to `dist/evidence/<run_id>/`:

```bash
# List recent evidence bundles
ls -la dist/evidence/

# Review latest
RUN_ID=$(ls dist/evidence/ | tail -1)
cat dist/evidence/$RUN_ID/manifest.json  # Summary
cat dist/evidence/$RUN_ID/evidence.json  # Event log
```

## Quality Scoring

### Generate Quality Report

```bash
python scripts/quality_score.py
```

**Output:**
- `dist/quality_report.json` - Machine-readable scores
- `dist/quality_report.md` - Human-readable dashboard

### Interpret Scores

| Score Range | Status | Action |
|-------------|--------|--------|
| 76-100% | Good | Maintain |
| 51-75% | Fair | Add missing docs |
| 26-50% | Poor | Prioritize documentation |
| 0-25% | Critical | Immediate attention |

### Improve Scores

Scores are based on documentation coverage:
- PRD/Spec (20 points)
- ADR/Decision (15 points)
- Runbook (20 points)
- Use Case (15 points)
- Guide/Tutorial (10 points)
- AAR/Report (10 points)
- Evidence (5 points)
- Reference (5 points)

Plus 15 points for basic metadata (description + version).

## Document Linting

### Check Documents

```bash
# Check mode (for CI)
python scripts/doc_lint.py --check docs/

# Show diffs
python scripts/doc_lint.py --diff docs/
```

### Auto-Fix Missing Metadata

```bash
python scripts/doc_lint.py --fix docs/
```

This adds YAML frontmatter with:
- `doc_id` - inferred from filename
- `doc_type` - inferred from content
- `title` - extracted from H1 or filename

## Troubleshooting

### Sync Failures

**Error: "AIRTABLE_TOKEN not set"**
```bash
export AIRTABLE_TOKEN="pat..."
```

**Error: "Mappings not found"**
```bash
# Run provisioner first
python scripts/airtable_provision.py
```

**Error: "Rate limited" (429)**
The sync automatically retries with exponential backoff. If persistent:
1. Check Airtable rate limits (5 req/sec)
2. Wait and retry
3. Consider running during off-peak hours

**Error: "API error 422"**
Usually invalid field values. Check:
1. Select options match schema: `cat schema/airtable.base.json`
2. Required fields are present

### Extraction Issues

**Warning: "Could not parse frontmatter"**
SKILL.md files need YAML frontmatter:
```yaml
---
name: My Skill
description: What it does
---
```

**Warning: "Invalid doc_type"**
Document must have recognized type. Valid types:
- spec, decision, report, use_case, evidence
- runbook, security, marketing, architecture
- planning, audit, guide, reference

### Schema Issues

**Error: "Validation failed"**
```bash
# Check specific errors
python scripts/validate_catalog.py dist/catalog.json 2>&1 | head -50

# Common fixes:
# - Add missing required fields
# - Fix enum values
# - Remove invalid characters from IDs
```

## CI/CD Workflows

### Trigger Descriptions

| Trigger | Behavior |
|---------|----------|
| PR | Dry-run only, posts comment with diff |
| Push to main | Live sync |
| Schedule (6 AM UTC) | Live incremental sync |
| Manual dispatch | Configurable dry-run/incremental |

### Manual Workflow Trigger

```bash
gh workflow run sync.yml -f dry_run=false -f incremental=true
```

### Monitor Workflow

```bash
# List recent runs
gh run list --workflow=sync.yml

# View specific run
gh run view <run-id>

# Download artifacts
gh run download <run-id> -n evidence-bundle-<run-id>
```

## Schema Changes

### Adding a New Field

1. Update `schema/airtable.base.json`:
   ```json
   "new_field": {
     "type": "singleLineText",
     "description": "What this field is for",
     "source": "repo"
   }
   ```

2. Update `schema/catalog.schema.json` if needed

3. Re-provision:
   ```bash
   python scripts/airtable_provision.py
   ```

4. Update extractor if `source: repo`

### Adding a New Table

1. Add to `schema/airtable.base.json` tables object
2. Add sync logic to `sync_airtable.py`
3. Re-provision

## Emergency Procedures

### Rollback Sync

Airtable doesn't support true rollback. Options:
1. Restore from backup (Airtable Pro feature)
2. Re-sync from known good catalog
3. Manual corrections

### Disable Scheduled Sync

```bash
# Edit workflow file to comment out schedule
# Or disable via GitHub UI: Actions → Workflow → Disable
```

### Clear and Re-sync

```bash
# Remove previous catalog cache
rm -f dist/catalog.prev.json

# Full sync (not incremental)
python scripts/sync_airtable.py
```

## Output Files Reference

| File | Description | Retention |
|------|-------------|-----------|
| `dist/catalog.json` | Main catalog | Current |
| `dist/catalog.prev.json` | Previous for diff | 1 version |
| `dist/catalog.warnings.json` | Parse warnings | Current |
| `dist/sync_summary.json` | Last sync stats | Current |
| `dist/quality_report.json` | Quality scores | Current |
| `dist/quality_report.md` | Readable report | Current |
| `dist/evidence/<run_id>/` | Audit bundles | 90 days |
| `mappings/airtable_ids.json` | Table/field IDs | Persistent |

## Contacts

- **Repo Owner:** Jeremy
- **Airtable Base:** Intent Catalog
- **GitHub Actions:** `.github/workflows/sync.yml`
