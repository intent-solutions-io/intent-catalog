# Phase Plan Audit

## Gaps Identified

### 1. Enhancement G Incomplete (Phase 1)
**Issue**: `commit_sha` is tracked in `meta.repos` but not per entity.
**Impact**: Cannot trace individual entity to exact commit.
**Fix**: Add `source_commit` field to Plugin, Skill, Document schemas and extractor.

### 2. Missing Test Strategy
**Issue**: No unit tests for extractor, validator, or sync scripts.
**Impact**: Regressions possible; refactoring risky.
**Fix**: Add `tests/` directory with pytest suite for each script.

### 3. No Local Development Mode
**Issue**: No way to test Airtable sync without touching production base.
**Impact**: Risky deployments; hard to iterate.
**Fix**: Add `--base-id` override and document dev base setup in runbook.

### 4. Missing Rollback Strategy
**Issue**: If sync corrupts Airtable data, no documented recovery path.
**Impact**: Production incidents could be unrecoverable.
**Fix**: Add `dist/catalog.backup.json` pre-sync snapshot and rollback script.

### 5. Phase 4-5 Parallelism Opportunity
**Issue**: Doc linkage analysis (Phase 5) doesn't depend on Airtable sync.
**Impact**: Unnecessary serialization slows delivery.
**Revision**: Split Phase 5 - extraction-side quality scoring can start after Phase 1.

### 6. Rate Limit Strategy Missing Early
**Issue**: Rate limiting only addressed in Phase 6, but Phase 3 sync will hit limits.
**Impact**: Phase 3 could fail on large repos.
**Fix**: Add basic batching in Phase 3, refine in Phase 6.

## Revised Phase Plan

### Phase 1 (Current)
- Complete Enhancement G (commit_sha per entity)
- Add basic test suite for extractor/validator
- **Definition of Done**: `make ci` passes, all entities have source_commit

### Phase 2 (Schema Provisioning)
- Add Enhancement C (schema as code)
- Include dev base ID in config for local testing
- **Definition of Done**: Idempotent provisioner, mappings file generated

### Phase 3 (Sync)
- Add Enhancement A (protected fields)
- Add Enhancement F (confidence levels in links)
- Basic batching (10 records/request) to avoid rate limits
- Pre-sync backup snapshot
- **Definition of Done**: Idempotent sync, DRY_RUN works, protected fields preserved

### Phase 4 (Multi-repo + Incremental)
- Add Enhancement B (incremental sync)
- Add Enhancement G completion (collision-safe IDs)
- Config-driven repo list
- **Definition of Done**: No-op runs are fast, no ID collisions

### Phase 5 (Quality + Doc Linkage)
- Add Enhancement D (doc fixer)
- Add Enhancement E (quality dashboard)
- Can run quality scoring on extraction output (no Airtable dependency)
- **Definition of Done**: Quality report generated, fixer works in check mode

### Phase 6 (Production Hardening)
- Exponential backoff, correlation IDs
- Evidence bundles
- Full runbook
- Scheduled nightly job
- **Definition of Done**: Nightly job stable for 7 days

## Enhancements Mapping

| Enhancement | Phase | Status |
|-------------|-------|--------|
| A) Protected-field policy | 3 | Planned |
| B) Incremental sync | 4 | Planned |
| C) Schema provisioning | 2 | Planned |
| D) Doc-linking fixer | 5 | Planned |
| E) Quality scoring | 5 | Planned |
| F) Relationship inference | 1,3 | Partial (confidence exists) |
| G) Multi-repo normalization | 1,4 | In Progress (needs commit_sha) |

## Additional Improvements Added

1. **Test suite**: pytest for all scripts (Phase 1+)
2. **Dev base support**: Local testing without prod risk (Phase 2+)
3. **Rollback capability**: Pre-sync snapshots (Phase 3+)
4. **Early batching**: Avoid rate limits from Phase 3 (not just Phase 6)
