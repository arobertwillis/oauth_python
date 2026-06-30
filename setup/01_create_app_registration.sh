#!/usr/bin/env bash
# ============================================================
# Step 1: Create the App Registration
#
# This script:
#   1. Creates an app registration in Microsoft Entra ID
#   2. Creates the matching service principal (enterprise app)
#   3. Sets the access token version to v2
#   4. Enables security group claims in tokens
#   5. Configures a SPA redirect URI (for PKCE, no client secret)
#   6. Exposes an API scope (access_as_user)
#   7. Grants API permission and admin consent
#
# Prerequisites:
#   - Azure CLI installed and logged in (az login)
#   - Sufficient permissions (Application Administrator or Global Admin)
#
# Usage:
#   ./setup/01_create_app_registration.sh
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

require_cmd az
require_cmd jq
require_cmd uuidgen
require_az_login

step "Step 1: Create App Registration"

# ── 1.1 Check if app already exists ────────────────────────────
info "Checking if app registration '$APP_NAME' already exists..."

EXISTING_APP_ID=$(az ad app list \
    --display-name "$APP_NAME" \
    --query "[0].appId" \
    --output tsv 2>/dev/null || echo "")

if [[ -n "$EXISTING_APP_ID" && "$EXISTING_APP_ID" != "None" ]]; then
    warn "App registration '$APP_NAME' already exists (Client ID: $EXISTING_APP_ID)"
    echo ""
    read -p "  Do you want to delete it and recreate? (y/N): " RECREATE
    if [[ "$RECREATE" =~ ^[Yy]$ ]]; then
        info "Deleting existing app registration..."
        APP_OBJECT_ID=$(az ad app list --display-name "$APP_NAME" --query "[0].id" --output tsv)
        az ad app delete --id "$APP_OBJECT_ID"
        ok "Deleted existing app registration"
        sleep 2  # Wait for Azure to process the deletion
    else
        info "Keeping existing app registration. Skipping creation."
        echo "$EXISTING_APP_ID" > "$SCRIPT_DIR/.app_client_id"
        APP_OBJECT_ID=$(az ad app list --display-name "$APP_NAME" --query "[0].id" --output tsv)
        echo "$APP_OBJECT_ID" > "$SCRIPT_DIR/.app_object_id"
        exit 0
    fi
fi

# ── 1.2 Create the app registration ───────────────────────────
info "Creating app registration '$APP_NAME'..."

# Create the app with minimal config first — we'll configure it
# via the Graph API in subsequent steps, since the Azure CLI
# doesn't support all the settings we need (SPA redirects,
# groupMembershipClaims, oauth2PermissionScopes).
APP_OBJECT_ID=$(az ad app create \
    --display-name "$APP_NAME" \
    --sign-in-audience AzureADMyOrg \
    --query id \
    --output tsv)

CLIENT_ID=$(az ad app show --id "$APP_OBJECT_ID" --query appId --output tsv)

ok "Created app registration"
ok "  Application (client) ID: $CLIENT_ID"
ok "  Object ID:               $APP_OBJECT_ID"

# Save IDs for other scripts to use
echo "$CLIENT_ID" > "$SCRIPT_DIR/.app_client_id"
echo "$APP_OBJECT_ID" > "$SCRIPT_DIR/.app_object_id"

# ── 1.3 Create the Service Principal (Enterprise Application) ──
info "Creating service principal (enterprise application)..."

SP_OBJECT_ID=$(az ad sp create --id "$CLIENT_ID" --query id --output tsv 2>/dev/null || true)

if [[ -z "$SP_OBJECT_ID" || "$SP_OBJECT_ID" == "None" ]]; then
    # Service principal may already exist
    SP_OBJECT_ID=$(az ad sp list --filter "appId eq '$CLIENT_ID'" --query "[0].id" --output tsv)
fi

echo "$SP_OBJECT_ID" > "$SCRIPT_DIR/.sp_object_id"
ok "Service principal Object ID: $SP_OBJECT_ID"

# ── 1.4 Generate UUIDs for scopes and roles ───────────────────
SCOPE_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
echo "$SCOPE_ID" > "$SCRIPT_DIR/.scope_id"

ROLE_READ_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
ROLE_WRITE_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
echo "$ROLE_READ_ID" > "$SCRIPT_DIR/.role_read_id"
echo "$ROLE_WRITE_ID" > "$SCRIPT_DIR/.role_write_id"

