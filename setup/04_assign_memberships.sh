#!/usr/bin/env bash
# ============================================================
# Step 4: Assign Users to Groups & Groups to Enterprise App
#
# This script:
#   1. Adds the reader user to the api-readers group
#   2. Adds the writer user to the api-writers group
#   3. Assigns both groups to the enterprise application
#      (so group claims appear in tokens)
#
# Prerequisites:
#   - Steps 1–3 completed (app, groups, users created)
#   - Azure CLI installed and logged in
#
# Usage:
#   ./setup/04_assign_memberships.sh
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

require_cmd az
require_az_login

step "Step 4: Assign Users to Groups & Enterprise App"

# ── Load IDs from previous steps ──────────────────────────────
load_id() {
    local file="$SCRIPT_DIR/$1"
    if [[ ! -f "$file" ]]; then
        fail "File '$file' not found. Did you run the previous steps?"
    fi
    cat "$file"
}

READER_GROUP_ID=$(load_id ".reader_group_id")
WRITER_GROUP_ID=$(load_id ".writer_group_id")
READER_USER_ID=$(load_id ".reader_user_id")
WRITER_USER_ID=$(load_id ".writer_user_id")
SP_OBJECT_ID=$(load_id ".sp_object_id")

info "Loaded IDs from previous steps"

# ── 4.1 Add reader user to api-readers group ──────────────────
info "Adding reader user to '$READER_GROUP_NAME' group..."

IS_READER_MEMBER=$(az ad group member check \
    --group "$READER_GROUP_ID" \
    --member-id "$READER_USER_ID" \
    --query value \
    --output tsv 2>/dev/null || echo "false")

if [[ "$IS_READER_MEMBER" == "true" ]]; then
    warn "Reader user is already a member of '$READER_GROUP_NAME'"
else
    az ad group member add \
        --group "$READER_GROUP_ID" \
        --member-id "$READER_USER_ID"
    ok "Added reader user to '$READER_GROUP_NAME'"
fi

# ── 4.2 Add writer user to api-writers group ──────────────────
info "Adding writer user to '$WRITER_GROUP_NAME' group..."

IS_WRITER_MEMBER=$(az ad group member check \
    --group "$WRITER_GROUP_ID" \
    --member-id "$WRITER_USER_ID" \
    --query value \
    --output tsv 2>/dev/null || echo "false")

if [[ "$IS_WRITER_MEMBER" == "true" ]]; then
    warn "Writer user is already a member of '$WRITER_GROUP_NAME'"
else
    az ad group member add \
        --group "$WRITER_GROUP_ID" \
        --member-id "$WRITER_USER_ID"
    ok "Added writer user to '$WRITER_GROUP_NAME'"
fi

# ── 4.3 Verify group memberships ─────────────────────────────
info "Verifying group memberships..."

READER_MEMBERS=$(az ad group member list \
    --group "$READER_GROUP_ID" \
    --query "[].displayName" \
    --output tsv 2>/dev/null)
ok "'$READER_GROUP_NAME' members: $READER_MEMBERS"

WRITER_MEMBERS=$(az ad group member list \
    --group "$WRITER_GROUP_ID" \
    --query "[].displayName" \
    --output tsv 2>/dev/null)
ok "'$WRITER_GROUP_NAME' members: $WRITER_MEMBERS"

# ── 4.4 Assign groups to the Enterprise Application ──────────
# This ensures that:
#   a) Only members of these groups can obtain tokens for this app
#   b) Group Object IDs appear in the JWT 'groups' claim
#
# We do this via the Microsoft Graph API using appRoleAssignments.
# Since we haven't defined custom app roles, we use the default
# app role (ID: 00000000-0000-0000-0000-000000000000).

info "Assigning groups to the enterprise application..."
info "  (This makes group claims appear in JWT tokens)"

DEFAULT_ROLE_ID="00000000-0000-0000-0000-000000000000"

# Assign api-readers group
info "Assigning '$READER_GROUP_NAME' to the enterprise app..."

az rest --method POST \
    --url "https://graph.microsoft.com/v1.0/servicePrincipals/$SP_OBJECT_ID/appRoleAssignments" \
    --headers "Content-Type=application/json" \
    --body "{
        \"principalId\": \"$READER_GROUP_ID\",
        \"resourceId\": \"$SP_OBJECT_ID\",
        \"appRoleId\": \"$DEFAULT_ROLE_ID\"
    }" \
    --output none 2>/dev/null || {
    warn "Reader group assignment may already exist (this is OK)"
}
ok "Assigned '$READER_GROUP_NAME' to enterprise app"

# Assign api-writers group
info "Assigning '$WRITER_GROUP_NAME' to the enterprise app..."

az rest --method POST \
    --url "https://graph.microsoft.com/v1.0/servicePrincipals/$SP_OBJECT_ID/appRoleAssignments" \
    --headers "Content-Type=application/json" \
    --body "{
        \"principalId\": \"$WRITER_GROUP_ID\",
        \"resourceId\": \"$SP_OBJECT_ID\",
        \"appRoleId\": \"$DEFAULT_ROLE_ID\"
    }" \
    --output none 2>/dev/null || {
    warn "Writer group assignment may already exist (this is OK)"
}
ok "Assigned '$WRITER_GROUP_NAME' to enterprise app"

# ── Summary ───────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${GREEN}  ✓ Memberships Assigned${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${BOLD}Reader user${NC} → $READER_GROUP_NAME"
echo -e "  ${BOLD}Writer user${NC} → $WRITER_GROUP_NAME"
echo -e "  ${BOLD}$READER_GROUP_NAME${NC} → Enterprise App"
echo -e "  ${BOLD}$WRITER_GROUP_NAME${NC} → Enterprise App"
echo ""
