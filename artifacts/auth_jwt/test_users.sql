-- ============================================================================
-- TEST USERS FOR JWT AUTHENTICATION SYSTEM
-- ============================================================================
--
-- IMPORTANT: Save the API keys below! You'll need them to get JWT tokens.
--
-- To get a JWT token:
--   POST /auth/token
--   Body: {"api_key": "the_plaintext_key_below"}
--
-- ============================================================================

-- USER 1: PUBLIC - public.user@example.com
-- Plaintext API Key: pub_key_2x9K4mNp7rT3wQvY8sL1
INSERT INTO tbl_users (email, role, api_key_hash, is_active, created_at, updated_at)
VALUES (
    'basic.user0@example.com',
    'basic',
    '$2b$12$766aCSbrkCyp.pS5pcP3.Oryk3Y0Kcm70pDVKuEXCZOCprX3wx3ZK',
    TRUE,
    NOW(),
    NOW()
);

-- USER 2: BASIC - basic.user1@example.com
-- Plaintext API Key: basic_key_9H3dF7nM2kL4xW6pR8vT
INSERT INTO tbl_users (email, role, api_key_hash, is_active, created_at, updated_at)
VALUES (
    'basic.user1@example.com',
    'basic',
    '$2b$12$hclpCp6tz9fL8iHqqEA87ubgyHy0DPOwA5E9L9rDhK81M2D18krCW',
    TRUE,
    NOW(),
    NOW()
);

-- USER 3: BASIC - basic.user2@example.com
-- Plaintext API Key: basic_key_4K8mT6pY3qN9wR2sL7xV
INSERT INTO tbl_users (email, role, api_key_hash, is_active, created_at, updated_at)
VALUES (
    'basic.user2@example.com',
    'basic',
    '$2b$12$nZe1zmxdLkgB77XKLjmGX.KH6pzlrgwUDZF/zbD5zbBqNymOSIaJ.',
    TRUE,
    NOW(),
    NOW()
);

-- USER 4: BASIC - basic.user3@example.com
-- Plaintext API Key: basic_key_7R5nW3kM8pT4yL2vX9qH
INSERT INTO tbl_users (email, role, api_key_hash, is_active, created_at, updated_at)
VALUES (
    'basic.user3@example.com',
    'basic',
    '$2b$12$aqtCvnGeOXwGo1DSfV163eeKROSSN/LU15O4nn9efu5yMv3/0.Oty',
    TRUE,
    NOW(),
    NOW()
);

-- USER 5: PREMIUM - premium.user1@example.com
-- Plaintext API Key: prem_key_8N4mK7pT3wY9rL6xQ2vH
INSERT INTO tbl_users (email, role, api_key_hash, is_active, created_at, updated_at)
VALUES (
    'premium.user1@example.com',
    'premium',
    '$2b$12$LPNVwFYZf9w7XMWYcek1mOcBRLVDJnLVsYuJGWxrlMfrj3MZ4gbkK',
    TRUE,
    NOW(),
    NOW()
);

-- USER 6: PREMIUM - premium.user2@example.com
-- Plaintext API Key: prem_key_5W9nR4kT7mL3pY8xQ6vH
INSERT INTO tbl_users (email, role, api_key_hash, is_active, created_at, updated_at)
VALUES (
    'premium.user2@example.com',
    'premium',
    '$2b$12$602F/1hk8g1Iiwc7ZqGjy.1XceZ/Wr/7v7gA3sjjffYanecPoQzGa',
    TRUE,
    NOW(),
    NOW()
);

-- USER 7: PREMIUM - premium.user3@example.com
-- Plaintext API Key: prem_key_2L7nW5kM9pT4xR8qY3vH
INSERT INTO tbl_users (email, role, api_key_hash, is_active, created_at, updated_at)
VALUES (
    'premium.user3@example.com',
    'premium',
    '$2b$12$ZtNsdZ1dh6Ll9MdF8u1PreFEe3TjM9aldmYDXgTkD.Cp5/Mgp90kG',
    TRUE,
    NOW(),
    NOW()
);

-- USER 8: ADMIN - admin.user1@example.com
-- Plaintext API Key: admin_key_6M9pT4nW8kL3xR7qY2vH
INSERT INTO tbl_users (email, role, api_key_hash, is_active, created_at, updated_at)
VALUES (
    'admin.user1@example.com',
    'admin',
    '$2b$12$ahKt5XpV6Kc6Oxr951Wjl.0AfTKJQrwD0A0O/ACqyMCZPD5gIFmy6',
    TRUE,
    NOW(),
    NOW()
);

-- USER 9: ADMIN - admin.user2@example.com
-- Plaintext API Key: admin_key_3N7mK5pT9wL4xR8qY6vH
INSERT INTO tbl_users (email, role, api_key_hash, is_active, created_at, updated_at)
VALUES (
    'admin.user2@example.com',
    'admin',
    '$2b$12$XFMcBkhKH3sDdkpjGQdyYO2iFQuyKaBTDtrIP9yz5iWlHq5Ul3RM2',
    TRUE,
    NOW(),
    NOW()
);

-- USER 10: ADMIN - test.developer@example.com
-- Plaintext API Key: dev_key_4K8mT6pY3qN9wR2sL7xV5
INSERT INTO tbl_users (email, role, api_key_hash, is_active, created_at, updated_at)
VALUES (
    'test.developer@example.com',
    'admin',
    '$2b$12$8Z5sp7GJYpKdcjsKhyg9QuTkzu35fEd17P6jWwO1o01CDM0.m2dHi',
    TRUE,
    NOW(),
    NOW()
);

-- ============================================================================
-- QUICK REFERENCE - API KEYS BY ROLE
-- ============================================================================

-- BASIC USERS:
--   basic.user0@example.com             → pub_key_2x9K4mNp7rT3wQvY8sL1
--   basic.user1@example.com             → basic_key_9H3dF7nM2kL4xW6pR8vT
--   basic.user2@example.com             → basic_key_4K8mT6pY3qN9wR2sL7xV
--   basic.user3@example.com             → basic_key_7R5nW3kM8pT4yL2vX9qH

-- PREMIUM USERS:
--   premium.user1@example.com           → prem_key_8N4mK7pT3wY9rL6xQ2vH
--   premium.user2@example.com           → prem_key_5W9nR4kT7mL3pY8xQ6vH
--   premium.user3@example.com           → prem_key_2L7nW5kM9pT4xR8qY3vH

-- ADMIN USERS:
--   admin.user1@example.com             → admin_key_6M9pT4nW8kL3xR7qY2vH
--   admin.user2@example.com             → admin_key_3N7mK5pT9wL4xR8qY6vH
--   test.developer@example.com          → dev_key_4K8mT6pY3qN9wR2sL7xV5

-- ============================================================================
-- ROLE CAPABILITIES
-- ============================================================================
-- PUBLIC:  Can access homepage, health check, auth endpoints only
-- BASIC:   PUBLIC + simple search (max 25 results, full_data)
-- PREMIUM: BASIC + advanced search (max 5000 results, full_data_clean)
-- ADMIN:   PREMIUM + ETL endpoints (extract, load, full_refresh)
-- ============================================================================
