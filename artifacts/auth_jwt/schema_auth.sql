-- Authentication Schema for BOLO API
-- Creates users table and related functions for JWT-based authentication

-- Users table
CREATE TABLE IF NOT EXISTS tbl_users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'basic',
    api_key_hash VARCHAR(255),  -- bcrypt hash of the API key
    is_active BOOLEAN DEFAULT FALSE,
    activation_token VARCHAR(255),  -- Cleared after activation
    activation_expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_login_at TIMESTAMP,
    
    CONSTRAINT valid_role CHECK (role IN ('public', 'basic', 'premium', 'admin')),
    CONSTRAINT email_format CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$')
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_tbl_users_email ON tbl_users(email);
CREATE INDEX IF NOT EXISTS idx_tbl_users_activation_token ON tbl_users(activation_token) 
    WHERE activation_token IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tbl_users_active ON tbl_users(is_active) WHERE is_active = TRUE;

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_tbl_users_updated_at 
    BEFORE UPDATE ON tbl_users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- View for active tbl_users (excluding sensitive data)
CREATE OR REPLACE VIEW vw_active_users AS
SELECT 
    user_id,
    email,
    role,
    is_active,
    created_at,
    last_login_at
FROM tbl_users
WHERE is_active = TRUE;

-- Grant permissions (adjust as needed for your database user)
-- GRANT SELECT, INSERT, UPDATE ON users TO your_app_user;
-- GRANT SELECT ON vw_active_users TO your_app_user;
