# Plan: Validate Schools and Daycares Against PHIX Reference List

**Status:** ✅ Implemented  
**Date:** 2026-01-14  

---

## Problem Statement

Input data contains school/daycare names that may not match the official PHIX (Public Health Information Exchange) reference list. This causes:
- Data quality issues in reports
- Difficulty linking records to official facility IDs
- No validation that facilities exist in the PHU's jurisdiction

## Solution

Add a validation step in preprocessing that matches input school/daycare names against the PHIX reference list using strict exact comparisons with configurable behavior for unmatched facilities.

---

## Implementation

### Files Created

| File | Purpose |
|------|---------|
| `pipeline/validate_phix.py` | Validation module with loading, matching, and batch validation |
| `tests/unit/test_validate_phix.py` | 26 unit tests covering all functionality |

### Files Modified

| File | Changes |
|------|---------|
| `config/parameters.yaml` | Added `phix_validation` configuration section |
| `pipeline/orchestrator.py` | Integrated validation into Step 2 (Preprocessing) |

### Configuration Options

```yaml
phix_validation:
  enabled: true
  reference_file: BYO_PHIX_REFERENCE.xlsx   # Placeholder; operators supply actual PHIX workbook path
  phu_mapping_file: config/phu_aliases.yaml   # Maps PHIX column names -> template codes
  target_phu_code: null                       # Optional default scope when no template is provided
  unmatched_behavior: warn # warn | error | skip
```

**Behavior modes:**
- `warn` - Log warning, continue processing all records
- `error` - Fail pipeline if any facilities don't match
- `skip` - Filter out records with unmatched facilities

---

## How It Works

### Pipeline Flow

```
Step 2: Preprocessing
├── read_input()
├── map_columns()
├── filter_columns()
├── ensure_required_columns()
├── check_addresses_complete()
├── validate_facilities()        ← NEW: PHIX validation
│   ├── Load PHIX Excel reference
│   ├── Normalize facility names
│   ├── Map PHIX PHU columns to canonical template codes
│   ├── Restrict matching to template/config PHU scope (if configured)
│   ├── Try exact match (100% confidence)
│   ├── Write unmatched to CSV
│   └── Enrich DataFrame/metadata with PHIX IDs + PHU scope
├── build_preprocess_result()
└── write_artifact()
```

### PHIX Reference Format

The Excel file has one column per PHU, with values in `"FACILITY NAME - ID"` format:

```
| Algoma PHU                              | Brant PHU                    |
|----------------------------------------|------------------------------|
| ANNA MCCREA PUBLIC SCHOOL - 019186     | BRANTFORD ELEMENTARY - 12345 |
| SUNSHINE DAYCARE - AL-0003561          | MAPLE CHILDCARE - 67890      |
```

### Output

**Console:**
```
Step 2: Preprocessing
...
🏫 PHIX validation complete: 1,247 records validated
⚠️  3 facilities not found in PHIX reference. See output/unmatched_facilities.csv
```

**Enriched data (per record):**
- `PHIX_ID` - Official facility identifier
- `PHIX_MATCH_CONFIDENCE` - Match score (0-100)
- `PHIX_MATCH_TYPE` - "exact" or "none"
- `PHIX_MATCHED_PHU` / `_CODE` - PHU column + canonical code for the matched facility
- `PHIX_TARGET_PHU_CODE` / `_LABEL` - Template/config PHU scope copied to metadata
- Artifact metadata includes `phix_validation` payload so Step 6 can log PHIX scope per PDF

**Unmatched report (`output/unmatched_facilities.csv`):**
```csv
facility_name,match_type,confidence
Lincon Elementary School,none,0
New Daycare Centre,none,0
```

---

## Design Decisions

### 1. Excel vs JSON for reference data

**Decision:** Keep Excel as source (official PHIX format PHUs receive)

**Rationale:**
- PHU staff can update without technical knowledge
- No manual conversion step to forget
- Caching makes load time acceptable

**Trade-off:** Slightly slower initial load (~0.5s vs ~50ms)

### 2. Integration point

**Decision:** After `check_addresses_complete()`, before `build_preprocess_result()`

**Rationale:**
- Validates after basic data normalization
- Can filter records before building client objects
- Follows existing validation pattern (addresses)

### 3. Fuzzy matching algorithm

**Decision:** Require exact facility name matches (case-insensitive)

**Rationale:**
- Eliminates the risk of picking the wrong facility due to similar spellings
- Aligns with Panorama usage where facility folders/templates must match canonical names
- Encourages upstream data normalization (alias mapping now solved by PHU mapping, not name similarity)

### 4. PHU alias mapping and PDF auditing

**Decision:** Require a YAML mapping (`config/phu_aliases.yaml`) that links PHIX column headers
to template acronyms; propagate PHIX scope into PDF validation logs.

**Rationale:**
- Prevents cross-PHU matches when multiple units share similarly named schools.
- Supports PHU mergers by allowing multiple PHIX aliases to map to one template code.
- PDF validation now records `phix_target_phu_code`/`phix_matched_phu_code` per notice and
  emits a `phix_target_phu` warning if the PHU codes diverge, giving auditors a traceable log.
- Threshold 85% catches minor typos without false positives

---

## Testing

```bash
# Run PHIX validation tests only
uv run pytest tests/unit/test_validate_phix.py -v

# Run all unit tests
uv run pytest -m unit
```

**Test coverage:**
- Parsing PHIX entries ("NAME - ID" format)
- Exact match behavior (case-insensitive, typo rejection)
- All three `unmatched_behavior` modes
- Edge cases (empty data, missing columns)
- Caching behavior

---

## Future Enhancements

1. **JSON cache layer** - Auto-generate JSON cache for faster loads
2. **CLI command** - `viper convert-phix` to pre-generate JSON
3. **PHU filtering** - Only load facilities for configured PHU
4. **Alias support** - Allow manual alias mappings for known variations
- BYO PHIX file: keep the licensed workbook outside git (ignored by pattern) and update `reference_file` locally before running.
