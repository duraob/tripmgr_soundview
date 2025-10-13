-- =====================================================
-- Location Mapping Update Script for Vendor Filtering Fix
-- =====================================================
-- 
-- This script automates the update of location_mapping table
-- after vendor refresh to handle the transition from UBI-based
-- vendor IDs to location-based vendor IDs.
--
-- PREREQUISITES:
-- 1. Database migration has been run (ubi column added to vendor table)
-- 2. Vendor data has been refreshed from BioTrack API
-- 3. Backup of current data has been created
--
-- USAGE:
-- psql -d your_database_name -f update_location_mappings.sql
-- =====================================================

-- Start transaction for safety
BEGIN;

-- =====================================================
-- STEP 1: Create backup tables for safety
-- =====================================================

-- Backup current location mappings
CREATE TABLE location_mapping_backup AS 
SELECT * FROM location_mapping;

-- Backup current vendor data
CREATE TABLE vendor_backup AS 
SELECT * FROM vendor;

-- Log the backup creation
INSERT INTO api_refresh_log (api_name, last_refresh, records_count, status, error_message)
VALUES ('location_mapping_backup', NOW(), (SELECT COUNT(*) FROM location_mapping), 'success', 'Backup created before location mapping updates');

-- =====================================================
-- STEP 2: Analyze current state
-- =====================================================

-- Show current location mappings that need updating
-- (mappings that still point to UBI values instead of location IDs)
SELECT 
    'CURRENT MAPPINGS TO UPDATE:' as info,
    lm.id,
    lm.leaftrade_dispensary_location_id,
    lm.biotrack_vendor_id as current_vendor_id,
    c.name as customer_name,
    c.city as customer_city,
    v.name as vendor_name,
    v.ubi as vendor_ubi
FROM location_mapping lm
JOIN customer c ON lm.customer_id = c.id
LEFT JOIN vendor v ON lm.biotrack_vendor_id = v.biotrack_vendor_id
WHERE lm.biotrack_vendor_id IN (
    SELECT DISTINCT ubi FROM vendor WHERE ubi IS NOT NULL
);

-- Show available vendors with same UBI (Manchester and Hartford)
SELECT 
    'AVAILABLE VENDORS WITH SAME UBI:' as info,
    v.id,
    v.biotrack_vendor_id as location_id,
    v.name as vendor_name,
    v.ubi,
    v.license_info
FROM vendor v
WHERE v.ubi IN (
    SELECT DISTINCT ubi FROM vendor 
    WHERE ubi IS NOT NULL 
    GROUP BY ubi 
    HAVING COUNT(*) > 1
)
ORDER BY v.ubi, v.name;

-- =====================================================
-- STEP 3: Update location mappings based on business logic
-- =====================================================

-- Option A: Automatic mapping based on customer city
-- This assumes customers in Manchester should map to Manchester vendor
-- and customers in Hartford should map to Hartford vendor

-- Update mappings for Manchester customers
UPDATE location_mapping 
SET 
    biotrack_vendor_id = 'ACRE0015647',  -- Manchester location ID
    updated_at = NOW()
WHERE customer_id IN (
    SELECT c.id 
    FROM customer c 
    WHERE c.city ILIKE '%Manchester%'
    OR c.name ILIKE '%Manchester%'
)
AND biotrack_vendor_id IN (
    SELECT DISTINCT ubi FROM vendor WHERE ubi IS NOT NULL
);

-- Update mappings for Hartford customers
UPDATE location_mapping 
SET 
    biotrack_vendor_id = 'ACRE0015648',  -- Hartford location ID
    updated_at = NOW()
WHERE customer_id IN (
    SELECT c.id 
    FROM customer c 
    WHERE c.city ILIKE '%Hartford%'
    OR c.name ILIKE '%Hartford%'
)
AND biotrack_vendor_id IN (
    SELECT DISTINCT ubi FROM vendor WHERE ubi IS NOT NULL
);

-- =====================================================
-- STEP 4: Handle remaining mappings (manual review required)
-- =====================================================

-- Show mappings that still need manual attention
SELECT 
    'MAPPINGS REQUIRING MANUAL REVIEW:' as info,
    lm.id,
    lm.leaftrade_dispensary_location_id,
    lm.biotrack_vendor_id as current_vendor_id,
    c.name as customer_name,
    c.city as customer_city,
    c.state as customer_state,
    'MANUAL UPDATE REQUIRED' as action_needed
