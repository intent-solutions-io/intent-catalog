# Intent Catalog Data Contract v1.0.0

## Overview

This document defines the data contract for the Intent Catalog - a deterministic index of plugins, skills, and documents across Intent Solutions repositories.

## Design Principles

1. **Repo is source of truth** - Airtable syncs FROM this catalog, not vice versa
2. **Deterministic** - Same input always produces same output (stable ordering)
3. **Idempotent** - Running extract multiple times produces identical results
4. **Best-effort parsing** - Missing fields produce warnings, not failures

## Entity Types

### Plugin

A plugin is a complete Claude Code extension containing skills, commands, agents, and/or MCP servers.

**Detection**: Directory contains `.claude-plugin/plugin.json` OR `plugin.json`

**ID Format**: `plugin_id` = kebab-case name from manifest or directory name
- Example: `nixtla-baseline-lab`, `supabase-skill-pack`

**Required Fields**:
| Field | Type | Source |
|-------|------|--------|
| `plugin_id` | string | manifest.name or dirname |
| `name` | string | manifest.displayName or manifest.name |
| `path` | string | relative path from repo root |
| `source_repo` | string | repo name |

**Optional Fields**:
| Field | Type | Source |
|-------|------|--------|
| `description` | string | manifest.description |
| `version` | string | manifest.version |
| `status` | enum | inferred from path or manifest |
| `has_mcp` | boolean | existence of .mcp.json |
| `commands` | string[] | files in commands/ |
| `agents` | string[] | files in agents/ |

### Skill

A skill is a reusable AI prompt defined in a SKILL.md file with YAML frontmatter.

**Detection**: File named `SKILL.md` with YAML frontmatter (starts with `---`)

**ID Format**: `skill_id` = name from frontmatter or parent directory
- Example: `nixtla-anomaly-detector`, `supabase-auth-setup`

**Required Fields**:
| Field | Type | Source |
|-------|------|--------|
| `skill_id` | string | frontmatter.name or dirname |
| `name` | string | frontmatter.name |
| `path` | string | relative path to SKILL.md |
| `source_repo` | string | repo name |

**Optional Fields**:
| Field | Type | Source |
|-------|------|--------|
| `description` | string | frontmatter.description |
| `version` | string | frontmatter.version |
| `allowed_tools` | string | frontmatter.allowed-tools |
| `author` | string | frontmatter.author |
| `license` | string | frontmatter.license |
| `trigger_phrases` | string[] | parsed from description |
| `is_standalone` | boolean | not inside a plugin directory |
| `has_references` | boolean | references/ dir exists |
| `has_assets` | boolean | assets/ dir exists |
| `has_scripts` | boolean | scripts/ dir exists |

### Document

A document is a markdown file in a `000-docs/` directory or matching the naming pattern `NNN-AA-CODE-*.md`.

**Detection**:
1. File in `000-docs/` directory
2. Filename matches `NNN-AA-CODE-*.md` pattern

**ID Format**: `doc_id` = filename without extension or generated from path
- Example: `001-OD-ARCH-baseline-design`, `nixtla-baseline-lab/000-docs/readme`

**Category Codes**:
| Code | Full Name | doc_type |
|------|-----------|----------|
| `OD-ARCH` | Architecture | architecture |
| `PP-PLAN` | Planning | planning |
| `PP-PRD` | Product Requirements | spec |
| `PP-ARD` | Architecture Requirements | decision |
| `AA-AACR` | After-Action Review | report |
| `AA-AUDT` | Audit | audit |
| `DR-STND` | Standards | spec |
| `DR-GUID` | Guide | guide |
| `OD-REF` | Reference | reference |
| `UC-CASE` | Use Case | use_case |

**Required Fields**:
| Field | Type | Source |
|-------|------|--------|
| `doc_id` | string | filename or generated |
| `path` | string | relative path |
| `source_repo` | string | repo name |

**Optional Fields**:
| Field | Type | Source |
|-------|------|--------|
| `title` | string | first H1 or filename |
| `doc_type` | enum | category code mapping |
| `category_code` | string | extracted from filename |
| `status` | enum | frontmatter or default |

## Relationship Types

### Plugin ↔ Skill Relations

| Type | Description |
|------|-------------|
| `ships_with` | Skill is bundled inside the plugin |
| `depends_on` | Plugin requires this skill to function |
| `invokes` | Plugin calls this skill during execution |
| `recommends` | Plugin suggests using this skill |
| `embeds` | Plugin embeds skill content |

### Entity ↔ Document Relations

| Type | Description |
|------|-------------|
| `spec` | Document specifies requirements |
| `decision` | Document records architectural decision |
| `report` | Document reports on status/results |
| `use_case` | Document describes use case |
| `evidence` | Document provides supporting evidence |
| `runbook` | Document provides operational procedures |
| `security` | Document addresses security concerns |
| `marketing` | Document is marketing material |

### Confidence Levels

| Level | Description |
|-------|-------------|
| `manual` | Explicitly defined in source |
| `inferred` | Automatically detected by extractor |

## Output Format

### Main Output: `dist/catalog.json`

```json
{
  "meta": {
    "version": "1.0.0",
    "extracted_at": "2026-01-16T00:00:00Z",
    "repos": [
      {"path": "/path/to/repo", "name": "repo-name", "commit": "abc123"}
    ]
  },
  "plugins": [...],
  "skills": [...],
  "documents": [...],
  "relationships": [...],
  "warnings": [...]
}
```

### Warnings Output: `dist/catalog.warnings.json`

Files that couldn't be parsed deterministically:

```json
[
  {"path": "path/to/file", "message": "Missing frontmatter", "severity": "warning"}
]
```

## Validation Rules

1. All IDs must be unique within their entity type
2. All IDs must be kebab-case (`^[a-z0-9-]+$`)
3. Relationships must reference valid source and target IDs
4. Version fields must be semver format
5. Required fields must be present

## Determinism Guarantees

1. Arrays are sorted alphabetically by ID
2. Object keys are sorted alphabetically
3. Timestamps are ISO 8601 UTC
4. No random or time-based IDs (derived from content)
5. Same repos + same commits = same output

## CLI Usage

```bash
# Extract from multiple repos
./scripts/extract_catalog.py \
  --repo /path/to/ccpi \
  --repo /path/to/nixtla \
  --out dist/catalog.json

# Validate output
./scripts/validate_catalog.py dist/catalog.json

# CI commands
make extract
make validate
make ci
```
