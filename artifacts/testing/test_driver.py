"""
Driver Script for Modular Authentication Tests

This script demonstrates how to run individual authentication tests
and provides example test sequences.

Usage:
    python test_driver.py
"""
from test_auth_modular import run_test, list_tests

# ============================================================================
# HARDCODED TEST DATA (modify these as needed)
# ============================================================================

# Use these for testing with existing accounts
EXISTING_EMAIL = "test_1730996743.123456@example.com"
EXISTING_API_KEY = "basic_key_9H3dF7nM2kL4xW6pR8vT"
EXISTING_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."  # Replace with actual token

# Use these for testing new registrations
NEW_EMAIL = None  # Set to None to auto-generate, or specify "newuser@example.com"

# ============================================================================
# EXAMPLE TEST SEQUENCES
# ============================================================================

def example_full_registration_flow():
    """
    Example: Complete registration flow for a new user
    Tests: register -> activation -> token generation -> protected endpoint
    """
    print("\n" + "▓"*70)
    print("▓ EXAMPLE: Full Registration Flow")
    print("▓"*70)
    
    # Step 1: Register
    result = run_test("register", email=NEW_EMAIL)
    if not result:
        print("❌ Registration failed, stopping")
        return
    
    email = result['email']
    activation_token = result['activation_token']
    
    # Step 2: Activate
    result = run_test("activation", token=activation_token)
    if not result:
        print("❌ Activation failed, stopping")
        return
    
    api_key = result['api_key']
    
    # Step 3: Generate token
    result = run_test("token_generation", api_key=api_key)
    if not result:
        print("❌ Token generation failed, stopping")
        return
    
    access_token = result['access_token']
    
    # Step 4: Test protected endpoint
    result = run_test("protected_with_token", access_token=access_token)
    if not result:
        print("❌ Protected endpoint test failed")
        return
    
    print("\n✅ Full registration flow completed successfully!")
    print(f"\n📧 Email: {email}")
    print(f"🔑 API Key: {api_key}")
    print(f"🎫 Token: {access_token[:50]}...")

def example_existing_user_token_generation():
    """
    Example: Generate token for existing user
    Tests: token generation -> protected endpoint
    """
    print("\n" + "▓"*70)
    print("▓ EXAMPLE: Generate Token for Existing User")
    print("▓"*70)
    
    # Generate token
    result = run_test("token_generation", api_key=EXISTING_API_KEY)
    if not result:
        print("❌ Token generation failed")
        return
    
    access_token = result['access_token']
    
    # Test protected endpoint
    result = run_test("protected_with_token", access_token=access_token)
    if result:
        print("\n✅ Token generation and usage successful!")
        print(f"🎫 Token: {access_token[:50]}...")

def example_key_reset_flow():
    """
    Example: Reset API key and test old vs new tokens
    Tests: key reset -> old token (fail) -> new token (succeed)
    """
    print("\n" + "▓"*70)
    print("▓ EXAMPLE: API Key Reset Flow")
    print("▓"*70)
    
    # First, generate token with current key
    result = run_test("token_generation", api_key=EXISTING_API_KEY)
    if not result:
        print("❌ Initial token generation failed, stopping")
        return
    
    old_token = result['access_token']
    print(f"\n📝 Old token: {old_token[:50]}...")
    
    # Reset key
    result = run_test("key_reset", email=EXISTING_EMAIL)
    if not result:
        print("❌ Key reset failed")
        return
    
    new_api_key = result['api_key']
    print(f"\n🔑 New API key: {new_api_key}")
    
    # Test old token (should fail)
    print("\n--- Testing old token (should fail) ---")
    run_test("old_token_after_reset", old_token=old_token)
    
    # Generate and test new token
    print("\n--- Generating and testing new token ---")
    result = run_test("new_token_after_reset", new_api_key=new_api_key)
    if result:
        print("\n✅ Key reset flow completed successfully!")
        print(f"🔑 New API Key: {new_api_key}")

