#!/usr/bin/env bash
# ============================================================
# Teardown: Remove All Azure Resources
#
# This script removes everything created by the setup scripts:
#   - App registration (and its service principal)
#   - Security groups (api-readers, api-writers)
#   - Test users (reader, writer)
#   - The .env file
#   - Temporary state files in setup/
#
# Prerequisites:
#   - Azure CLI installed and logged in
#
# Usage:
#   ./setup/teardown.sh
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/config.sh"

require_cmd az
require_az_login

echo ""
echo -e "${RED}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${RED}║          OAuth Python API — Teardown                        ║${NC}"
echo -e "${RED}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}${RED}This will permanently delete:${NC}"
echo -e "    • App registration: $APP_NAME"
echo -e "    • Security groups:  $READER_GROUP_NAME, $WRITER_GROUP_NAME"
echo -e "    • Test users:       ${READER_USERNAME}@..., ${WRITER_USERNAME}@..."
echo -e "    • .env file"
echo ""

read -p "  Are you sure? Type 'yes' to confirm: " CONFIRM
if [[ "$CONFIRM" != "yes" ]]; then
    info "Teardown cancelled."
    exit 0
fi

echo ""

# ── Helper to safely read a state file ────────────────────────
read_id() {
    local file="$SCRIPT_DIR/$1"
    if [[ -f "$file" ]]; then
        cat "$file"
    else
        echo ""
    fi
}

# ── Delete App Registrations ──────────────────────────────────
step "Deleting App Registrations"

# Delete Client App
CLIENT_APP_OBJECT_ID=$(read_id ".client_app_object_id")
if [[ -n "$CLIENT_APP_OBJECT_ID" ]]; then
    info "Deleting client app registration (Object ID: $CLIENT_APP_OBJECT_ID)..."
    az ad app delete --id "$CLIENT_APP_OBJECT_ID" 2>/dev/null && \
        ok "Deleted client app registration '$CLIENT_APP_NAME'" || \
        warn "Could not delete client app registration (may already be deleted)"
else
    CLIENT_APP_OBJECT_ID=$(az ad app list --display-name "$CLIENT_APP_NAME" --query "[0].id" --output tsv 2>/dev/null || echo "")
    if [[ -n "$CLIENT_APP_OBJECT_ID" && "$CLIENT_APP_OBJECT_ID" != "None" ]]; then
        info "Found client app registration by name, deleting..."
        az ad app delete --id "$CLIENT_APP_OBJECT_ID" 2>/dev/null && \
            ok "Deleted client app registration '$CLIENT_APP_NAME'" || \
            warn "Could not delete client app registration"
    fi
fi

# Delete API App
APP_OBJECT_ID=$(read_id ".app_object_id")

if [[ -n "$APP_OBJECT_ID" ]]; then
    info "Deleting app registration (Object ID: $APP_OBJECT_ID)..."
    az ad app delete --id "$APP_OBJECT_ID" 2>/dev/null && \
        ok "Deleted app registration '$APP_NAME'" || \
        warn "Could not delete app registration (may already be deleted)"
else
    # Try to find it by name
    APP_OBJECT_ID=$(az ad app list --display-name "$APP_NAME" --query "[0].id" --output tsv 2>/dev/null || echo "")
    if [[ -n "$APP_OBJECT_ID" && "$APP_OBJECT_ID" != "None" ]]; then
        info "Found app registration by name, deleting..."
        az ad app delete --id "$APP_OBJECT_ID" 2>/dev/null && \
            ok "Deleted app registration '$APP_NAME'" || \
            warn "Could not delete app registration"
    else
        info "App registration '$APP_NAME' not found (already deleted?)"
    fi
fi

# ── Delete Test Users ─────────────────────────────────────────
step "Deleting Test Users"

TENANT_DOMAIN=$(read_id ".tenant_domain")
if [[ -z "$TENANT_DOMAIN" ]]; then
    TENANT_DOMAIN=$(get_tenant_domain)
fi

for USERNAME in "$READER_USERNAME" "$WRITER_USERNAME"; do
    UPN="${USERNAME}@${TENANT_DOMAIN}"
    info "Deleting user '$UPN'..."

    USER_ID=$(az ad user list \
        --filter "userPrincipalName eq '$UPN'" \
        --query "[0].id" \
        --output tsv 2>/dev/null || echo "")

    if [[ -n "$USER_ID" && "$USER_ID" != "None" ]]; then
        az ad user delete --id "$USER_ID" 2>/dev/null && \
            ok "Deleted user '$UPN'" || \
            warn "Could not delete user '$UPN'"
    else
        info "User '$UPN' not found (already deleted?)"
    fi
done

# ── Delete Security Groups ───────────────────────────────────
step "Deleting Security Groups"

for GROUP_NAME in "$READER_GROUP_NAME" "$WRITER_GROUP_NAME"; do
    info "Deleting group '$GROUP_NAME'..."

    GROUP_ID=$(az ad group list \
        --display-name "$GROUP_NAME" \
        --query "[?displayName=='$GROUP_NAME'].id" \
        --output tsv 2>/dev/null || echo "")

    if [[ -n "$GROUP_ID" ]]; then
        az ad group delete --group "$GROUP_ID" 2>/dev/null && \
            ok "Deleted group '$GROUP_NAME'" || \
            warn "Could not delete group '$GROUP_NAME'"
    else
        info "Group '$GROUP_NAME' not found (already deleted?)"
    fi
done

# ── Clean up local files ─────────────────────────────────────
step "Cleaning Up Local Files"

# Remove .env file
ENV_FILE="$REPO_ROOT/$ENV_OUTPUT_FILE"
if [[ -f "$ENV_FILE" ]]; then
    rm "$ENV_FILE"
    ok "Deleted .env file"
else
    info ".env file not found"
fi

CLIENT_ENV_FILE="$REPO_ROOT/.env.client"
if [[ -f "$CLIENT_ENV_FILE" ]]; then
    rm "$CLIENT_ENV_FILE"
    ok "Deleted .env.client file"
fi

# Remove state files
for STATE_FILE in .app_client_id .app_object_id .sp_object_id .scope_id \
                  .role_read_id .role_write_id \
                  .client_app_client_id .client_app_object_id .client_sp_object_id .client_secret \
                  .reader_group_id .writer_group_id \
                  .reader_user_id .writer_user_id .tenant_domain; do
    if [[ -f "$SCRIPT_DIR/$STATE_FILE" ]]; then
        rm "$SCRIPT_DIR/$STATE_FILE"
    fi
done
ok "Deleted temporary state files"

# ── Summary ───────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${GREEN}  ✓ Teardown Complete${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  All Azure resources and local config have been removed."
echo -e "  To set up again, run: ${CYAN}./setup/setup_all.sh${NC}"
echo ""
