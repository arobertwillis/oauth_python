import os
import sys

import msal
import requests
from dotenv import load_dotenv

# Load credentials from .env.calient (located at the repo root)
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_CLIENT_PATH = os.path.join(REPO_ROOT, ".env.client")

if not os.path.exists(ENV_CLIENT_PATH):
    print(f"Error: {ENV_CLIENT_PATH} not found.")
    print("Please run the setup scripts (setup/setup_all.sh) to generate it.")
    sys.exit(1)

load_dotenv(ENV_CLIENT_PATH)

TENANT_ID = os.environ["AZURE_TENANT_ID"]
CLIENT_ID = os.environ["CLIENT_ID"]
CERT_THUMBPRINT = os.environ.get("CERT_THUMBPRINT")
API_SCOPE = os.environ["API_SCOPE"]

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
API_BASE_URL = "http://localhost:8000/api"

print("=============================================")
print("  Python CLI Client (Service-to-Service)")
print("=============================================\n")

# Load private key from .certs/
CERT_PATH = os.path.join(REPO_ROOT, ".certs", "oauth_python_cli_full.pem")
if not os.path.exists(CERT_PATH):
    print(f"Error: {CERT_PATH} not found.")
    print("Please run the setup scripts (setup/07_configure_certificates.sh) to generate it.")
    sys.exit(1)

with open(CERT_PATH, "r") as f:
    private_key = f.read()

# 1. Initialize MSAL Confidential Client using a Certificate
app = msal.ConfidentialClientApplication(
    CLIENT_ID,
    authority=AUTHORITY,
    client_credential={
        "thumbprint": CERT_THUMBPRINT,
        "private_key": private_key
    }
)

# 2. Request a Token using the Client Credentials Flow
print("1. Requesting token from Azure AD...")

# The scope MUST be the Application ID URI of the API followed by /.default
# e.g., api://<api-client-id>/.default
# This tells Azure to grant whatever App Roles have been assigned to this Client.
result = app.acquire_token_for_client(scopes=[API_SCOPE])

if "access_token" not in result:
    print("❌ Failed to acquire token!")
    print(f"Error: {result.get('error')}")
    print(f"Description: {result.get('error_description')}")
    sys.exit(1)

access_token = result["access_token"]
print("✅ Token acquired successfully!\n")

# Prepare headers for the API requests
headers = {
    "Authorization": f"Bearer {access_token}"
}

# 3. Test the /api/items GET endpoint (Requires Read role)
print("2. Fetching items (GET /api/items)...")
response = requests.get(f"{API_BASE_URL}/items", headers=headers)
if response.status_code == 200:
    print(f"✅ Success: {response.json()}\n")
else:
    print(f"❌ Failed ({response.status_code}): {response.text}\n")

# 4. Test the /api/items POST endpoint (Requires Write role)
print("3. Creating an item (POST /api/items)...")
new_item = {
    "name": "Item from Python CLI",
    "description": "Created automatically via Client Credentials flow"
}
response = requests.post(f"{API_BASE_URL}/items", json=new_item, headers=headers)
if response.status_code == 200 or response.status_code == 201:
    print(f"✅ Success: {response.json()}\n")
else:
    print(f"❌ Failed ({response.status_code}): {response.text}\n")

print("Done!")
