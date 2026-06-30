#!/usr/bin/env bash
# ============================================================
# Step 3: Create Test Users
#
# This script creates two test users in your Azure tenant:
#   - reader@<your-domain>  — will be assigned to api-readers
#   - writer@<your-domain>  — will be assigned to api-writers
#
# The tenant domain is auto-detected from your Azure account.
# Users are created with a temporary password and forced to
# change it on first sign-in.
#
# Prerequisites:
#   - Azure CLI installed and logged in
#   - User Administrator or Global Admin role
#
# Usage:
#   ./setup/03_create_users.sh
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

require_cmd az
require_az_login

step "Step 3: Create Test Users"

# ── 3.1 Auto-detect tenant domain ────────────────────────────
info "Detecting tenant domain..."

TENANT_DOMAIN=$(get_tenant_domain)

if [[ -z "$TENANT_DOMAIN" ]]; then
    warn "Could not auto-detect tenant domain."
    echo ""
    read -p "  Enter your Azure tenant domain (e.g., yourdomain.onmicrosoft.com): " TENANT_DOMAIN
    if [[ -z "$TENANT_DOMAIN" ]]; then
        fail "Tenant domain is required to create users."
    fi
fi

ok "Tenant domain: $TENANT_DOMAIN"
echo "$TENANT_DOMAIN" > "$SCRIPT_DIR/.tenant_domain"

READER_UPN="${READER_USERNAME}@${TENANT_DOMAIN}"
WRITER_UPN="${WRITER_USERNAME}@${TENANT_DOMAIN}"

# ── 3.2 Create reader user ───────────────────────────────────
info "Creating user '$READER_UPN'..."

EXISTING_READER=$(az ad user list \
    --filter "userPrincipalName eq '$READER_UPN'" \
    --query "[0].id" \
    --output tsv 2>/dev/null || echo "")

if [[ -n "$EXISTING_READER" && "$EXISTING_READER" != "None" ]]; then
    warn "User '$READER_UPN' already exists (Object ID: $EXISTING_READER)"
    READER_USER_ID="$EXISTING_READER"
else
    READER_USER_ID=$(az ad user create \
        --display-name "$READER_DISPLAY_NAME" \
        --user-principal-name "$READER_UPN" \
        --password "$TEMP_PASSWORD" \
        --force-change-password-next-sign-in true \
        --query id \
        --output tsv)
    ok "Created user '$READER_UPN'"
fi

echo "$READER_USER_ID" > "$SCRIPT_DIR/.reader_user_id"
ok "  Object ID: $READER_USER_ID"

# ── 3.3 Create writer user ───────────────────────────────────
info "Creating user '$WRITER_UPN'..."

EXISTING_WRITER=$(az ad user list \
    --filter "userPrincipalName eq '$WRITER_UPN'" \
    --query "[0].id" \
    --output tsv 2>/dev/null || echo "")

if [[ -n "$EXISTING_WRITER" && "$EXISTING_WRITER" != "None" ]]; then
    warn "User '$WRITER_UPN' already exists (Object ID: $EXISTING_WRITER)"
    WRITER_USER_ID="$EXISTING_WRITER"
else
    WRITER_USER_ID=$(az ad user create \
        --display-name "$WRITER_DISPLAY_NAME" \
        --user-principal-name "$WRITER_UPN" \
        --password "$TEMP_PASSWORD" \
        --force-change-password-next-sign-in true \
        --query id \
        --output tsv)
    ok "Created user '$WRITER_UPN'"
fi

echo "$WRITER_USER_ID" > "$SCRIPT_DIR/.writer_user_id"
ok "  Object ID: $WRITER_USER_ID"

# ── Summary ───────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${GREEN}  ✓ Test Users Created${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${BOLD}Reader:${NC} $READER_UPN (ID: $READER_USER_ID)"
echo -e "  ${BOLD}Writer:${NC} $WRITER_UPN (ID: $WRITER_USER_ID)"
echo ""
echo -e "  ${YELLOW}⚠ Temporary password for both users:${NC} $TEMP_PASSWORD"
echo -e "  ${YELLOW}  Users must change this on first sign-in.${NC}"
echo -e "  ${YELLOW}  They may need to visit https://myaccount.microsoft.com first.${NC}"
echo ""
