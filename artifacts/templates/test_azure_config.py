"""
Azure AD Configuration Diagnostic Tool
Tests Microsoft Graph API authentication configuration

This script will help identify configuration issues with:
- Tenant ID
- Client ID  
- Client Secret
- API Permissions

Run this to get detailed error information about your Azure AD setup.
"""

import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_azure_ad_auth():
    """Test Azure AD authentication and diagnose issues"""
    
    print("="*70)
    print("  AZURE AD AUTHENTICATION DIAGNOSTIC TOOL")
    print("="*70)
    print()
    
    # Step 1: Check environment variables
    print("Step 1: Checking environment variables...")
    print("-"*70)
    
    tenant_id = os.getenv("API_AZURE_TENANT_ID")
    client_id = os.getenv("API_AZURE_CLIENT_ID")
    client_secret = os.getenv("API_AZURE_CLIENT_SECRET")
    from_address = os.getenv("API_EMAIL_FROM_ADDRESS")
    
    print("tenant_id:" + tenant_id)
    print("client_id:" + client_id)
    print("client_secret:" + client_secret)
    print("from_address:" + from_address)
    
    config_ok = True
    
    if tenant_id:
        print(f"✓ API_AZURE_TENANT_ID: {tenant_id[:8]}...{tenant_id[-4:]}")
    else:
        print("✗ API_AZURE_TENANT_ID: NOT SET")
        config_ok = False
    
    if client_id:
        print(f"✓ API_AZURE_CLIENT_ID: {client_id[:8]}...{client_id[-4:]}")
    else:
        print("✗ API_AZURE_CLIENT_ID: NOT SET")
        config_ok = False
    
    if client_secret:
        print(f"✓ API_AZURE_CLIENT_SECRET: {client_secret[:4]}...{client_secret[-4:]} (length: {len(client_secret)})")
    else:
        print("✗ API_AZURE_CLIENT_SECRET: NOT SET")
        config_ok = False
    
    if from_address:
        print(f"✓ API_EMAIL_FROM_ADDRESS: {from_address}")
    else:
        print("✗ API_EMAIL_FROM_ADDRESS: NOT SET")
        config_ok = False
    
    print()
    
    if not config_ok:
        print("❌ CONFIGURATION INCOMPLETE")
        print("   Please set all required environment variables.")
        return False
    
    print("✓ All environment variables are set")
    print()
    
    # Step 2: Test authentication
    print("Step 2: Testing Microsoft Graph API authentication...")
    print("-"*70)
    
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    
    print(f"Token endpoint: {token_url}")
    print()
    
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials"
    }
    
    try:
        print("Requesting access token...")
        response = requests.post(token_url, data=data, timeout=10)
        
        print(f"Response Status: {response.status_code}")
        print()
        
        if response.status_code == 200:
            print("✓ AUTHENTICATION SUCCESSFUL!")
            print()
            
            token_data = response.json()
            access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 0)
            
            print(f"Access Token (first 50 chars): {access_token[:50]}...")
            print(f"Token Type: {token_data.get('token_type', 'N/A')}")
            print(f"Expires In: {expires_in} seconds ({expires_in/60:.1f} minutes)")
            print()
            
            # Test if token has required permissions
            print("Step 3: Checking token permissions...")
            print("-"*70)
            
            # Try to access Graph API with the token
            graph_url = f"https://graph.microsoft.com/v1.0/users/{from_address}"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            print(f"Testing access to: {graph_url}")
            user_response = requests.get(graph_url, headers=headers, timeout=10)
            
            print(f"Response Status: {user_response.status_code}")
            print()
            
            if user_response.status_code == 200:
                print("✓ Successfully accessed user information")
                user_data = user_response.json()
                print(f"  User Principal Name: {user_data.get('userPrincipalName')}")
                print(f"  Display Name: {user_data.get('displayName')}")
                print()
                print("✓ ALL TESTS PASSED!")
                print("  Your Azure AD configuration is correct and ready to send emails.")
            else:
                print("⚠ Could not access user information")
                print(f"  Status: {user_response.status_code}")
                try:
                    error = user_response.json()
                    print(f"  Error: {error.get('error', {}).get('message', 'Unknown error')}")
                except:
                    print(f"  Response: {user_response.text}")
                print()
                print("  This might mean:")
                print("  - The Mail.Send permission needs admin consent")
                print("  - The FROM_ADDRESS doesn't exist in your Microsoft 365")
            
            return True
            
        else:
            print("❌ AUTHENTICATION FAILED")
            print()
            
            try:
                error_data = response.json()
                error_code = error_data.get('error', 'unknown')
                error_desc = error_data.get('error_description', 'No description')
                
                print(f"Error Code: {error_code}")
                print()
                print("Error Description:")
                print(error_desc)
                print()
                
                # Provide specific troubleshooting
                print("="*70)
                print("TROUBLESHOOTING:")
                print("="*70)
                
                if 'AADSTS7000215' in error_desc:
                    print()
                    print("❌ INVALID CLIENT SECRET")
                    print()
                    print("Solution:")
                    print("1. Go to Azure Portal > App Registrations")
                    print("2. Select your app")
                    print("3. Go to 'Certificates & secrets'")
                    print("4. Delete the old secret")
                    print("5. Create a new client secret")
                    print("6. Copy the VALUE (not the Secret ID)")
                    print("7. Update API_AZURE_CLIENT_SECRET in your .env file")
                    print()
                
                elif 'AADSTS700016' in error_desc:
                    print()
                    print("❌ INVALID CLIENT ID")
                    print()
                    print("Solution:")
                    print("1. Go to Azure Portal > App Registrations")
                    print("2. Select your app")
                    print("3. Copy the 'Application (client) ID' from Overview")
                    print("4. Update API_AZURE_CLIENT_ID in your .env file")
                    print()
                
                elif 'AADSTS90002' in error_desc:
                    print()
                    print("❌ INVALID TENANT ID")
                    print()
                    print("Solution:")
                    print("1. Go to Azure Portal > Azure Active Directory")
                    print("2. Copy the 'Tenant ID' from Overview")
                    print("3. Update API_AZURE_TENANT_ID in your .env file")
                    print()
                
                elif 'unauthorized_client' in error_code:
                    print()
                    print("❌ MISSING API PERMISSIONS OR ADMIN CONSENT")
                    print()
                    print("Solution:")
                    print("1. Go to Azure Portal > App Registrations")
                    print("2. Select your app")
                    print("3. Go to 'API permissions'")
                    print("4. Click 'Add a permission'")
                    print("5. Select 'Microsoft Graph'")
                    print("6. Select 'Application permissions'")
                    print("7. Find and add 'Mail.Send'")
                    print("8. Click 'Grant admin consent for [Your Organization]'")
                    print("9. Wait a few minutes for changes to propagate")
                    print()
                
                else:
                    print()
                    print("General troubleshooting steps:")
                    print("1. Verify all credentials in Azure Portal")
                    print("2. Ensure client secret hasn't expired")
                    print("3. Check that Mail.Send permission has admin consent")
                    print("4. Try creating a new client secret")
                    print()
                
            except Exception as e:
                print("Could not parse error response:")
                print(response.text)
                print()
            
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ REQUEST FAILED: {str(e)}")
        print()
        print("This usually means:")
        print("- Network connectivity issues")
        print("- Invalid tenant ID (check the URL)")
        print("- Firewall blocking Azure AD endpoints")
        return False


if __name__ == "__main__":
    try:
        test_azure_ad_auth()
    except KeyboardInterrupt:
        print("\nTest cancelled by user")
    except Exception as e:
        print(f"\nUnexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
