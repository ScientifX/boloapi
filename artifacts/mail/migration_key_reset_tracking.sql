-- Migration: Add Key Reset Tracking Columns
-- Date: 2025-01-XX
-- Purpose: Track daily key reset attempts per user

-- Add columns to tbl_users
ALTER TABLE tbl_users 
ADD COLUMN IF NOT EXISTS key_reset_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS key_reset_date DATE;

-- Add index for performance
CREATE INDEX IF NOT EXISTS idx_users_key_reset_date 
ON tbl_users(key_reset_date);

-- Add comment for documentation
COMMENT ON COLUMN tbl_users.key_reset_count IS 'Number of key resets today';
COMMENT ON COLUMN tbl_users.key_reset_date IS 'Date of last key reset (for daily counter reset)';

-- Verify columns were added
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'tbl_users'
  AND column_name IN ('key_reset_count', 'key_reset_date')
ORDER BY column_name;
