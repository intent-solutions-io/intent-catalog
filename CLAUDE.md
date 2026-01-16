# CLAUDE.md - Intent Catalog

## Project Overview

**Intent Catalog** is a catalog control-plane that indexes plugins, skills, and documents across Intent Solutions repositories. It produces a deterministic `catalog.json` that serves as the source of truth before syncing to Airtable.

## Current Status: Phase 1 Complete

Phase 1 deliverables:
- [x] Data contract: `schema/catalog.schema.json` + `schema/catalog.contract.md`
- [x] Extractor: `scripts/extract_catalog.py`
- [x] Validator: `scripts/validate_catalog.py`
- [x] CI: `.github/workflows/ci.yml`
- [x] Docs: `README.md`, `docs/runbook.md`

## Key Files

| File | Purpose |
|------|---------|
| `schema/catalog.schema.json` | JSON Schema v1.0.0 |
| `schema/catalog.contract.md` | Human-readable data contract |
| `scripts/extract_catalog.py` | Deterministic extractor |
| `scripts/validate_catalog.py` | Schema validator |
| `Makefile` | Build commands |
| `dist/catalog.json` | Output (gitignored) |

## Quick Commands

```bash
make extract   # Extract catalog from repos
make validate  # Validate against schema
make ci        # Full pipeline
```

## Repos Scanned

Default paths in Makefile:
- `/home/jeremy/000-projects/claude-code-plugins` (CCPI)
- `/home/jeremy/000-projects/nixtla`

## Entity Types

1. **Plugins** - detected by `plugin.json` or `.claude-plugin/plugin.json`
2. **Skills** - detected by `SKILL.md` with YAML frontmatter
3. **Documents** - detected by `000-docs/` directories or `NNN-AA-CODE-*.md` pattern

## Relationships

Plugin↔Skill relations: `ships_with`, `depends_on`, `invokes`, `recommends`, `embeds`
Entity↔Document relations: `spec`, `decision`, `report`, `use_case`, `evidence`, `runbook`, `security`, `marketing`

## Phase 2 (Next)

- Airtable sync from catalog.json
- Incremental updates
- Webhook triggers on repo changes

## Development Notes

- Extractor is idempotent: same input → same output
- All arrays sorted alphabetically for determinism
- Warnings don't fail extraction, only validation strictness

## Handoff Context

This repo was created 2026-01-15 as part of the Airtable data architecture project. The goal is to have a proper data contract before syncing to Airtable, ensuring the repo is the source of truth.

Related work:
- Airtable schema design: `/home/jeremy/.claude/plans/rippling-marinating-sloth.md`
- Airtable skill scripts: `/home/jeremy/.claude/skills/airtable/scripts/`
