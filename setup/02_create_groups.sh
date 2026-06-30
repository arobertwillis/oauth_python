#!/usr/bin/env bash
# ============================================================
# Step 2: Create Security Groups
#
# This script creates two security groups:
#   - api-readers: Users with read-only API access
#   - api-writers: Users with read + write API access
#
# Prerequisites:
#   - Azure CLI installed and logged in
#   - Groups Administrator or Global Admin role
#
# Usage:
#   ./setup/02_create_groups.sh
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

require_cmd az
require_az_login

step "Step 2: Create Security Groups"

# ── 2.1 Create api-readers group ──────────────────────────────
info "Creating security group '$READER_GROUP_NAME'..."

EXISTING_READER=$(az ad group list \
    --display-name "$READER_GROUP_NAME" \
    --query "[?displayName=='$READER_GROUP_NAME'].id" \
    --output tsv 2>/dev/null || echo "")

if [[ -n "$EXISTING_READER" ]]; then
    warn "Group '$READER_GROUP_NAME' already exists (Object ID: $EXISTING_READER)"
    READER_GROUP_ID="$EXISTING_READER"
else
    READER_GROUP_ID=$(az ad group create \
        --display-name "$READER_GROUP_NAME" \
        --mail-nickname "$READER_GROUP_NAME" \
        --description "$READER_GROUP_DESCRIPTION" \
        --query id \
        --output tsv)
    ok "Created group '$READER_GROUP_NAME'"
fi

echo "$READER_GROUP_ID" > "$SCRIPT_DIR/.reader_group_id"
ok "  Object ID: $READER_GROUP_ID"

# ── 2.2 Create api-writers group ──────────────────────────────
info "Creating security group '$WRITER_GROUP_NAME'..."

EXISTING_WRITER=$(az ad group list \
    --display-name "$WRITER_GROUP_NAME" \
    --query "[?displayName=='$WRITER_GROUP_NAME'].id" \
    --output tsv 2>/dev/null || echo "")

if [[ -n "$EXISTING_WRITER" ]]; then
    warn "Group '$WRITER_GROUP_NAME' already exists (Object ID: $EXISTING_WRITER)"
    WRITER_GROUP_ID="$EXISTING_WRITER"
else
    WRITER_GROUP_ID=$(az ad group create \
        --display-name "$WRITER_GROUP_NAME" \
        --mail-nickname "$WRITER_GROUP_NAME" \
        --description "$WRITER_GROUP_DESCRIPTION" \
        --query id \
        --output tsv)
    ok "Created group '$WRITER_GROUP_NAME'"
fi

echo "$WRITER_GROUP_ID" > "$SCRIPT_DIR/.writer_group_id"
ok "  Object ID: $WRITER_GROUP_ID"

# ── Summary ───────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${GREEN}  ✓ Security Groups Created${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${BOLD}$READER_GROUP_NAME:${NC} $READER_GROUP_ID"
echo -e "  ${BOLD}$WRITER_GROUP_NAME:${NC} $WRITER_GROUP_ID"
echo ""