FROM location_mapping lm
JOIN customer c ON lm.customer_id = c.id
WHERE lm.biotrack_vendor_id IN (
    SELECT DISTINCT ubi FROM vendor WHERE ubi IS NOT NULL
)
AND lm.customer_id NOT IN (
    SELECT c.id 
    FROM customer c 
    WHERE c.city ILIKE '%Manchester%' 
    OR c.city ILIKE '%Hartford%'
    OR c.name ILIKE '%Manchester%' 
    OR c.name ILIKE '%Hartford%'
);

-- =====================================================
-- STEP 5: Verify updates
-- =====================================================

-- Show updated mappings
SELECT 
    'UPDATED MAPPINGS:' as info,
    lm.id,
    lm.leaftrade_dispensary_location_id,
    lm.biotrack_vendor_id as new_vendor_id,
    c.name as customer_name,
    c.city as customer_city,
    v.name as vendor_name,
    v.ubi as vendor_ubi
FROM location_mapping lm
JOIN customer c ON lm.customer_id = c.id
JOIN vendor v ON lm.biotrack_vendor_id = v.biotrack_vendor_id
WHERE lm.updated_at >= NOW() - INTERVAL '1 minute';

-- Check for orphaned mappings (mappings pointing to non-existent vendors)
SELECT 
    'ORPHANED MAPPINGS (SHOULD BE 0):' as info,
    COUNT(*) as orphaned_count
FROM location_mapping lm
LEFT JOIN vendor v ON lm.biotrack_vendor_id = v.biotrack_vendor_id
WHERE v.biotrack_vendor_id IS NULL;

-- =====================================================
-- STEP 6: Manual mapping updates (if needed)
-- =====================================================

-- Uncomment and modify these queries for manual updates if needed:

/*
-- Example: Update specific customer to Manchester vendor
UPDATE location_mapping 
SET 
    biotrack_vendor_id = 'ACRE0015647',  -- Manchester location ID
    updated_at = NOW()
WHERE customer_id = [SPECIFIC_CUSTOMER_ID]
AND biotrack_vendor_id IN (
    SELECT DISTINCT ubi FROM vendor WHERE ubi IS NOT NULL
);

-- Example: Update specific customer to Hartford vendor  
UPDATE location_mapping 
SET 
    biotrack_vendor_id = 'ACRE0015648',  -- Hartford location ID
    updated_at = NOW()
WHERE customer_id = [SPECIFIC_CUSTOMER_ID]
AND biotrack_vendor_id IN (
    SELECT DISTINCT ubi FROM vendor WHERE ubi IS NOT NULL
);
*/

-- =====================================================
-- STEP 7: Final verification
-- =====================================================

-- Summary of changes
SELECT 
    'FINAL SUMMARY:' as info,
    COUNT(*) as total_mappings,
    COUNT(CASE WHEN lm.biotrack_vendor_id IN (SELECT biotrack_vendor_id FROM vendor) THEN 1 END) as valid_mappings,
    COUNT(CASE WHEN lm.biotrack_vendor_id NOT IN (SELECT biotrack_vendor_id FROM vendor) THEN 1 END) as invalid_mappings
FROM location_mapping lm;

-- Show all current mappings with vendor details
SELECT 
    'ALL CURRENT MAPPINGS:' as info,
    lm.id,
    lm.leaftrade_dispensary_location_id,
    lm.biotrack_vendor_id,
    c.name as customer_name,
    c.city as customer_city,
    v.name as vendor_name,
    v.ubi as vendor_ubi,
    CASE 
        WHEN v.biotrack_vendor_id IS NOT NULL THEN 'VALID'
        ELSE 'INVALID - NEEDS FIX'
    END as status
FROM location_mapping lm
JOIN customer c ON lm.customer_id = c.id
LEFT JOIN vendor v ON lm.biotrack_vendor_id = v.biotrack_vendor_id
ORDER BY c.name, v.name;

-- Log the completion
INSERT INTO api_refresh_log (api_name, last_refresh, records_count, status, error_message)
VALUES (
    'location_mapping_update', 
    NOW(), 
    (SELECT COUNT(*) FROM location_mapping WHERE updated_at >= NOW() - INTERVAL '1 minute'),
    'success', 
    'Location mappings updated for vendor filtering fix'
);

-- =====================================================
-- COMMIT OR ROLLBACK DECISION
-- =====================================================

-- Review the results above before committing
-- If everything looks good, uncomment the next line:
-- COMMIT;

-- If you need to rollback, uncomment the next line:
-- ROLLBACK;

-- =====================================================
-- ROLLBACK INSTRUCTIONS (if needed)
-- =====================================================

/*
-- To rollback changes:
-- 1. ROLLBACK the transaction (above)
-- 2. Or restore from backup:
--    DROP TABLE location_mapping;
--    ALTER TABLE location_mapping_backup RENAME TO location_mapping;
--    DROP TABLE vendor_backup;
*/
