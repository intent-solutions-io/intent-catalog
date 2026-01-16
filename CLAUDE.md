# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Intent Catalog is a catalog control-plane that produces a deterministic `catalog.json` indexing plugins, skills, and documents across Intent Solutions repositories. The repo is the source of truth; Airtable syncs FROM this catalog.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt  # or: pip install pyyaml jsonschema

# Extract catalog from repos (outputs dist/catalog.json)
make extract

# Validate catalog against JSON Schema
make validate

# Full CI pipeline
make ci

# Extract from custom repos
python scripts/extract_catalog.py \
  --repo /path/to/repo1 \
  --repo /path/to/repo2 \
  --out dist/catalog.json

# Validate with strict mode (fail on warnings)
python scripts/validate_catalog.py dist/catalog.json --strict
```

Default repos scanned (configured in Makefile):
- `/home/jeremy/000-projects/claude-code-plugins`
- `/home/jeremy/000-projects/nixtla`

## Architecture

```
intent-catalog/
├── scripts/
│   ├── extract_catalog.py    # Walks repos, outputs catalog.json
│   └── validate_catalog.py   # Validates against JSON Schema + semantic rules
├── schema/
│   ├── catalog.schema.json   # JSON Schema v1.0.0 (Draft 2020-12)
│   └── catalog.contract.md   # Human-readable data contract
├── dist/                     # Output (gitignored)
│   ├── catalog.json          # Main catalog
│   └── catalog.warnings.json # Files that couldn't be parsed
└── Makefile                  # Build commands
```

**Data flow**: Repo files → `extract_catalog.py` → `catalog.json` → `validate_catalog.py` → (future) Airtable sync

## Entity Detection

| Entity | Detection Rule |
|--------|----------------|
| Plugin | `plugin.json` or `.claude-plugin/plugin.json` in directory |
| Skill | `SKILL.md` file with YAML frontmatter (starts with `---`) |
| Document | Files in `000-docs/` dirs OR matching `NNN-AA-CODE-*.md` pattern |

## ID Formats

All IDs must be kebab-case (`^[a-z0-9-]+$`):
- `plugin_id`: from manifest name or directory name
- `skill_id`: from frontmatter `name` field or parent directory
- `doc_id`: from filename (e.g., `001-OD-ARCH-design` → `001-od-arch-design`)

## Key Design Constraints

1. **Deterministic output**: Same input repos + commits = identical JSON output
2. **Sorted arrays**: All arrays sorted alphabetically by ID for stable diffs
3. **Best-effort parsing**: Missing fields produce warnings, not failures
4. **Relationship inference**: Plugin↔Skill `ships_with` relations auto-detected when skill is inside plugin directory

## Validation Rules

`validate_catalog.py` checks:
- JSON Schema compliance (Draft 2020-12)
- Relationship references point to valid source/target IDs
- IDs are kebab-case format
- No duplicate IDs within entity type (relaxed in multi-repo mode)

## Current Status

Phase 1 complete. Phase 2 planned: Airtable sync, incremental updates, webhook triggers.
