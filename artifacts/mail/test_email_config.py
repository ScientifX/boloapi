# Create test file
import os
import sys

# Show which email_utils.py is being loaded
import email_utils
print("="*70)
print(f"Loading email_utils from: {email_utils.__file__}")
print("="*70)

# Simulate how your app loads config
try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

# Now test EmailConfig
from email_utils import EmailConfig

print("What EmailConfig actually returns:")
print("="*70)
print(f"TENANT_ID: {EmailConfig.TENANT_ID}")
print(f"CLIENT_ID: {EmailConfig.CLIENT_ID}")
print(f"CLIENT_SECRET: {EmailConfig.CLIENT_SECRET[:10]}..." if EmailConfig.CLIENT_SECRET else "None")
print(f"FROM_ADDRESS: {EmailConfig.FROM_ADDRESS}")
print("="*70)

# Check if swapped
if EmailConfig.CLIENT_ID and '~' in str(EmailConfig.CLIENT_ID):
    print("❌ ERROR: CLIENT_ID contains '~' - this is the SECRET!")
    print(f"   Full CLIENT_ID value: {EmailConfig.CLIENT_ID}")
elif EmailConfig.CLIENT_SECRET and len(str(EmailConfig.CLIENT_SECRET)) == 36 and str(EmailConfig.CLIENT_SECRET).count('-') == 4:
    print("❌ ERROR: CLIENT_SECRET looks like a GUID - this is the ID!")  
    print(f"   Full CLIENT_SECRET value: {EmailConfig.CLIENT_SECRET}")