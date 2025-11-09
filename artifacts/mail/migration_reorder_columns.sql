-- Migration: Reorder tbl_users Columns
-- Date: 2025-01-XX
-- Purpose: Reorder columns for better logical grouping

-- IMPORTANT: This migration preserves all data and constraints

BEGIN;

-- Step 1: Create new table with desired column order
CREATE TABLE tbl_users_new (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    role VARCHAR(50) NOT NULL,
    api_key_hash TEXT NOT NULL,
    is_active BOOLEAN DEFAULT FALSE,
    activation_token VARCHAR(255),
    activation_expires_at TIMESTAMP,
    key_reset_count INTEGER DEFAULT 0,
    key_reset_date DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_login_at TIMESTAMP
);

-- Step 2: Copy all data from old table to new table
INSERT INTO tbl_users_new (
    user_id,
    email,
    role,
    api_key_hash,
    is_active,
    activation_token,
    activation_expires_at,
    key_reset_count,
    key_reset_date,
    created_at,
    updated_at,
    last_login_at
)
SELECT 
    user_id,
    email,
    role,
    api_key_hash,
    is_active,
    activation_token,
    activation_expires_at,
    key_reset_count,
    key_reset_date,
    created_at,
    updated_at,
    last_login_at
FROM tbl_users;

-- Step 3: Drop old table
DROP TABLE tbl_users;

-- Step 4: Rename new table to original name
ALTER TABLE tbl_users_new RENAME TO tbl_users;

-- Step 5: Recreate indexes
CREATE INDEX IF NOT EXISTS idx_users_email ON tbl_users(email);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON tbl_users(is_active);
CREATE INDEX IF NOT EXISTS idx_users_activation_token ON tbl_users(activation_token);
CREATE INDEX IF NOT EXISTS idx_users_key_reset_date ON tbl_users(key_reset_date);

-- Step 6: Add column comments for documentation
COMMENT ON COLUMN tbl_users.user_id IS 'Unique user identifier (UUID)';
COMMENT ON COLUMN tbl_users.email IS 'User email address (unique)';
COMMENT ON COLUMN tbl_users.role IS 'User role: public, basic, premium, admin';
COMMENT ON COLUMN tbl_users.api_key_hash IS 'Bcrypt hash of API key';
COMMENT ON COLUMN tbl_users.is_active IS 'Whether account is activated';
COMMENT ON COLUMN tbl_users.activation_token IS 'Token for account activation (null after activation)';
COMMENT ON COLUMN tbl_users.activation_expires_at IS 'Activation token expiration (48 hours)';
COMMENT ON COLUMN tbl_users.key_reset_count IS 'Number of key resets today';
COMMENT ON COLUMN tbl_users.key_reset_date IS 'Date of last key reset';
COMMENT ON COLUMN tbl_users.created_at IS 'Account creation timestamp';
COMMENT ON COLUMN tbl_users.updated_at IS 'Last update timestamp';
COMMENT ON COLUMN tbl_users.last_login_at IS 'Last successful login timestamp';

COMMIT;

-- Verify the new column order
SELECT 
    column_name, 
    ordinal_position,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'tbl_users'
ORDER BY ordinal_position;

-- Verify data integrity (count should match)
SELECT COUNT(*) as total_users FROM tbl_users;

-- Show sample of data
SELECT 
    user_id,
    email,
    role,
    is_active,
    key_reset_count,
    key_reset_date,
    created_at
FROM tbl_users
ORDER BY created_at DESC
LIMIT 5;
