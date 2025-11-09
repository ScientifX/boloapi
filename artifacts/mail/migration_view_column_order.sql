-- Alternative: Create View with Desired Column Order
-- Use this if you prefer not to recreate the table
-- This doesn't change the actual table, just how you see it

-- Create view with desired column order
CREATE OR REPLACE VIEW vw_users_ordered AS
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

-- Now you can query the view instead of the table:
-- SELECT * FROM vw_users_ordered;

-- Verify the view
SELECT 
    column_name, 
    ordinal_position,
    data_type
FROM information_schema.columns
WHERE table_name = 'vw_users_ordered'
ORDER BY ordinal_position;

-- Test the view
SELECT * FROM vw_users_ordered LIMIT 5;
