"""
Extended Driver Script for Authentication and Role-Based Testing

This script provides access to both authentication tests and comprehensive
role-based access control tests.

Usage:
    python test_driver_extended.py
"""
from test_auth_modular import run_test as run_auth_test, list_tests as list_auth_tests
from test_roles import (
    run_role_test, 
    run_all_role_tests,
    test_simple_search_access,
    test_simple_search_limits,
    test_simple_search_data_field,
    test_advanced_search_access,
    test_etl_extract_access,
    test_etl_load_access
)

# ============================================================================
# ROLE-BASED TEST CONFIGURATION
# ============================================================================

# Note: Update TEST_KEYS in test_roles.py with actual API keys from your database
AVAILABLE_ROLES = ["PUBLIC", "BASIC", "PREMIUM", "ADMIN"]

# ============================================================================
# INTERACTIVE MENU
# ============================================================================

def show_main_menu():
    """Display main interactive menu"""
    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + "  FBI Wanted API - Comprehensive Test Suite".center(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70)
    print("\nSelect test category:")
    print("  1. Authentication Tests")
    print("  2. Role-Based Access Control Tests")
    print("  3. Run Full Test Suite (All Auth + All Roles)")
    print("  0. Exit")
    print()

def show_auth_menu():
    """Display authentication tests menu"""
    print("\n" + "="*70)
    print(" AUTHENTICATION TESTS")
    print("="*70)
    print("  1. Full registration flow (new user)")
    print("  2. Generate token for existing user")
    print("  3. API key reset flow")
    print("  4. Security tests")
    print("  5. Individual test examples")
    print("  6. List all available auth tests")
    print("  7. Custom auth test")
    print("  0. Back to main menu")
    print()

def show_role_menu():
    """Display role-based tests menu"""
    print("\n" + "="*70)
    print(" ROLE-BASED ACCESS CONTROL TESTS")
    print("="*70)
    print("  1. Test PUBLIC role (should be denied all)")
    print("  2. Test BASIC role (simple search only, limit 25)")
    print("  3. Test PREMIUM role (simple + advanced, limit 5000)")
    print("  4. Test ADMIN role (all endpoints)")
    print("  5. Run all role tests")
    print("  6. Individual role test (custom)")
    print("  0. Back to main menu")
    print()

def show_individual_role_test_menu():
    """Display individual role test options"""
    print("\n" + "="*70)
    print(" INDIVIDUAL ROLE TESTS")
    print("="*70)
    print("  1. Test simple search access")
    print("  2. Test simple search limits")
    print("  3. Test simple search data field")
    print("  4. Test advanced search access")
    print("  5. Test ETL extract access")
    print("  6. Test ETL load access")
    print("  0. Back to role menu")
    print()

# ============================================================================
# AUTH TEST HANDLERS (from original test_driver.py)
# ============================================================================

# Hardcoded test data for auth tests
EXISTING_EMAIL = "test_1730996743.123456@example.com"
EXISTING_API_KEY = "basic_key_9H3dF7nM2kL4xW6pR8vT"
NEW_EMAIL = None

def example_full_registration_flow():
    """Complete registration flow for a new user"""
    print("\n" + "▓"*70)
    print("▓ EXAMPLE: Full Registration Flow")
    print("▓"*70)
    
    result = run_auth_test("register", email=NEW_EMAIL)
    if not result:
        print("❌ Registration failed, stopping")
        return
    
    email = result['email']
    activation_token = result['activation_token']
    
    result = run_auth_test("activation", token=activation_token)
    if not result:
        print("❌ Activation failed, stopping")
        return
    
    api_key = result['api_key']
    
    result = run_auth_test("token_generation", api_key=api_key)
    if not result:
        print("❌ Token generation failed, stopping")
        return
    
    access_token = result['access_token']
    
    result = run_auth_test("protected_with_token", access_token=access_token)
    if not result:
        print("❌ Protected endpoint test failed")
        return
    
    print("\n✅ Full registration flow completed successfully!")
    print(f"\n📧 Email: {email}")
    print(f"🔑 API Key: {api_key}")
    print(f"🎫 Token: {access_token[:50]}...")

def example_existing_user_token_generation():
    """Generate token for existing user"""
    print("\n" + "▓"*70)
    print("▓ EXAMPLE: Generate Token for Existing User")
    print("▓"*70)
    
    result = run_auth_test("token_generation", api_key=EXISTING_API_KEY)
    if not result:
        print("❌ Token generation failed")
        return
    
    access_token = result['access_token']
    
    result = run_auth_test("protected_with_token", access_token=access_token)
    if result:
        print("\n✅ Token generation and usage successful!")
        print(f"🎫 Token: {access_token[:50]}...")