# ── 1.5 Configure the app via Microsoft Graph API ─────────────
# We use a single PATCH call to set everything at once:
#   - SPA redirect URI (NOT web — required for PKCE without client secret)
#   - accessTokenAcceptedVersion: 2 (modern v2 token format)
#   - groupMembershipClaims: SecurityGroup (include groups in JWT)
#   - identifierUris: api://<client-id> (Application ID URI)
#   - oauth2PermissionScopes: the access_as_user scope
#   - appRoles: the Service-to-Service roles (Read/Write)

info "Configuring app registration via Microsoft Graph API..."
info "  → Setting SPA redirect URI (PKCE-compatible)"
info "  → Setting token version to v2"
info "  → Enabling security group claims in tokens"
info "  → Setting Application ID URI"
info "  → Creating 'access_as_user' API scope"
info "  → Creating App Roles for Service Principals"

az rest --method PATCH \
    --url "https://graph.microsoft.com/v1.0/applications/$APP_OBJECT_ID" \
    --headers "Content-Type=application/json" \
    --body "{
        \"spa\": {
            \"redirectUris\": [\"$REDIRECT_URI\"]
        },
        \"api\": {
            \"requestedAccessTokenVersion\": 2,
            \"oauth2PermissionScopes\": [
                {
                    \"adminConsentDescription\": \"Allows the user to access the OAuth Python API\",
                    \"adminConsentDisplayName\": \"Access OAuth Python API\",
                    \"id\": \"$SCOPE_ID\",
                    \"isEnabled\": true,
                    \"type\": \"User\",
                    \"userConsentDescription\": \"Allows you to access the OAuth Python API\",
                    \"userConsentDisplayName\": \"Access OAuth Python API\",
                    \"value\": \"access_as_user\"
                }
            ]
        },
        \"appRoles\": [
            {
                \"allowedMemberTypes\": [\"Application\"],
                \"description\": \"$ROLE_READ_ALL_DESC\",
                \"displayName\": \"$ROLE_READ_ALL_DESC\",
                \"id\": \"$ROLE_READ_ID\",
                \"isEnabled\": true,
                \"origin\": \"Application\",
                \"value\": \"$ROLE_READ_ALL\"
            },
            {
                \"allowedMemberTypes\": [\"Application\"],
                \"description\": \"$ROLE_WRITE_ALL_DESC\",
                \"displayName\": \"$ROLE_WRITE_ALL_DESC\",
                \"id\": \"$ROLE_WRITE_ID\",
                \"isEnabled\": true,
                \"origin\": \"Application\",
                \"value\": \"$ROLE_WRITE_ALL\"
            }
        ],
        \"identifierUris\": [\"api://$CLIENT_ID\"],
        \"groupMembershipClaims\": \"SecurityGroup\"
    }" \
    --output none

ok "App registration configured successfully"

# ── 1.6 Add API permission (app grants itself the scope) ──────
info "Adding API permission (self-referencing scope)..."

# The app needs to list its own scope as a required resource access
# so that users can consent to it.
az rest --method PATCH \
    --url "https://graph.microsoft.com/v1.0/applications/$APP_OBJECT_ID" \
    --headers "Content-Type=application/json" \
    --body "{
        \"requiredResourceAccess\": [
            {
                \"resourceAppId\": \"$CLIENT_ID\",
                \"resourceAccess\": [
                    {
                        \"id\": \"$SCOPE_ID\",
                        \"type\": \"Scope\"
                    }
                ]
            }
        ]
    }" \
    --output none

ok "API permission added"

# ── 1.7 Grant admin consent ───────────────────────────────────
info "Granting admin consent for the API permission..."
info "  (This may take a moment to propagate...)"

# Wait a moment for the permission to propagate
sleep 5

# Grant admin consent using az ad app permission
az ad app permission admin-consent --id "$CLIENT_ID" 2>/dev/null || {
    warn "Auto admin consent failed. You may need to grant consent manually:"
    warn "  Azure Portal → App registrations → $APP_NAME → API permissions → Grant admin consent"
}

ok "Admin consent granted (or attempted)"

# ── Summary ───────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${GREEN}  ✓ App Registration Complete${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${BOLD}Application (Client) ID:${NC} $CLIENT_ID"
echo -e "  ${BOLD}Object ID:${NC}              $APP_OBJECT_ID"
echo -e "  ${BOLD}Service Principal ID:${NC}   $SP_OBJECT_ID"
echo -e "  ${BOLD}API Scope:${NC}              api://$CLIENT_ID/access_as_user"
echo -e "  ${BOLD}Redirect URI:${NC}           $REDIRECT_URI"
echo -e "  ${BOLD}Token Version:${NC}          v2"
echo -e "  ${BOLD}Group Claims:${NC}           SecurityGroup"
echo ""
