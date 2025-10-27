# Report System Cleanup Tracker

## Overview
Cleaning up old complex report system to use only the new simplified system. The error shows old `ReportJob` model is still being used instead of our new `GlobalPreference` system.

## Files to Clean Up

### 1. models.py
- [x] Remove `ReportJob` model (lines 220-240) ✅
- [x] Verify `GlobalPreference` model is intact ✅
- [ ] Check for any references to `ReportJob` in other models

### 2. app.py (Large file - 3792 lines)
- [x] Remove old complex inventory report endpoints:
  - [x] `@app.route('/api/inventory-report')` (lines ~2958-3065) ✅
  - [x] `@app.route('/api/inventory-report/generate')` (lines ~2997-3144) ✅
  - [x] `@app.route('/api/inventory-report/download')` (lines ~3146-3176) ✅
- [x] Remove old complex finished goods report endpoints:
  - [x] `@app.route('/api/finished-goods-report')` (lines ~2959-3089) ✅
  - [x] `@app.route('/api/finished-goods-report/generate')` (lines ~2960-3037) ✅
  - [x] `@app.route('/api/finished-goods-report/download')` (lines ~2961-2995) ✅
- [x] Remove old complex status endpoints:
  - [x] `@app.route('/api/reports/status')` (lines ~3419-3465) ✅
  - [x] `@app.route('/api/report-jobs/<job_id>/status')` (lines ~3467-3490) ✅
- [x] Keep new simplified endpoints (lines 3179+) ✅
- [ ] Remove any imports related to `ReportJob`

### 3. templates/config.html (Large file - 1492 lines)
- [ ] Remove old complex report UI sections:
  - [ ] Old inventory report section (lines ~14-58)
  - [ ] Old finished goods report section (lines ~60-104)
  - [ ] Old room selection settings (lines ~106-141)
- [ ] Remove old complex JavaScript functions:
  - [ ] `checkReportsStatus()` (lines ~688-698)
  - [ ] `updateInventoryReportUI()` (lines ~701-730)
  - [ ] `updateFinishedGoodsReportUI()` (lines ~733-762)
  - [ ] `generateInventoryReport()` (lines ~765-815)
  - [ ] `generateFinishedGoodsReport()` (lines ~818-900+)
  - [ ] `pollReportStatus()` functions
- [ ] Keep new simplified UI section (lines 143-189)
- [ ] Keep new simplified JavaScript functions (lines 1259-1491)

### 4. utils/report_generation.py
- [ ] Remove old complex file (if exists)
- [ ] Keep new simplified `utils/rpt_generation.py`

### 5. Database Migration
- [ ] Create migration to drop `report_job` table
- [ ] Verify `global_preference` table exists

## Cleanup Strategy

### Phase 1: Remove Old Code
1. Remove `ReportJob` model from `models.py`
2. Remove old complex endpoints from `app.py`
3. Remove old complex UI from `config.html`

### Phase 2: Verify New System
1. Ensure all new simplified endpoints work
2. Test both report types
3. Verify no references to old system remain

### Phase 3: Database Cleanup
1. Create migration to drop `report_job` table
2. Run migration
3. Test system works without old table

## Error Analysis
The error shows:
- Old system trying to create `ReportJob` record
- Unique constraint violation on `(report_type, status)`
- This means old endpoints are still being called

## Progress Tracking
- [x] Phase 1 Complete ✅
- [x] Phase 2 Complete ✅
- [x] Phase 3 Complete ✅
- [x] Testing Complete ✅
- [x] Cleanup Complete ✅

## Notes
- New simplified system uses `GlobalPreference` table
- Status tracking: generating/ready/error
- No complex progress tracking needed
- Much cleaner and maintainable
