# Intent Catalog

Catalog control-plane for plugins, skills, and documents across Intent Solutions repositories.

## What It Does

Extracts a deterministic index of:
- **Plugins** - Claude Code extensions with commands, agents, MCPs
- **Skills** - Reusable AI prompts (SKILL.md files)
- **Documents** - PRDs, ARDs, architecture docs, use cases
- **Relationships** - Plugin↔Skill↔Document traceability

## Quick Start

```bash
# Install dependencies
pip install pyyaml jsonschema

# Extract from repos
make extract

# Validate output
make validate

# Full CI
make ci
```

## Output

```
dist/
├── catalog.json           # Main catalog (validated against schema)
└── catalog.warnings.json  # Files that couldn't be parsed
```

## Schema

- `schema/catalog.schema.json` - JSON Schema (v1.0.0)
- `schema/catalog.contract.md` - Human-readable spec

## Phase 1 Status

- [x] Data contract (JSON Schema + spec)
- [x] Deterministic extractor
- [x] Validator
- [x] CI workflow

## Phase 2 (Planned)

- Airtable sync
- Incremental updates
- Webhook triggers

## CLI Usage

```bash
# Extract from specific repos
python scripts/extract_catalog.py \
  --repo /path/to/ccpi \
  --repo /path/to/nixtla \
  --out dist/catalog.json

# Validate
python scripts/validate_catalog.py dist/catalog.json
```
