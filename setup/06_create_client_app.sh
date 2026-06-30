#!/usr/bin/env bash
# ============================================================
# Step 6: Create Client App for Service-to-Service Auth
#
# This script creates a second App Registration representing an
# automated background script or daemon. It then grants this
# client application the App Roles (Application Permissions) 
# required to access the main API.
#
# Prerequisites:
#   - Azure CLI installed and logged in
#   - Steps 1-5 completed (main API app created)
#
# Usage:
#   ./setup/06_create_client_app.sh
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

require_cmd az
require_az_login

step "Step 6: Create Client App for Service-to-Service Auth"

# Load API app info
API_CLIENT_ID=$(cat "$SCRIPT_DIR/.app_client_id")
API_SP_OBJECT_ID=$(cat "$SCRIPT_DIR/.sp_object_id")
ROLE_READ_ID=$(cat "$SCRIPT_DIR/.role_read_id")
ROLE_WRITE_ID=$(cat "$SCRIPT_DIR/.role_write_id")

# ── 6.1 Create Client App Registration ────────────────────────
info "Creating Client App Registration '$CLIENT_APP_NAME'..."

EXISTING_APP_ID=$(az ad app list --display-name "$CLIENT_APP_NAME" --query "[0].appId" --output tsv 2>/dev/null || echo "")

if [[ -n "$EXISTING_APP_ID" && "$EXISTING_APP_ID" != "None" ]]; then
    warn "Client App '$CLIENT_APP_NAME' already exists (Client ID: $EXISTING_APP_ID)"
    CLIENT_APP_OBJECT_ID=$(az ad app list --display-name "$CLIENT_APP_NAME" --query "[0].id" --output tsv)
else
    CLIENT_APP_OBJECT_ID=$(az ad app create \
        --display-name "$CLIENT_APP_NAME" \
        --sign-in-audience AzureADMyOrg \
        --query id \
        --output tsv)
    EXISTING_APP_ID=$(az ad app show --id "$CLIENT_APP_OBJECT_ID" --query appId --output tsv)
    ok "Created Client App Registration"
fi

echo "$EXISTING_APP_ID" > "$SCRIPT_DIR/.client_app_client_id"
echo "$CLIENT_APP_OBJECT_ID" > "$SCRIPT_DIR/.client_app_object_id"

ok "  Client ID: $EXISTING_APP_ID"
ok "  Object ID: $CLIENT_APP_OBJECT_ID"

# ── 6.2 Create Client Service Principal ───────────────────────
info "Creating Client Service Principal..."

CLIENT_SP_OBJECT_ID=$(az ad sp create --id "$EXISTING_APP_ID" --query id --output tsv 2>/dev/null || true)

if [[ -z "$CLIENT_SP_OBJECT_ID" || "$CLIENT_SP_OBJECT_ID" == "None" ]]; then
    CLIENT_SP_OBJECT_ID=$(az ad sp list --filter "appId eq '$EXISTING_APP_ID'" --query "[0].id" --output tsv)
fi

echo "$CLIENT_SP_OBJECT_ID" > "$SCRIPT_DIR/.client_sp_object_id"
ok "  Service Principal ID: $CLIENT_SP_OBJECT_ID"

# ── 6.3 Generate Client Secret ────────────────────────────────
  # We no longer generate a secret here; it is handled by 07_configure_certificates.sh

# ── 6.4 Grant App Roles to the Client ─────────────────────────
info "Granting App Roles (Application Permissions) to the Client..."

# We use Microsoft Graph to create an appRoleAssignment
# granting the Client Service Principal access to the API Service Principal
# for the Items.Write.All role.

info "  → Assigning '$ROLE_WRITE_ALL' role..."

az rest --method POST \
    --url "https://graph.microsoft.com/v1.0/servicePrincipals/$CLIENT_SP_OBJECT_ID/appRoleAssignments" \
    --headers "Content-Type=application/json" \
    --body "{
        \"principalId\": \"$CLIENT_SP_OBJECT_ID\",
        \"resourceId\": \"$API_SP_OBJECT_ID\",
        \"appRoleId\": \"$ROLE_WRITE_ID\"
    }" \
    --output none 2>/dev/null || {
    warn "Role assignment may already exist (this is OK)"
}
ok "  Role assigned."

# ── Summary ───────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${GREEN}  ✓ Client App Created & Configured${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${BOLD}Client App ID:${NC}     $EXISTING_APP_ID"
echo -e "  ${BOLD}Granted Role:${NC}      $ROLE_WRITE_ALL"
echo ""
