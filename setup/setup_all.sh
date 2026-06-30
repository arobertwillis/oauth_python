#!/usr/bin/env bash
# ============================================================
# Run All Setup Steps
#
# This is the main entry point — it runs all setup scripts in
# order and gives you a fully configured Azure + FastAPI setup.
#
# What it does:
#   1. Creates an App Registration with PKCE/SPA config
#   2. Creates api-readers and api-writers security groups
#   3. Creates reader and writer test users
#   4. Assigns users to groups and groups to the enterprise app
#   5. Generates the .env file with all Azure IDs
#
# Prerequisites:
#   - Azure CLI installed (https://aka.ms/install-azure-cli)
#   - jq installed (brew install jq)
#   - Logged in to Azure CLI (az login)
#   - Sufficient permissions in your tenant:
#     • Application Administrator (for app registration)
#     • Groups Administrator (for security groups)
#     • User Administrator (for creating users)
#     — or Global Administrator (covers all of the above)
#
# Usage:
#   ./setup/setup_all.sh
#
# To undo everything:
#   ./setup/teardown.sh
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║         OAuth Python API — Azure Setup                      ║${NC}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ── Pre-flight checks ─────────────────────────────────────────
info "Running pre-flight checks..."

require_cmd az
require_cmd jq
require_cmd uuidgen

require_az_login
ok "Azure CLI is installed and logged in"

TENANT_ID=$(get_tenant_id)
TENANT_DOMAIN=$(get_tenant_domain)
ok "Tenant: $TENANT_DOMAIN (ID: $TENANT_ID)"

SIGNED_IN_USER=$(az ad signed-in-user show --query displayName --output tsv 2>/dev/null || echo "unknown")
ok "Signed in as: $SIGNED_IN_USER"

echo ""
echo -e "  ${BOLD}This script will create the following in your Azure tenant:${NC}"
echo -e "    • App registration:  $APP_NAME"
echo -e "    • Security groups:   $READER_GROUP_NAME, $WRITER_GROUP_NAME"
echo -e "    • Test users:        ${READER_USERNAME}@${TENANT_DOMAIN}, ${WRITER_USERNAME}@${TENANT_DOMAIN}"
echo ""
echo -e "  ${YELLOW}All resources use the Entra ID Free tier (no cost).${NC}"
echo ""

read -p "  Proceed? (y/N): " PROCEED
if [[ ! "$PROCEED" =~ ^[Yy]$ ]]; then
    info "Setup cancelled."
    exit 0
fi

# ── Run each step ─────────────────────────────────────────────
bash "$SCRIPT_DIR/01_create_app_registration.sh"
bash "$SCRIPT_DIR/02_create_groups.sh"
bash "$SCRIPT_DIR/03_create_users.sh"
bash "$SCRIPT_DIR/04_assign_memberships.sh"
bash "$SCRIPT_DIR/06_create_client_app.sh"
bash "$SCRIPT_DIR/07_configure_certificates.sh"
bash "$SCRIPT_DIR/05_generate_env.sh"

# ── Final Summary ─────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                                                              ║${NC}"
echo -e "${GREEN}║   ${BOLD}✓  Azure Setup Complete!${NC}${GREEN}                                   ║${NC}"
echo -e "${GREEN}║                                                              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}Next steps:${NC}"
echo ""
echo -e "  1. ${CYAN}Start the API:${NC}"
echo -e "     source .venv/bin/activate"
echo -e "     uvicorn app.main:app --reload"
echo ""
echo -e "  2. ${CYAN}Open Swagger UI:${NC}"
echo -e "     http://localhost:8000/docs"
echo ""
echo -e "  3. ${CYAN}Sign in with a test user:${NC}"
echo -e "     Click 'Authorize' → sign in with reader or writer"
echo -e "     Temporary password: $TEMP_PASSWORD"
echo -e "     (Users must change password on first sign-in)"
echo ""
echo -e "  4. ${CYAN}Test the endpoints:${NC}"
echo -e "     Reader → can GET /api/items, cannot POST"
echo -e "     Writer → can GET and POST /api/items"
echo ""
echo -e "  ${YELLOW}To undo this setup:${NC}  ./setup/teardown.sh"
echo ""
