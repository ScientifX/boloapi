"""
Key Reset Daily Limit Test Script
Tests the daily limit enforcement on API key resets

Usage:
    python test_key_reset_limit.py [email]
    
Example:
    python test_key_reset_limit.py test@example.com
"""

import sys
import os
import requests
import time
from datetime import datetime

# Configuration
BASE_URL = os.getenv('API_APP_BASE_URL', 'http://localhost:8000')

def print_section(title):
    """Print a formatted section header"""
    print("\n" + "="*70)
    print(f"  {title}")
    print("="*70)

def test_key_reset_limit(email, max_attempts=10):
    """
    Test the daily key reset limit by attempting multiple resets.
    
    Args:
        email: Email address to test with
        max_attempts: Maximum number of reset attempts (default: 10)
    """
    print_section("Key Reset Daily Limit Test")
    
    print(f"Testing with email: {email}")
    print(f"Maximum attempts: {max_attempts}")
    print(f"API Base URL: {BASE_URL}")
    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    print("\n⚠️  WARNING: This test will:")
    print("   1. Reset your API key multiple times")
    print("   2. Invalidate previous API keys with each reset")
    print("   3. Test the daily limit enforcement")
    
    confirm = input("\nProceed with test? (yes/no): ").strip().lower()
    if confirm != 'yes':
        print("\n❌ Test cancelled")
        return False
    
    print("\n" + "-"*70)
    print("Starting reset attempts...")
    print("-"*70)
    
    successful_resets = []
    limit_hit = False
    limit_hit_at = None
    
    for attempt in range(1, max_attempts + 1):
        print(f"\n🔄 Attempt #{attempt}")
        
        try:
            payload = {"email": email}
            response = requests.post(
                f"{BASE_URL}/auth/key/reset",
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                # Success
                data = response.json()
                api_key = data.get('api_key', '')
                email_sent = data.get('email_sent', False)
                
                print(f"   ✅ Status: 200 OK")
                print(f"   📧 Email sent: {email_sent}")
                print(f"   🔑 API Key: {api_key[:20]}...{api_key[-10:]}")
                
                successful_resets.append({
                    'attempt': attempt,
                    'api_key': api_key,
                    'timestamp': datetime.now().isoformat()
                })
                
            elif response.status_code == 429:
                # Rate limit hit!
                data = response.json()
                detail = data.get('detail', 'Unknown error')
                
                print(f"   🛑 Status: 429 Too Many Requests")
                print(f"   💬 Message: {detail}")
                
                limit_hit = True
                limit_hit_at = attempt
                
                print("\n" + "="*70)
                print("  🎯 DAILY LIMIT ENFORCEMENT DETECTED!")
                print("="*70)
                break
                
            elif response.status_code == 404:
                # Email not found
                print(f"   ❌ Status: 404 Not Found")
                print(f"   💬 Email address not registered: {email}")
                print("\n❌ Test failed: User does not exist")
                print("   Register the user first with: POST /auth/register")
                return False
                
            elif response.status_code == 400:
                # Account not activated
                data = response.json()
                detail = data.get('detail', 'Unknown error')
                print(f"   ❌ Status: 400 Bad Request")
                print(f"   💬 Message: {detail}")
                print("\n❌ Test failed: Account not activated")
                print("   Activate the account first")
                return False
                
            else:
                # Unexpected status
                print(f"   ⚠️  Status: {response.status_code}")
                print(f"   💬 Response: {response.text[:200]}")
                
        except requests.exceptions.RequestException as e:
            print(f"   ❌ Request Error: {str(e)}")
            print("\n❌ Test failed: Cannot connect to API")
            print(f"   Check that the API is running at: {BASE_URL}")
            return False
            
        except Exception as e:
            print(f"   ❌ Unexpected Error: {str(e)}")
        
        # Small delay between attempts
        if attempt < max_attempts and not limit_hit:
            time.sleep(0.3)
    
    # Print summary
    print("\n" + "="*70)
    print("  TEST SUMMARY")
    print("="*70)
    
    print(f"\nTotal Attempts: {max_attempts if not limit_hit else limit_hit_at}")
    print(f"Successful Resets: {len(successful_resets)}")
    print(f"Limit Hit: {'Yes ✅' if limit_hit else 'No ❌'}")
    
    if limit_hit:
        print(f"Limit Hit At: Attempt #{limit_hit_at}")
        print(f"Daily Limit: {len(successful_resets)} reset(s) per day")
    
    if successful_resets:
        print(f"\n📋 Successful Resets:")
        for reset in successful_resets:
            print(f"   #{reset['attempt']}: {reset['api_key'][:30]}... at {reset['timestamp']}")
    
    print("\n" + "-"*70)
    
    # Evaluation
    if limit_hit:
        print("\n✅ TEST PASSED: Daily limit enforcement is working!")
        print(f"   The system correctly blocked reset attempt #{limit_hit_at}")
        print(f"   Daily limit appears to be: {len(successful_resets)} reset(s)")
        
        if len(successful_resets) == 1:
            print("\n💡 Recommendation: Limit is set to 1 (recommended for production)")
        elif len(successful_resets) <= 3:
            print("\n💡 Recommendation: Limit is reasonable for production")
        else:
            print("\n⚠️  Warning: Limit seems high - consider reducing for security")
            
        return True
        
    else:
        print("\n⚠️  TEST INCONCLUSIVE: Did not hit daily limit")
        print(f"   Completed {len(successful_resets)} resets without hitting limit")
        print("\n   Possible reasons:")
        print("   1. Daily limit is set higher than test attempts")
        print("   2. Daily limit feature is not configured")
        print("   3. Database columns not added (key_reset_count, key_reset_date)")
        print("   4. Environment variable API_MAX_DAILY_KEY_RESETS not set")
        
        print("\n📝 To configure:")
        print("   1. Run migration: migration_key_reset_tracking.sql")
        print("   2. Set: API_MAX_DAILY_KEY_RESETS=1")
        print("   3. Restart application")
        
        return False

def check_api_health():
    """Check if API is accessible"""
    try:
        response = requests.get(f"{BASE_URL}/auth/", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API is accessible")
            print(f"   Version: {data.get('version', 'unknown')}")
            print(f"   Email configured: {data.get('email_configured', 'unknown')}")
            return True
        else:
            print(f"⚠️  API returned status: {response.status_code}")
            return True
    except Exception as e:
        print(f"❌ Cannot connect to API at {BASE_URL}")
        print(f"   Error: {str(e)}")
        return False

def check_database_columns(email):
    """Try to determine if reset tracking columns exist"""
    print("\n📊 Checking if reset tracking is configured...")
    
    # Try a reset to see if it works at all
    try:
        response = requests.post(
            f"{BASE_URL}/auth/key/reset",
            json={"email": email},
            timeout=10
        )
        
        if response.status_code in [200, 429]:
            print("✅ Reset endpoint is functional")
            if response.status_code == 429:
                print("✅ Daily limit is already active!")
            return True
        elif response.status_code == 404:
            print(f"⚠️  Email {email} not found - register first")
            return False
        elif response.status_code == 400:
            data = response.json()
            if 'not activated' in data.get('detail', '').lower():
                print(f"⚠️  Account {email} not activated - activate first")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ Error checking reset endpoint: {str(e)}")
        return False

def main():
    """Main test function"""
    
    print("\n" + "█"*70)
    print("  KEY RESET DAILY LIMIT TEST")
    print("█"*70)
    
    # Get email from command line or prompt
    if len(sys.argv) > 1:
        email = sys.argv[1]
    else:
        email = input("\nEnter email address to test: ").strip()
    
    if not email or '@' not in email:
        print("❌ Invalid email address")
        print("\nUsage: python test_key_reset_limit.py [email]")
        print("Example: python test_key_reset_limit.py test@example.com")
        return 1
    
    print(f"\nTesting with: {email}")
    print(f"API URL: {BASE_URL}")
    
    # Check API is accessible
    print_section("Pre-flight Checks")
    if not check_api_health():
        print("\n❌ Cannot proceed - API not accessible")
        print("   Make sure your API is running:")
        print("   uvicorn app:app --reload")
        return 1
    
    if not check_database_columns(email):
        print("\n❌ Cannot proceed - account issues")
        print("   Make sure the account exists and is activated")
        return 1
    
    # Get max attempts
    print("\n" + "-"*70)
    max_attempts_input = input("Maximum reset attempts to try (default: 5, max: 20): ").strip()
    
    if max_attempts_input:
        try:
            max_attempts = int(max_attempts_input)
            if max_attempts < 1 or max_attempts > 20:
                print("⚠️  Using default: 5 attempts")
                max_attempts = 5
        except ValueError:
            print("⚠️  Invalid input, using default: 5 attempts")
            max_attempts = 5
    else:
        max_attempts = 5
    
    # Run the test
    success = test_key_reset_limit(email, max_attempts)
    
    # Final notes
    print("\n" + "="*70)
    print("  ADDITIONAL INFORMATION")
    print("="*70)
    
    print("\n📝 Notes:")
    print("   - The daily limit resets at midnight")
    print("   - Each successful reset invalidates the previous API key")
    print("   - The limit is tracked per user account")
    print("   - Default limit: 1 reset per day (configurable)")
    
    print("\n🔧 Configuration:")
    print("   Environment variable: API_MAX_DAILY_KEY_RESETS")
    print("   Database columns: key_reset_count, key_reset_date")
    print("   Migration: migration_key_reset_tracking.sql")
    
    print("\n📚 Documentation:")
    print("   - KEY_RESET_LIMIT_SETUP.md")
    print("   - NEW_FEATURES_v2.1.0.md")
    
    print("\n" + "="*70)
    
    if success:
        print("\n🎉 Test completed successfully!")
        return 0
    else:
        print("\n⚠️  Test completed with issues")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
