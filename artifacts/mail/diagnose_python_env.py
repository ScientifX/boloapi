"""
Check what Python actually sees for environment variables
This will show if there's a mismatch between Windows env vars and what Python loads
"""

import os
import sys

print("="*70)
print("  PYTHON ENVIRONMENT VARIABLE CHECK")
print("="*70)

# First, check if .env file exists
print("\n1. Checking for .env file...")
print("-"*70)
if os.path.exists('.env'):
    print("⚠️  WARNING: .env file EXISTS in current directory!")
    print("   This file may be overriding your Windows environment variables")
    print("\n   Contents of .env file:")
    with open('.env', 'r') as f:
        for line in f:
            if 'AZURE' in line or 'EMAIL' in line:
                print(f"   {line.rstrip()}")
else:
    print("✅ No .env file found")

# Now load like the app does
print("\n2. Loading environment variables like your app does...")
print("-"*70)

# Simulate what config.py does
try:
    from dotenv import load_dotenv
    load_dotenv()  # This is what config.py does
    print("✅ load_dotenv() executed (found python-dotenv)")
except ImportError:
    print("ℹ️  python-dotenv not installed - using only Windows env vars")

# Now check what Python sees
print("\n3. What Python sees AFTER load_dotenv():")
print("-"*70)

client_id = os.getenv("API_AZURE_CLIENT_ID")
client_secret = os.getenv("API_AZURE_CLIENT_SECRET")
tenant_id = os.getenv("API_AZURE_TENANT_ID")

print(f"API_AZURE_CLIENT_ID:     {client_id}")
print(f"API_AZURE_CLIENT_SECRET: {client_secret[:10]}...{client_secret[-4:] if client_secret else 'None'}")
print(f"API_AZURE_TENANT_ID:     {tenant_id}")

print("\n4. Validation:")
print("-"*70)

# Check CLIENT_ID format (should be GUID)
if client_id and len(client_id) == 36 and client_id.count('-') == 4:
    print("✅ CLIENT_ID looks correct (GUID format)")
else:
    print("❌ CLIENT_ID format is WRONG!")
    if client_id and '~' in client_id:
        print("   🚨 CLIENT_ID contains '~' - this looks like a SECRET, not an ID!")

# Check CLIENT_SECRET format (should have special chars)
if client_secret and len(client_secret) > 20:
    print("✅ CLIENT_SECRET looks correct (has length)")
    if client_secret.count('-') == 4 and len(client_secret) == 36:
        print("   ⚠️  WARNING: CLIENT_SECRET looks like a GUID - might be swapped!")
else:
    print("❌ CLIENT_SECRET format may be wrong")

# Check TENANT_ID format (should be GUID)
if tenant_id and len(tenant_id) == 36 and tenant_id.count('-') == 4:
    print("✅ TENANT_ID looks correct (GUID format)")
else:
    print("❌ TENANT_ID format is WRONG!")

print("\n5. Diagnosis:")
print("-"*70)

# Check if there's a mismatch
windows_client_id = "9a128d2a-63a6-402a-890b-3de25a37e660"
windows_client_secret_prefix = "YOj8Q~hKUmL8g574vwFL_6m1XTHau"

if client_id == windows_client_id:
    print("✅ Python CLIENT_ID matches Windows environment variable")
else:
    print("❌ Python CLIENT_ID DIFFERENT from Windows environment variable!")
    print(f"   Windows has: {windows_client_id}")
    print(f"   Python sees: {client_id}")
    print("\n   👉 Solution: Delete or fix the .env file")

if client_secret and client_secret.startswith(windows_client_secret_prefix):
    print("✅ Python CLIENT_SECRET matches Windows environment variable")
else:
    print("❌ Python CLIENT_SECRET DIFFERENT from Windows environment variable!")
    print(f"   Windows has: {windows_client_secret_prefix}...")
    print(f"   Python sees: {client_secret[:30] if client_secret else 'None'}...")
    print("\n   👉 Solution: Delete or fix the .env file")

print("="*70)