def example_security_tests():
    """
    Example: Run security-related tests
    Tests: no token (fail) -> invalid token (fail) -> valid token (succeed)
    """
    print("\n" + "▓"*70)
    print("▓ EXAMPLE: Security Tests")
    print("▓"*70)
    
    # Test 1: No token
    print("\n--- Test 1: Access without token ---")
    run_test("protected_no_token")
    
    # Test 2: Invalid token
    print("\n--- Test 2: Access with invalid token ---")
    run_test("invalid_token")
    
    # Test 3: Valid token
    print("\n--- Test 3: Access with valid token ---")
    result = run_test("token_generation", api_key=EXISTING_API_KEY)
    if result:
        access_token = result['access_token']
        run_test("protected_with_token", access_token=access_token)
        print("\n✅ Security tests completed!")

def example_individual_tests():
    """
    Example: Run individual tests with hardcoded values
    """
    print("\n" + "▓"*70)
    print("▓ EXAMPLE: Individual Test Runs")
    print("▓"*70)
    
    # Example 1: Test registration only
    print("\n--- Test: Register ---")
    result = run_test("register", email="individual_test@example.com")
    
    # Example 2: Test token generation only
    print("\n--- Test: Token Generation ---")
    result = run_test("token_generation", api_key=EXISTING_API_KEY)
    
    # Example 3: Test protected endpoint only
    if result:
        print("\n--- Test: Protected Endpoint ---")
        run_test("protected_with_token", access_token=result['access_token'])

# ============================================================================
# INTERACTIVE MENU
# ============================================================================

def show_menu():
    """Display interactive menu"""
    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + "  JWT Authentication Test Driver".center(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70)
    print("\nSelect an option:")
    print("  1. Full registration flow (new user)")
    print("  2. Generate token for existing user")
    print("  3. API key reset flow")
    print("  4. Security tests")
    print("  5. Individual test examples")
    print("  6. List all available tests")
    print("  7. Custom test (enter test name)")
    print("  0. Exit")
    print()

def run_custom_test():
    """Allow user to run a custom test with manual parameters"""
    list_tests()
    test_name = input("\nEnter test name: ").strip()
    
    # Get parameters based on test
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
    
    # Run the test
    run_test(test_name, **params)

def interactive_mode():
    """Run in interactive mode with menu"""
    while True:
        show_menu()
        choice = input("Enter your choice: ").strip()
        
        if choice == "1":
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
            list_tests()
        elif choice == "7":
            run_custom_test()
        elif choice == "0":
            print("\nExiting...")
            break
        else:
            print("\n❌ Invalid choice. Please try again.")
        
        input("\nPress Enter to continue...")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import sys
    
    # Check for command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == "--help":
            print("\nUsage:")
            print("  python test_driver.py              # Interactive mode")
            print("  python test_driver.py --example 1  # Run example 1")
            print("  python test_driver.py --example 2  # Run example 2")
            print("  python test_driver.py --example 3  # Run example 3")
            print("  python test_driver.py --example 4  # Run example 4")
            print("  python test_driver.py --example 5  # Run example 5")
            print("  python test_driver.py --list       # List all tests")
            print()
        elif sys.argv[1] == "--list":
            list_tests()
        elif sys.argv[1] == "--example" and len(sys.argv) > 2:
            example_num = sys.argv[2]
            if example_num == "1":
                example_full_registration_flow()
            elif example_num == "2":
                example_existing_user_token_generation()
            elif example_num == "3":
                example_key_reset_flow()
            elif example_num == "4":
                example_security_tests()
            elif example_num == "5":
                example_individual_tests()
            else:
                print(f"Unknown example: {example_num}")
        else:
            print(f"Unknown argument: {sys.argv[1]}")
            print("Use --help for usage information")
    else:
        # Run in interactive mode
        interactive_mode()
