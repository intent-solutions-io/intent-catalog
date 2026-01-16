# Intent Catalog Makefile

PYTHON := python3
SCRIPTS := scripts
DIST := dist
SCHEMA := schema

# Default repos to scan
CCPI_REPO := /home/jeremy/000-projects/claude-code-plugins
NIXTLA_REPO := /home/jeremy/000-projects/nixtla

.PHONY: all extract validate ci clean help

all: ci

## extract: Extract catalog from repos
extract:
	@mkdir -p $(DIST)
	$(PYTHON) $(SCRIPTS)/extract_catalog.py \
		--repo $(CCPI_REPO) \
		--repo $(NIXTLA_REPO) \
		--out $(DIST)/catalog.json

## validate: Validate catalog against schema
validate:
	$(PYTHON) $(SCRIPTS)/validate_catalog.py $(DIST)/catalog.json

## ci: Run full CI pipeline (extract + validate)
ci: extract validate
	@echo "CI passed"

## clean: Remove generated files
clean:
	rm -rf $(DIST)/*.json

## help: Show this help
help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/## //'
