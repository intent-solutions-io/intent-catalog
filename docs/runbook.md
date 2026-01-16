# Intent Catalog Runbook

## Local Setup

### Prerequisites

- Python 3.10+
- pip

### Install Dependencies

```bash
pip install pyyaml jsonschema
```

### Verify Installation

```bash
python scripts/extract_catalog.py --help
python scripts/validate_catalog.py --help
```

## Running Locally

### Extract Catalog

```bash
# Using Makefile (uses default repo paths)
make extract

# Custom repos
python scripts/extract_catalog.py \
  --repo /home/jeremy/000-projects/claude-code-plugins \
  --repo /home/jeremy/000-projects/nixtla \
  --out dist/catalog.json
```

### Validate Output

```bash
make validate
# or
python scripts/validate_catalog.py dist/catalog.json
```

### Full CI

```bash
make ci
```

## Output Files

| File | Description |
|------|-------------|
| `dist/catalog.json` | Main catalog output |
| `dist/catalog.warnings.json` | Parsing warnings |

## Troubleshooting

### "Schema not found"

Ensure you're running from the repo root:
```bash
cd /home/jeremy/000-projects/intent-catalog
make validate
```

### "jsonschema not installed"

```bash
pip install jsonschema
```

### "Repo path does not exist"

Check the repo paths in the Makefile or pass explicit `--repo` flags.

### High Warning Count

Warnings indicate files that couldn't be parsed deterministically:
- Missing YAML frontmatter in SKILL.md
- Non-standard document naming
- JSON parse errors in manifests

Review `dist/catalog.warnings.json` for details.

## Adding New Repos

Edit `Makefile` to add repo paths:

```makefile
NEW_REPO := /path/to/new/repo

extract:
    $(PYTHON) $(SCRIPTS)/extract_catalog.py \
        --repo $(CCPI_REPO) \
        --repo $(NIXTLA_REPO) \
        --repo $(NEW_REPO) \
        --out $(DIST)/catalog.json
```

## CI/CD

GitHub Actions runs on:
- Push to master/main
- Pull requests

Workflow:
1. Checkout repos
2. Install Python + deps
3. Run extract
4. Run validate
5. Upload artifact (on main)