def example_key_reset_flow():
    """Reset API key and test old vs new tokens"""
    print("\n" + "▓"*70)
    print("▓ EXAMPLE: API Key Reset Flow")
    print("▓"*70)
    
    result = run_auth_test("token_generation", api_key=EXISTING_API_KEY)
    if not result:
        print("❌ Initial token generation failed, stopping")
        return
    
    old_token = result['access_token']
    print(f"\n📝 Old token: {old_token[:50]}...")
    
    result = run_auth_test("key_reset", email=EXISTING_EMAIL)
    if not result:
        print("❌ Key reset failed")
        return
    
    new_api_key = result['api_key']
    print(f"\n🔑 New API key: {new_api_key}")
    
    print("\n--- Testing old token (should fail) ---")
    run_auth_test("old_token_after_reset", old_token=old_token)
    
    print("\n--- Generating and testing new token ---")
    result = run_auth_test("new_token_after_reset", new_api_key=new_api_key)
    if result:
        print("\n✅ Key reset flow completed successfully!")
        print(f"🔑 New API Key: {new_api_key}")

def example_security_tests():
    """Run security-related tests"""
    print("\n" + "▓"*70)
    print("▓ EXAMPLE: Security Tests")
    print("▓"*70)
    
    print("\n--- Test 1: Access without token ---")
    run_auth_test("protected_no_token")
    
    print("\n--- Test 2: Access with invalid token ---")
    run_auth_test("invalid_token")
    
    print("\n--- Test 3: Access with valid token ---")
    result = run_auth_test("token_generation", api_key=EXISTING_API_KEY)
    if result:
        access_token = result['access_token']
        run_auth_test("protected_with_token", access_token=access_token)
        print("\n✅ Security tests completed!")

def example_individual_tests():
    """Run individual tests with hardcoded values"""
    print("\n" + "▓"*70)
    print("▓ EXAMPLE: Individual Test Runs")
    print("▓"*70)
    
    print("\n--- Test: Register ---")
    result = run_auth_test("register", email="individual_test@example.com")
    
    print("\n--- Test: Token Generation ---")
    result = run_auth_test("token_generation", api_key=EXISTING_API_KEY)
    
    if result:
        print("\n--- Test: Protected Endpoint ---")
        run_auth_test("protected_with_token", access_token=result['access_token'])

def run_custom_auth_test():
    """Allow user to run a custom auth test"""
    list_auth_tests()
    test_name = input("\nEnter test name: ").strip()
    
    params = {}
    
    if test_name == "register":
        email = input("Enter email (or press Enter for auto-generate): ").strip()
        if email:
            params['email'] = email
    elif test_name == "duplicate_register":
        email = input("Enter email: ").strip()
        if not email:
            print("❌ Email is required for this test")
            return
        params['email'] = email
    elif test_name == "activation":
        token = input("Enter activation token: ").strip()
        if not token:
            print("❌ Token is required for this test")
            return
        params['token'] = token
    elif test_name == "token_generation":
        api_key = input(f"Enter API key (or press Enter to use '{EXISTING_API_KEY[:20]}...'): ").strip()
        params['api_key'] = api_key if api_key else EXISTING_API_KEY
    elif test_name == "protected_with_token":
        access_token = input("Enter access token: ").strip()
        if not access_token:
            print("❌ Access token is required for this test")
            return
        params['access_token'] = access_token
    elif test_name == "key_reset":
        email = input(f"Enter email (or press Enter to use '{EXISTING_EMAIL}'): ").strip()
        params['email'] = email if email else EXISTING_EMAIL
    elif test_name == "old_token_after_reset":
        old_token = input("Enter old token: ").strip()
        if not old_token:
            print("❌ Old token is required for this test")
            return
        params['old_token'] = old_token
    elif test_name == "new_token_after_reset":
        new_api_key = input("Enter new API key: ").strip()
        if not new_api_key:
            print("❌ New API key is required for this test")
            return
        params['new_api_key'] = new_api_key
    
    run_auth_test(test_name, **params)

# ============================================================================
# ROLE TEST HANDLERS
# ============================================================================

def run_individual_role_test():
    """Run individual role test with user input"""
    while True:
        show_individual_role_test_menu()
        choice = input("Enter your choice: ").strip()
        
        if choice == "0":
            break
        
        # Get role
        print(f"\nAvailable roles: {', '.join(AVAILABLE_ROLES)}")
        role = input("Enter role to test: ").strip().upper()
        
        if role not in AVAILABLE_ROLES:
            print(f"❌ Invalid role. Choose from: {', '.join(AVAILABLE_ROLES)}")
            continue
        
        # Get should_succeed parameter
        should_succeed_input = input("Should this test succeed? (y/n, default=y): ").strip().lower()
        should_succeed = should_succeed_input != 'n'
        
        if choice == "1":
            test_simple_search_access(role, should_succeed)
        elif choice == "2":
            limit = input("Enter limit to test (25/50/100/500/5000): ").strip()
            try:
                limit = int(limit)
                test_simple_search_limits(role, limit, should_succeed)
            except ValueError:
                print("❌ Invalid limit")
        elif choice == "3":
            expected_field = input("Enter expected field (full_data/full_data_clean): ").strip()
            test_simple_search_data_field(role, expected_field)
        elif choice == "4":
            test_advanced_search_access(role, should_succeed)
        elif choice == "5":
            test_etl_extract_access(role, should_succeed)
        elif choice == "6":
            test_etl_load_access(role, should_succeed)
        else:
            print("❌ Invalid choice")
        
        input("\nPress Enter to continue...")

