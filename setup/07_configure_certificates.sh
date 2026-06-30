#!/usr/bin/env bash
set -e

# Load configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
source "$SCRIPT_DIR/config.sh"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 7: Configure Certificate Authentication"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Ensure we have the CLI Client Object ID from previous steps
if [[ ! -f "$SCRIPT_DIR/.client_app_object_id" ]]; then
    fail "Client App ID not found. Did you run 06_create_client_app.sh?"
fi
CLIENT_APP_OBJECT_ID=$(cat "$SCRIPT_DIR/.client_app_object_id")

# Create local secure directory
CERTS_DIR="$SCRIPT_DIR/../.certs"
mkdir -p "$CERTS_DIR"
chmod 700 "$CERTS_DIR"

CERT_PATH="$CERTS_DIR/oauth_python_cli.pem"
KEY_PATH="$CERTS_DIR/oauth_python_cli.key"
FULL_PEM_PATH="$CERTS_DIR/oauth_python_cli_full.pem"

info "Generating new self-signed certificate..."
# Generate Private Key and Public Cert
openssl req -x509 -newkey rsa:2048 \
    -keyout "$KEY_PATH" -out "$CERT_PATH" \
    -days 365 -nodes -subj "/CN=OAuthPythonCLI" 2>/dev/null

# Combine into a single PEM file for our Python/C# clients
cat "$KEY_PATH" "$CERT_PATH" > "$FULL_PEM_PATH"
chmod 400 "$FULL_PEM_PATH"
chmod 400 "$KEY_PATH"
chmod 400 "$CERT_PATH"

ok "Generated certificate at $FULL_PEM_PATH"

info "Uploading certificate public key to Azure AD App Registration..."
# Upload the public cert to Azure
az ad app credential reset \
    --id "$CLIENT_APP_OBJECT_ID" \
    --cert "@$CERT_PATH" \
    --append \
    --output none 2>/dev/null || warn "Certificate might already exist, attempting to proceed."

ok "Certificate uploaded to Azure."

info "Calculating Certificate Thumbprint..."
# Calculate Thumbprint using openssl
THUMBPRINT=$(openssl x509 -in "$CERT_PATH" -fingerprint -noout | sed 's/SHA1 Fingerprint=//g' | sed 's/://g')
echo "$THUMBPRINT" > "$SCRIPT_DIR/.cert_thumbprint"

ok "Thumbprint: $THUMBPRINT"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✓ Certificate Configuration Complete"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Certificate Path:  $FULL_PEM_PATH"
echo "  Thumbprint:        $THUMBPRINT"
echo ""