# ============================================================================
# MAIN MENU HANDLERS
# ============================================================================

def handle_auth_menu():
    """Handle authentication tests menu"""
    while True:
        show_auth_menu()
        choice = input("Enter your choice: ").strip()
        
        if choice == "0":
            break
        elif choice == "1":
            example_full_registration_flow()
        elif choice == "2":
            example_existing_user_token_generation()
        elif choice == "3":
            example_key_reset_flow()
        elif choice == "4":
            example_security_tests()
        elif choice == "5":
            example_individual_tests()
        elif choice == "6":
            list_auth_tests()
        elif choice == "7":
            run_custom_auth_test()
        else:
            print("❌ Invalid choice")
        
        input("\nPress Enter to continue...")

def handle_role_menu():
    """Handle role-based tests menu"""
    while True:
        show_role_menu()
        choice = input("Enter your choice: ").strip()
        
        if choice == "0":
            break
        elif choice == "1":
            run_role_test("PUBLIC")
        elif choice == "2":
            run_role_test("BASIC")
        elif choice == "3":
            run_role_test("PREMIUM")
        elif choice == "4":
            run_role_test("ADMIN")
        elif choice == "5":
            run_all_role_tests()
        elif choice == "6":
            run_individual_role_test()
        else:
            print("❌ Invalid choice")
        
        input("\nPress Enter to continue...")

def run_full_test_suite():
    """Run complete test suite - all auth tests and all role tests"""
    print("\n" + "▓"*70)
    print("▓" + " "*68 + "▓")
    print("▓" + "  FULL TEST SUITE - AUTHENTICATION + ROLES".center(68) + "▓")
    print("▓" + " "*68 + "▓")
    print("▓"*70)
    
    print("\n" + "="*70)
    print(" PART 1: AUTHENTICATION TESTS")
    print("="*70)
    
    # Run key auth test examples
    print("\n--- Running: Full Registration Flow ---")
    example_full_registration_flow()
    
    print("\n--- Running: Security Tests ---")
    example_security_tests()
    
    print("\n" + "="*70)
    print(" PART 2: ROLE-BASED ACCESS CONTROL TESTS")
    print("="*70)
    
    # Run all role tests
    role_results = run_all_role_tests()
    
    print("\n" + "▓"*70)
    print("▓ FULL TEST SUITE COMPLETE")
    print("▓"*70)

def interactive_mode():
    """Run in interactive mode with menu"""
    while True:
        show_main_menu()
        choice = input("Enter your choice: ").strip()
        
        if choice == "0":
            print("\nExiting...")
            break
        elif choice == "1":
            handle_auth_menu()
        elif choice == "2":
            handle_role_menu()
        elif choice == "3":
            run_full_test_suite()
        else:
            print("❌ Invalid choice. Please try again.")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--help":
            print("\nUsage:")
            print("  python test_driver_extended.py              # Interactive mode")
            print("  python test_driver_extended.py --full       # Run full test suite")
            print("  python test_driver_extended.py --auth       # Run auth examples")
            print("  python test_driver_extended.py --roles      # Run all role tests")
            print("  python test_driver_extended.py --role PUBLIC   # Test specific role")
            print("  python test_driver_extended.py --role BASIC")
            print("  python test_driver_extended.py --role PREMIUM")
            print("  python test_driver_extended.py --role ADMIN")
            print()
        elif sys.argv[1] == "--full":
            run_full_test_suite()
        elif sys.argv[1] == "--auth":
            print("Running authentication test examples...")
            example_full_registration_flow()
            example_security_tests()
        elif sys.argv[1] == "--roles":
            run_all_role_tests()
        elif sys.argv[1] == "--role" and len(sys.argv) > 2:
            role = sys.argv[2].upper()
            if role in AVAILABLE_ROLES:
                run_role_test(role)
            else:
                print(f"Unknown role: {role}")
                print(f"Available roles: {', '.join(AVAILABLE_ROLES)}")
        else:
            print(f"Unknown argument: {sys.argv[1]}")
            print("Use --help for usage information")
    else:
        # Run in interactive mode
        interactive_mode()
